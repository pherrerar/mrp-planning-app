
from pathlib import Path
import math

import pandas as pd
from openpyxl import load_workbook


# --------------------------------------------------
# 1. LOAD DATA FROM EXCEL
# --------------------------------------------------

PROJECT_FOLDER = Path(__file__).parent
EXCEL_FILE = PROJECT_FOLDER / "Production_Planning_Input.xlsx"


def read_excel_table(workbook, table_name):
    """Read an Excel named table into a pandas DataFrame."""

    for sheet in workbook.worksheets:
        if table_name in sheet.tables:
            table = sheet.tables[table_name]
            rows = list(sheet[table.ref])

            values = [
                [cell.value for cell in row]
                for row in rows
            ]

            headers = values[0]
            data = values[1:]

            df = pd.DataFrame(data, columns=headers)
            return df.dropna(how="all")

    raise ValueError(
        f"Table '{table_name}' was not found in the workbook."
    )


def load_data():
    """Load all Excel tables needed by the MRP model."""

    if not EXCEL_FILE.exists():
        raise FileNotFoundError(
            f"Excel file not found: {EXCEL_FILE}"
        )

    table_names = [
        "tblProducts",
        "tblHistoricalSales",
        "tblInventory",
        "tblBOM",
        "tblProductionParameters",
        "tblProductCosts",
        "tblPurchasing",
    ]

    workbook = load_workbook(
        EXCEL_FILE,
        data_only=True
    )

    try:
        data_tables = {
            name: read_excel_table(workbook, name)
            for name in table_names
        }
    finally:
        workbook.close()

    return data_tables


# --------------------------------------------------
# 2. BUILD THE MASTER PRODUCTION SCHEDULE (MPS)
# --------------------------------------------------

def build_mps(forecast_df, inventory_df):
    """
    Calculate planned production using demand,
    beginning inventory, and safety stock.

    Required forecast columns:
    Product_ID, Forecast_Month, Forecast_Units

    Required inventory columns:
    Item_ID, Initial_Stock, Safety_Stock
    """

    forecast = forecast_df.copy()
    inventory = inventory_df.copy()

    forecast["Forecast_Month"] = pd.to_datetime(
        forecast["Forecast_Month"]
    )

    forecast["Forecast_Units"] = pd.to_numeric(
        forecast["Forecast_Units"],
        errors="raise"
    )

    inventory["Initial_Stock"] = pd.to_numeric(
        inventory["Initial_Stock"],
        errors="raise"
    )

    inventory["Safety_Stock"] = pd.to_numeric(
        inventory["Safety_Stock"],
        errors="raise"
    )

    inventory_lookup = (
        inventory.set_index("Item_ID").to_dict("index")
    )

    mps_rows = []

    for product_id, group in forecast.groupby("Product_ID"):

        if product_id not in inventory_lookup:
            raise ValueError(
                f"Inventory data missing for {product_id}"
            )

        initial_stock = inventory_lookup[product_id][
            "Initial_Stock"
        ]

        safety_stock = inventory_lookup[product_id][
            "Safety_Stock"
        ]

        projected_inventory = initial_stock

        group = group.sort_values("Forecast_Month")

        for _, row in group.iterrows():

            demand = math.ceil(row["Forecast_Units"])
            beginning_inventory = projected_inventory

            planned_production = max(
                0,
                demand + safety_stock - beginning_inventory
            )

            ending_inventory = (
                beginning_inventory
                + planned_production
                - demand
            )

            mps_rows.append({
                "Product_ID": product_id,
                "Month": row["Forecast_Month"],
                "Forecast_Demand": demand,
                "Beginning_Inventory": beginning_inventory,
                "Safety_Stock": safety_stock,
                "Planned_Production": planned_production,
                "Ending_Inventory": ending_inventory,
            })

            projected_inventory = ending_inventory

    mps_df = pd.DataFrame(mps_rows)

    return mps_df.sort_values(
        ["Product_ID", "Month"]
    ).reset_index(drop=True)


# --------------------------------------------------
# 3. BUILD THE MATERIAL REQUIREMENTS PLAN (MRP)
# --------------------------------------------------

