
from pathlib import Path
import math

import pandas as pd
from openpyxl import load_workbook


# --------------------------------------------------
# 1. LOAD DATA FROM EXCEL AND CSV
# --------------------------------------------------

PROJECT_FOLDER = Path(__file__).parent
EXCEL_FILE = PROJECT_FOLDER / "Production_Planning_Input.xlsx"
OPEN_PO_FILE = PROJECT_FOLDER / "open_purchase_orders.csv"


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
    """Load all Excel tables and open purchase orders."""

    if not EXCEL_FILE.exists():
        raise FileNotFoundError(
            f"Excel file not found: {EXCEL_FILE}"
        )

    if not OPEN_PO_FILE.exists():
        raise FileNotFoundError(
            f"Open purchase orders file not found: {OPEN_PO_FILE}"
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

    open_purchase_orders = pd.read_csv(
    OPEN_PO_FILE,
    sep="\t"
)
    data_tables["open_purchase_orders"] = open_purchase_orders

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

def distribute_mps_to_weeks(mps_df):

    weekly_rows = []

    for _, row in mps_df.iterrows():

        month_start = pd.Timestamp(row["Month"]).to_period("M").start_time
        month_end = month_start + pd.offsets.MonthEnd(0)

        monthly_production = int(row["Planned_Production"])

        # Group the days of the month by ISO calendar week.
        week_groups = {}

        for day in pd.date_range(month_start, month_end):

            iso_year, iso_week, _ = day.isocalendar()

            week_start = day - pd.Timedelta(days=day.weekday())
            week_end = week_start + pd.Timedelta(days=6)

            key = (iso_year, iso_week)

            if key not in week_groups:
                week_groups[key] = {
                    "Week_Start": week_start,
                    "Week_End": week_end,
                    "Days_In_Month": 0
                }

            week_groups[key]["Days_In_Month"] += 1

        # Calculate proportional weekly quantities.
        weeks = list(week_groups.values())
        days_in_month = sum(w["Days_In_Month"] for w in weeks)

        allocations = []

        for week in weeks:

            exact_quantity = (
                monthly_production
                * week["Days_In_Month"]
                / days_in_month
            )

            allocations.append({
                **week,
                "Exact_Quantity": exact_quantity,
                "Weekly_Production": int(exact_quantity)
            })

        # Distribute remaining units without losing production.
        remaining_units = (
            monthly_production
            - sum(w["Weekly_Production"] for w in allocations)
        )

        allocations.sort(
            key=lambda w: (
                -(w["Exact_Quantity"] - w["Weekly_Production"]),
                w["Week_Start"]
            )
        )

        for i in range(remaining_units):
            allocations[i]["Weekly_Production"] += 1

        # Save weekly production.
        for week in allocations:

            iso_year, iso_week, _ = week["Week_Start"].isocalendar()

            weekly_rows.append({
                "Product_ID": row["Product_ID"],
                "Month": month_start,
                "Week_Start": week["Week_Start"],
                "Week_End": week["Week_End"],
                "Calendar_Week": f"CW{iso_week:02d}-{iso_year}",
                "Week_Days_In_Month": week["Days_In_Month"],
                "Planned_Production": week["Weekly_Production"]
            })

    return pd.DataFrame(weekly_rows)

def build_mrp(
    mps_df,
    bom_df,
    inventory_df,
    purchasing_df,
    open_purchase_orders_df=None,
    planning_start="2026-01-01",
    evaluation_date="2025-12-01",
):
    """
    Calculate gross and net material requirements,
    existing purchase order receipts, planned receipts,
    inventory projections, release dates, and costs.

    The current version supports L4L lot sizing.
    """

    # ----------------------------------------------
    # 3.1 COPY INPUT DATA
    # ----------------------------------------------

    mps = mps_df.copy()
    bom = bom_df.copy()
    inventory = inventory_df.copy()
    purchasing = purchasing_df.copy()

    if open_purchase_orders_df is None:
        open_pos = pd.DataFrame()
    else:
        open_pos = open_purchase_orders_df.copy()

    planning_start = pd.Timestamp(planning_start)
    evaluation_date = pd.Timestamp(evaluation_date)

    # ----------------------------------------------
    # 3.2 VALIDATE AND CONVERT DATA TYPES
    # ----------------------------------------------

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

    # ----------------------------------------------
    # 3.3 PREPARE OPEN PURCHASE ORDERS
    # ----------------------------------------------

    if not open_pos.empty:

        required_po_columns = [
            "Component_ID",
            "Expected_Arrival_Date",
            "Order_Quantity",
            "Status",
        ]

        missing_columns = [
            col for col in required_po_columns
            if col not in open_pos.columns
        ]

        if missing_columns:
            raise ValueError(
                f"Missing columns in open purchase orders: "
                f"{missing_columns}"
            )

        open_pos["Expected_Arrival_Date"] = pd.to_datetime(
            open_pos["Expected_Arrival_Date"],
            format="%m/%d/%Y",
            errors="raise"
        )

        open_pos["Order_Quantity"] = pd.to_numeric(
            open_pos["Order_Quantity"],
            errors="raise"
        )

        if (open_pos["Order_Quantity"] < 0).any():
            raise ValueError(
                "Purchase order quantities cannot be negative."
            )

        open_pos["Status"] = (
            open_pos["Status"]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        open_pos = open_pos[
            open_pos["Status"].isin(["OPEN", "RECEIVED"])
        ].copy()

    else:
        open_pos = pd.DataFrame(
            columns=[
                "Component_ID",
                "Expected_Arrival_Date",
                "Order_Quantity",
                "Status",
            ]
        )

    # ----------------------------------------------
    # 3.4 CREATE LOOKUP DICTIONARIES
    # ----------------------------------------------

    inventory_lookup = (
        inventory.set_index("Item_ID").to_dict("index")
    )

    purchasing_lookup = (
        purchasing.set_index("Component_ID").to_dict("index")
    )

    # ----------------------------------------------
    # 3.5 CALCULATE GROSS REQUIREMENTS
    # ----------------------------------------------

    gross_requirements = {}

    for _, plan_row in mps.iterrows():

        product_id = plan_row["Product_ID"]
        month = pd.Timestamp(plan_row["Month"])

        planned_units = int(
            plan_row["Planned_Production"]
        )

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

    # ----------------------------------------------
    # 3.6 SEPARATE EXISTING PURCHASE ORDER RECEIPTS
    # ----------------------------------------------

    po_before_start = {}
    po_by_month = {}

    for _, po_row in open_pos.iterrows():

        component_id = po_row["Component_ID"]

        arrival_date = pd.Timestamp(
            po_row["Expected_Arrival_Date"]
        )

        quantity = int(po_row["Order_Quantity"])

        # Ignore orders that arrived on or before
        # the evaluation date.
        if arrival_date <= evaluation_date:
            continue

        # Orders arriving after evaluation date
        # but before planning starts.
        if arrival_date < planning_start:

            po_before_start[component_id] = (
                po_before_start.get(component_id, 0)
                + quantity
            )

        # Orders arriving during the planning horizon.
        else:

            arrival_month = (
                arrival_date.to_period("M").to_timestamp()
            )

            key = (component_id, arrival_month)

            po_by_month[key] = (
                po_by_month.get(key, 0) + quantity
            )

    # ----------------------------------------------
    # 3.7 CALCULATE MRP BY COMPONENT AND MONTH
    # ----------------------------------------------

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

        # Initial inventory plus purchase orders
        # arriving before the planning horizon.
        projected_inventory = (
            int(component_inventory["Initial_Stock"])
            + po_before_start.get(component_id, 0)
        )

        safety_stock = int(
            component_inventory["Safety_Stock"]
        )

        unit_cost = float(
            purchasing_data["Unit_Cost"]
        )

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

        # ------------------------------------------
        # 3.8 MONTHLY MATERIAL REQUIREMENTS
        # ------------------------------------------

        for month_value in months:

            month = pd.Timestamp(month_value)

            gross_qty = gross_requirements.get(
                (component_id, month),
                0
            )

            beginning_inventory = projected_inventory

            # Existing purchase orders arriving this month.
            open_po_receipts = po_by_month.get(
                (component_id, month),
                0
            )

            # Net requirements after considering
            # inventory, safety stock, and existing POs.
            net_requirement = max(
                0,
                gross_qty
                + safety_stock
                - beginning_inventory
                - open_po_receipts
            )

            # L4L: planned receipt equals net requirement.
            planned_receipt = net_requirement

            # Ending inventory includes existing POs
            # and newly planned purchase receipts.
            ending_inventory = (
                beginning_inventory
                + open_po_receipts
                + planned_receipt
                - gross_qty
            )

            # Calculate planned order release date.
            if planned_receipt > 0:

                release_date = (
                    month - pd.Timedelta(
                        weeks=lead_time_weeks
                    )
                )

            else:
                release_date = pd.NaT

            # Determine order status.
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

            # Save monthly MRP results.
            mrp_rows.append({
                "Component_ID": component_id,
                "Month": month,
                "Gross_Requirements": gross_qty,
                "Beginning_Inventory": beginning_inventory,
                "Open_PO_Receipts": open_po_receipts,
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

    # ----------------------------------------------
    # 3.9 RETURN MRP RESULTS
    # ----------------------------------------------

    mrp_df = pd.DataFrame(mrp_rows)

    return mrp_df.sort_values(
        ["Component_ID", "Month"]
    ).reset_index(drop=True)