def build_mrp(
    mps_df,
    bom_df,
    inventory_df,
    purchasing_df,
    planning_start="2026-01-01",
    evaluation_date="2025-12-01",
):
    """
    Calculate gross and net material requirements,
    planned receipts, inventory projections,
    release dates, and estimated purchase costs.

    The current version supports the L4L lot-sizing rule.
    """

    mps = mps_df.copy()
    bom = bom_df.copy()
    inventory = inventory_df.copy()
    purchasing = purchasing_df.copy()

    mps["Month"] = pd.to_datetime(mps["Month"])

    bom["Quantity_Per_Unit"] = pd.to_numeric(
        bom["Quantity_Per_Unit"],
        errors="raise"
    )

    inventory["Initial_Stock"] = pd.to_numeric(
        inventory["Initial_Stock"],
        errors="raise"
    )

    inventory["Safety_Stock"] = pd.to_numeric(
        inventory["Safety_Stock"],
        errors="raise"
    )

    purchasing["Unit_Cost"] = pd.to_numeric(
        purchasing["Unit_Cost"],
        errors="raise"
    )

    purchasing["Lead_Time_Weeks"] = pd.to_numeric(
        purchasing["Lead_Time_Weeks"],
        errors="raise"
    )

    inventory_lookup = (
        inventory.set_index("Item_ID").to_dict("index")
    )

    purchasing_lookup = (
        purchasing.set_index("Component_ID").to_dict("index")
    )

    # Calculate gross requirements by component and month.
    gross_requirements = {}

    for _, plan_row in mps.iterrows():

        product_id = plan_row["Product_ID"]
        month = pd.Timestamp(plan_row["Month"])
        planned_units = int(plan_row["Planned_Production"])

        product_bom = bom[
            bom["Product_ID"] == product_id
        ]

        for _, bom_row in product_bom.iterrows():

            component_id = bom_row["Component_ID"]

            quantity_per_unit = bom_row[
                "Quantity_Per_Unit"
            ]

            gross_qty = math.ceil(
                planned_units * quantity_per_unit
            )

            key = (component_id, month)

            gross_requirements[key] = (
                gross_requirements.get(key, 0) + gross_qty
            )

    components = sorted(
        {component for component, month in gross_requirements}
    )

    months = sorted(mps["Month"].unique())

    planning_start = pd.Timestamp(planning_start)
    evaluation_date = pd.Timestamp(evaluation_date)

    mrp_rows = []

    for component_id in components:

        if component_id not in inventory_lookup:
            raise ValueError(
                f"Missing inventory data for {component_id}"
            )

        if component_id not in purchasing_lookup:
            raise ValueError(
                f"Missing purchasing data for {component_id}"
            )

        component_inventory = inventory_lookup[component_id]
        purchasing_data = purchasing_lookup[component_id]

        projected_inventory = int(
            component_inventory["Initial_Stock"]
        )

        safety_stock = int(
            component_inventory["Safety_Stock"]
        )

        unit_cost = float(purchasing_data["Unit_Cost"])
        lead_time_weeks = int(
            purchasing_data["Lead_Time_Weeks"]
        )

        lot_rule = str(
            purchasing_data["Lot_Sizing_Rule"]
        ).strip().upper()

        if lot_rule != "L4L":
            raise ValueError(
                f"Lot-sizing rule '{lot_rule}' for "
                f"{component_id} is not implemented. "
                "This version supports L4L."
            )

        for month_value in months:

            month = pd.Timestamp(month_value)

            gross_qty = gross_requirements.get(
                (component_id, month),
                0
            )

            beginning_inventory = projected_inventory

            net_requirement = max(
                0,
                gross_qty + safety_stock - beginning_inventory
            )

            planned_receipt = net_requirement

            ending_inventory = (
                beginning_inventory
                + planned_receipt
                - gross_qty
            )

            if planned_receipt > 0:
                release_date = (
                    month - pd.Timedelta(
                        weeks=lead_time_weeks
                    )
                )
            else:
                release_date = pd.NaT

            if planned_receipt == 0:
                order_status = "No order required"

            elif release_date < planning_start:

                if release_date < evaluation_date:
                    order_status = (
                        "URGENT: release date has passed"
                    )
                else:
                    order_status = (
                        "Release before planning horizon"
                    )

            else:
                order_status = "Planned order"

            mrp_rows.append({
                "Component_ID": component_id,
                "Month": month,
                "Gross_Requirements": gross_qty,
                "Beginning_Inventory": beginning_inventory,
                "Safety_Stock": safety_stock,
                "Net_Requirements": net_requirement,
                "Planned_Order_Receipt": planned_receipt,
                "Ending_Inventory": ending_inventory,
                "Lead_Time_Weeks": lead_time_weeks,
                "Planned_Order_Release_Date": release_date,
                "Unit_Cost": unit_cost,
                "Estimated_Purchase_Cost": (
                    planned_receipt * unit_cost
                ),
                "Order_Status": order_status,
            })

            projected_inventory = ending_inventory

    mrp_df = pd.DataFrame(mrp_rows)

    return mrp_df.sort_values(
        ["Component_ID", "Month"]
    ).reset_index(drop=True)
