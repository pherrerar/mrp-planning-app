
from pathlib import Path
from openpyxl import load_workbook
import pandas as pd

# 1. Locate the Excel file
PROJECT_FOLDER = Path(__file__).parent
EXCEL_FILE = PROJECT_FOLDER / "Production_Planning_Input.xlsx"

if not EXCEL_FILE.exists():
    raise FileNotFoundError(f"Excel file not found: {EXCEL_FILE}")

# 2. Open the workbook
workbook = load_workbook(EXCEL_FILE, data_only=True)

print("\nExcel file opened successfully!")

# 3. Read an Excel table into a DataFrame
def read_excel_table(workbook, table_name):
    for sheet in workbook.worksheets:
        if table_name in sheet.tables:
            table = sheet.tables[table_name]
            rows = list(
                sheet[table.ref]
            )

            values = [
                [cell.value for cell in row]
                for row in rows
            ]

            headers = values[0]
            data = values[1:]

            df = pd.DataFrame(data, columns=headers)

            # Remove completely empty rows
            df = df.dropna(how="all")

            return df

    raise ValueError(
        f"Table '{table_name}' was not found in the workbook."
    )

# 4. Load all seven tables
table_names = [
    "tblProducts",
    "tblHistoricalSales",
    "tblInventory",
    "tblBOM",
    "tblProductionParameters",
    "tblProductCosts",
    "tblPurchasing"
]

data_tables = {}

for table_name in table_names:
    df = read_excel_table(workbook, table_name)
    data_tables[table_name] = df

    print(f"\n{'=' * 50}")
    print(f"Table: {table_name}")
    print(f"Number of rows: {len(df)}")
    print(f"Columns: {list(df.columns)}")
    print("\nFirst 5 rows:")
    print(df.head().to_string(index=False))

workbook.close()

print("\nAll tables loaded successfully!")

# STEP 4: Validate data relationships

print("\n" + "=" * 50)
print("MRP DATA VALIDATION")
print("=" * 50)

products = data_tables["tblProducts"]
sales = data_tables["tblHistoricalSales"]
inventory = data_tables["tblInventory"]
bom = data_tables["tblBOM"]
purchasing = data_tables["tblPurchasing"]

errors = []

# 1. Check that sales products exist in the products table
valid_products = set(products["Product_ID"].dropna())
sales_products = set(sales["Product_ID"].dropna())

unknown_sales_products = sales_products - valid_products

if unknown_sales_products:
    errors.append(
        f"Sales contain unknown products: {unknown_sales_products}"
    )
else:
    print("PASS: All sales products exist in tblProducts.")

# 2. Check that every BOM component has inventory data
bom_components = set(bom["Component_ID"].dropna())
inventory_items = set(inventory["Item_ID"].dropna())

missing_inventory = bom_components - inventory_items

if missing_inventory:
    errors.append(
        f"Missing inventory records: {missing_inventory}"
    )
else:
    print("PASS: All BOM components have inventory records.")

# 3. Check that every BOM component has purchasing data
purchasing_components = set(purchasing["Component_ID"].dropna())

missing_purchasing = bom_components - purchasing_components

if missing_purchasing:
    errors.append(
        f"Missing purchasing records: {missing_purchasing}"
    )
else:
    print("PASS: All BOM components have purchasing records.")

# 4. Check BOM product references
bom_products = set(bom["Product_ID"].dropna())
unknown_bom_products = bom_products - valid_products

if unknown_bom_products:
    errors.append(
        f"BOM contains unknown products: {unknown_bom_products}"
    )
else:
    print("PASS: All BOM products exist in tblProducts.")

# 5. Check inventory values
if inventory[["Initial_Stock", "Safety_Stock"]].isna().any().any():
    errors.append("Inventory contains missing stock values.")
elif (
    inventory[["Initial_Stock", "Safety_Stock"]] < 0
).any().any():
    errors.append("Inventory contains negative stock values.")
else:
    print("PASS: Inventory values are present and nonnegative.")

# 6. Check BOM quantities
if bom["Quantity_Per_Unit"].isna().any():
    errors.append("BOM contains missing component quantities.")
elif (bom["Quantity_Per_Unit"] <= 0).any():
    errors.append("BOM contains zero or negative quantities.")
else:
    print("PASS: BOM quantities are positive.")

# Final result
print("\n" + "-" * 50)

if errors:
    print("VALIDATION FAILED:")
    for error in errors:
        print(f"- {error}")
else:
    print("ALL CHECKS PASSED!")
    print("The data relationships are ready for the next step.")

# STEP 5: Consolidated Material Requirements Planning

print("\n" + "=" * 50)
print("CONSOLIDATED MATERIAL REQUIREMENTS PLANNING")
print("=" * 50)

# Example production plan for testing
production_plan = {
    "PLG": 100,
    "PDG": 80
}

print("\nExample production plan:")
for product_id, quantity in production_plan.items():
    print(f"{product_id}: {quantity} units")

bom = data_tables["tblBOM"]
inventory = data_tables["tblInventory"]

# Store inventory information by component
inventory_lookup = inventory.set_index("Item_ID").to_dict("index")

# Step 1: Calculate and consolidate gross requirements
gross_requirements = {}

for _, row in bom.iterrows():
    product_id = row["Product_ID"]

    if product_id not in production_plan:
        continue

    component_id = row["Component_ID"]
    planned_units = production_plan[product_id]
    quantity_per_unit = row["Quantity_Per_Unit"]

    gross_qty = planned_units * quantity_per_unit

    if component_id not in gross_requirements:
        gross_requirements[component_id] = 0

    gross_requirements[component_id] += gross_qty

# Step 2: Subtract inventory and protect safety stock once
requirements = []

for component_id, gross_qty in gross_requirements.items():
    component_inventory = inventory_lookup[component_id]

    initial_stock = component_inventory["Initial_Stock"]
    safety_stock = component_inventory["Safety_Stock"]

    available_stock = max(0, initial_stock - safety_stock)
    net_requirement = max(0, gross_qty - available_stock)

    requirements.append({
        "Component_ID": component_id,
        "Gross_Requirement": gross_qty,
        "Initial_Stock": initial_stock,
        "Safety_Stock": safety_stock,
        "Available_Stock_After_Safety": available_stock,
        "Net_Requirement": net_requirement
    })

requirements_df = pd.DataFrame(requirements)

requirements_df = requirements_df.sort_values("Component_ID")

print("\nConsolidated material requirements:")
print(requirements_df.to_string(index=False))

# Step 3: Save results
output_folder = PROJECT_FOLDER / "outputs"
output_folder.mkdir(exist_ok=True)

output_file = output_folder / "basic_material_requirements.csv"
requirements_df.to_csv(output_file, index=False)

print(f"\nResults saved to: {output_file}")
print("\nConsolidated MRP calculation completed successfully!")

# STEP 6: Calculate Planned Purchase Order Timing

print("\n" + "=" * 50)
print("MRP: PLANNED PURCHASE ORDER TIMING")
print("=" * 50)

# Assumption for this example:
# All required materials are needed in Week 4.
NEED_WEEK = 4

# Load purchasing information from Excel
purchasing = data_tables["tblPurchasing"].copy()

# Combine net material requirements with supplier information
purchase_plan = requirements_df.merge(
    purchasing[
        [
            "Component_ID",
            "Unit_Cost",
            "Lead_Time_Weeks",
            "Lot_Sizing_Rule"
        ]
    ],
    on="Component_ID",
    how="left"
)

# Calculate when the purchase order should be released
purchase_plan["Need_Week"] = NEED_WEEK

purchase_plan["Order_Release_Week"] = (
    purchase_plan["Need_Week"]
    - purchase_plan["Lead_Time_Weeks"]
)

# Flag orders that should already be released
purchase_plan["Order_Status"] = purchase_plan[
    "Order_Release_Week"
].apply(
    lambda week: (
        "Order now / past due"
        if pd.notna(week) and week <= 0
        else (
            f"Release in week {int(week)}"
            if pd.notna(week)
            else "Check lead time"
        )
    )
)

# Show only components that need additional material
purchase_plan = purchase_plan[
    purchase_plan["Net_Requirement"] > 0
].copy()

# Select and organize useful columns
purchase_plan = purchase_plan[
    [
        "Component_ID",
        "Net_Requirement",
        "Unit_Cost",
        "Lead_Time_Weeks",
        "Lot_Sizing_Rule",
        "Need_Week",
        "Order_Release_Week",
        "Order_Status"
    ]
]

# Calculate estimated purchase cost
purchase_plan["Estimated_Purchase_Cost"] = (
    purchase_plan["Net_Requirement"]
    * purchase_plan["Unit_Cost"]
)

purchase_plan = purchase_plan.sort_values(
    "Order_Release_Week"
)

print("\nPlanned purchase orders:")
print(purchase_plan.to_string(index=False))

# Save the purchase plan
output_file = output_folder / "planned_purchase_orders.csv"
purchase_plan.to_csv(output_file, index=False)

print(f"\nPurchase plan saved to: {output_file}")
print("\nPurchase order timing calculated successfully!")

# STEP 7: Prepare Historical Sales for Forecasting

print("\n" + "=" * 50)
print("STEP 7: PREPARING HISTORICAL SALES")
print("=" * 50)

sales = data_tables["tblHistoricalSales"].copy()

# Convert month column to datetime
sales["Month"] = pd.to_datetime(sales["Month"])

# Ensure sales quantities are numeric
sales["Units_Sold"] = pd.to_numeric(
    sales["Units_Sold"],
    errors="coerce"
)

# Check for missing or invalid data
if sales["Units_Sold"].isna().any():
    raise ValueError(
        "Historical sales contains missing or invalid Units_Sold values."
    )

if (sales["Units_Sold"] < 0).any():
    raise ValueError(
        "Historical sales contains negative Units_Sold values."
    )

# Sort by product and month
sales = sales.sort_values(
    ["Product_ID", "Month"]
).reset_index(drop=True)

# Display the number of observations per product
print("\nHistorical observations by product:")

for product_id, group in sales.groupby("Product_ID"):
    print(
        f"{product_id}: {len(group)} observations, "
        f"from {group['Month'].min():%b %Y} "
        f"to {group['Month'].max():%b %Y}"
    )

print("\nMost recent sales observations:")
print(sales.groupby("Product_ID").tail(3).to_string(index=False))

# Save a clean copy for forecasting
output_file = output_folder / "clean_historical_sales.csv"
sales.to_csv(output_file, index=False)

print(f"\nClean historical sales saved to: {output_file}")
print("\nHistorical sales preparation completed successfully!")

# STEP 8: Compare Forecasting Methods

print("\n" + "=" * 60)
print("STEP 8: FORECASTING METHOD COMPARISON")
print("=" * 60)

forecast_results = []
future_forecasts = []

TEST_MONTHS = 6
MOVING_AVERAGE_WINDOW = 3
ALPHAS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]

for product_id, group in sales.groupby("Product_ID"):

    group = group.sort_values("Month").reset_index(drop=True)
    values = group["Units_Sold"].astype(float).tolist()
    dates = group["Month"].tolist()

    # Validate the monthly time series
    expected_months = pd.date_range(
        start=dates[0],
        periods=len(dates),
        freq="MS"
    )

    if len(dates) != 24 or not pd.DatetimeIndex(dates).equals(
        expected_months
    ):
        raise ValueError(
            f"{product_id}: expected 24 consecutive monthly observations."
        )

    # Split data: first 18 months for model development,
    # last 6 months for final evaluation
    train_values = values[:-TEST_MONTHS]
    test_values = values[-TEST_MONTHS:]

    # --------------------------------------------------
    # METHOD 1: MOVING AVERAGE (3 MONTHS)
    # --------------------------------------------------

    ma_predictions = []

    for i in range(len(train_values), len(values)):
        previous_values = values[i - MOVING_AVERAGE_WINDOW:i]
        prediction = sum(previous_values) / MOVING_AVERAGE_WINDOW
        ma_predictions.append(prediction)

    ma_errors = [
        actual - predicted
        for actual, predicted in zip(test_values, ma_predictions)
    ]

    ma_mad = sum(abs(error) for error in ma_errors) / len(ma_errors)

    ma_mape = (
        sum(
            abs(error) / actual * 100
            for actual, error in zip(test_values, ma_errors)
            if actual != 0
        )
        / sum(actual != 0 for actual in test_values)
        if any(actual != 0 for actual in test_values)
        else float("nan")
    )

    forecast_results.append({
        "Product_ID": product_id,
        "Method": "Moving Average (3 months)",
        "Alpha": None,
        "MAD": ma_mad,
        "MAPE_Percent": ma_mape
    })

    # --------------------------------------------------
    # METHOD 2: SIMPLE EXPONENTIAL SMOOTHING
    # Select alpha using training data only
    # --------------------------------------------------

    best_alpha = None
    best_validation_mad = float("inf")

    for alpha in ALPHAS:

        level = train_values[0]
        validation_errors = []

        # Use months 2 through 18 for one-step-ahead
        # validation, after a 3-month initialization period
        for i in range(1, len(train_values)):
            prediction = level

            if i >= MOVING_AVERAGE_WINDOW:
                validation_errors.append(
                    train_values[i] - prediction
                )

            level = (
                alpha * train_values[i]
                + (1 - alpha) * level
            )

        validation_mad = (
            sum(abs(error) for error in validation_errors)
            / len(validation_errors)
        )

        if validation_mad < best_validation_mad:
            best_validation_mad = validation_mad
            best_alpha = alpha

    # Evaluate selected alpha on the final 6 months
    level = train_values[0]
    ses_predictions = []

    for actual in train_values[1:]:
        level = best_alpha * actual + (1 - best_alpha) * level

    # Forecast each test month using only earlier actual data
    for i in range(len(train_values), len(values)):
        ses_predictions.append(level)

        level = (
            best_alpha * values[i]
            + (1 - best_alpha) * level
        )

    ses_errors = [
        actual - predicted
        for actual, predicted in zip(test_values, ses_predictions)
    ]

    ses_mad = sum(abs(error) for error in ses_errors) / len(ses_errors)

    nonzero_test_values = [
        (actual, error)
        for actual, error in zip(test_values, ses_errors)
        if actual != 0
    ]

    ses_mape = (
        sum(abs(error) / actual * 100 for actual, error in nonzero_test_values)
        / len(nonzero_test_values)
        if nonzero_test_values
        else float("nan")
    )

    forecast_results.append({
        "Product_ID": product_id,
        "Method": "Simple Exponential Smoothing",
        "Alpha": best_alpha,
        "MAD": ses_mad,
        "MAPE_Percent": ses_mape
    })

    # --------------------------------------------------
  
# FORECAST NEXT 3 MONTHS USING THE BEST EVALUATED METHOD

    # Moving Average had the lower MAD and MAPE for both products
    best_method = "Moving Average (3 months)"

    # Use the last 3 actual observations as the forecast basis
    moving_average_forecast = sum(values[-3:]) / 3

    next_month = pd.Timestamp(dates[-1]) + pd.DateOffset(months=1)

    for step in range(3):
        forecast_month = next_month + pd.DateOffset(months=step)

        future_forecasts.append({
            "Product_ID": product_id,
            "Forecast_Month": forecast_month,
            "Forecast_Units": round(moving_average_forecast, 2),
            "Method": best_method,
            "Alpha": None
        })

# --------------------------------------------------
# DISPLAY AND SAVE RESULTS
# --------------------------------------------------

comparison_df = pd.DataFrame(forecast_results)
future_forecasts_df = pd.DataFrame(future_forecasts)

print("\nForecast accuracy on the last 6 months:")
print(comparison_df.round(2).to_string(index=False))

print("\nForecast for the next 3 months:")
print(future_forecasts_df.to_string(index=False))

comparison_file = output_folder / "forecast_method_comparison.csv"
future_file = output_folder / "demand_forecast_next_3_months.csv"

comparison_df.to_csv(comparison_file, index=False)
future_forecasts_df.to_csv(future_file, index=False)

print(f"\nComparison saved to: {comparison_file}")
print(f"Future forecasts saved to: {future_file}")

print("\nForecast comparison completed successfully!")

# STEP 9: MASTER PRODUCTION SCHEDULE (MPS)

import math
import pandas as pd

print("\nSTEP 9: MASTER PRODUCTION SCHEDULE")

# 1. Load the demand forecast
forecast_file = output_folder / "demand_forecast_next_3_months.csv"
forecast_df = pd.read_csv(forecast_file)
forecast_df["Forecast_Month"] = pd.to_datetime(
    forecast_df["Forecast_Month"]
)

# 2. Load finished-goods inventory
inventory = data_tables["tblInventory"].copy()

inventory_lookup = (
    inventory.set_index("Item_ID").to_dict("index")
)

# 3. Create the production schedule
mps_rows = []

for product_id, group in forecast_df.groupby("Product_ID"):
    if product_id not in inventory_lookup:
        raise ValueError(
            f"Inventory data missing for {product_id}"
        )

    initial_stock = inventory_lookup[product_id]["Initial_Stock"]
    safety_stock = inventory_lookup[product_id]["Safety_Stock"]

    projected_inventory = initial_stock

    group = group.sort_values("Forecast_Month")

    for _, row in group.iterrows():
        # Round demand up to a whole unit
        demand = math.ceil(row["Forecast_Units"])

        beginning_inventory = projected_inventory

        # Production needed to meet demand and retain safety stock
        planned_production = max(
            0,
            demand + safety_stock - beginning_inventory
        )

        ending_inventory = (
            beginning_inventory + planned_production - demand
        )

        mps_rows.append({
            "Product_ID": product_id,
            "Month": row["Forecast_Month"],
            "Forecast_Demand": demand,
            "Beginning_Inventory": beginning_inventory,
            "Safety_Stock": safety_stock,
            "Planned_Production": planned_production,
            "Ending_Inventory": ending_inventory
        })

        # Carry inventory into the next month
        projected_inventory = ending_inventory

# 4. Display and save the MPS
mps_df = pd.DataFrame(mps_rows)
mps_df = mps_df.sort_values(
    ["Product_ID", "Month"]
).reset_index(drop=True)

print("\nMaster Production Schedule:")
print(mps_df.to_string(index=False))

output_file = output_folder / "master_production_schedule.csv"
mps_df.to_csv(output_file, index=False)

print(f"\nMPS saved to: {output_file}")
print("\nMPS completed successfully!")

# STEP 10: MATERIAL REQUIREMENTS PLANNING (MRP)

import math
import pandas as pd

print("\nSTEP 10: MATERIAL REQUIREMENTS PLANNING")

# 1. Load the MPS created in Step 9
mps_file = output_folder / "master_production_schedule.csv"
mps_df = pd.read_csv(mps_file)
mps_df["Month"] = pd.to_datetime(mps_df["Month"])

# 2. Load the BOM, inventory, and purchasing data
bom = data_tables["tblBOM"].copy()
inventory = data_tables["tblInventory"].copy()
purchasing = data_tables["tblPurchasing"].copy()

# Convert numeric columns
bom["Quantity_Per_Unit"] = pd.to_numeric(
    bom["Quantity_Per_Unit"], errors="raise"
)
inventory["Initial_Stock"] = pd.to_numeric(
    inventory["Initial_Stock"], errors="raise"
)
inventory["Safety_Stock"] = pd.to_numeric(
    inventory["Safety_Stock"], errors="raise"
)
purchasing["Unit_Cost"] = pd.to_numeric(
    purchasing["Unit_Cost"], errors="raise"
)
purchasing["Lead_Time_Weeks"] = pd.to_numeric(
    purchasing["Lead_Time_Weeks"], errors="raise"
)

# 3. Validate component data
inventory_lookup = inventory.set_index("Item_ID").to_dict("index")
purchasing_lookup = purchasing.set_index("Component_ID").to_dict("index")

for _, row in bom.iterrows():
    component_id = row["Component_ID"]

    if component_id not in inventory_lookup:
        raise ValueError(
            f"Missing inventory data for component {component_id}"
        )

    if component_id not in purchasing_lookup:
        raise ValueError(
            f"Missing purchasing data for component {component_id}"
        )

# 4. Calculate gross component requirements by month
gross_requirements = {}

for _, plan_row in mps_df.iterrows():
    product_id = plan_row["Product_ID"]
    month = plan_row["Month"]
    planned_units = int(plan_row["Planned_Production"])

    product_bom = bom[bom["Product_ID"] == product_id]

    for _, bom_row in product_bom.iterrows():
        component_id = bom_row["Component_ID"]
        quantity_per_unit = bom_row["Quantity_Per_Unit"]

        gross_qty = math.ceil(planned_units * quantity_per_unit)
        key = (component_id, month)

        gross_requirements[key] = (
            gross_requirements.get(key, 0) + gross_qty
        )

# 5. Calculate net requirements and planned orders
mrp_rows = []

components = sorted({key[0] for key in gross_requirements})
months = sorted(mps_df["Month"].unique())

# Planning settings for this historical simulation
planning_start = pd.Timestamp("2026-01-01")
evaluation_date = pd.Timestamp("2025-12-01")

for component_id in components:
    component_inventory = inventory_lookup[component_id]
    purchasing_data = purchasing_lookup[component_id]

    projected_inventory = int(component_inventory["Initial_Stock"])
    safety_stock = int(component_inventory["Safety_Stock"])
    unit_cost = float(purchasing_data["Unit_Cost"])
    lead_time_weeks = int(purchasing_data["Lead_Time_Weeks"])
    lot_rule = str(purchasing_data["Lot_Sizing_Rule"]).strip().upper()

    for month_value in months:
        month = pd.Timestamp(month_value)
        gross_qty = gross_requirements.get(
            (component_id, month), 0
        )

        beginning_inventory = projected_inventory

        # Protect safety stock after meeting gross requirements
        net_requirement = max(
            0,
            gross_qty + safety_stock - beginning_inventory
        )

        if lot_rule == "L4L":
            planned_receipt = net_requirement
        else:
            raise ValueError(
                f"Lot-sizing rule '{lot_rule}' for {component_id} "
                "is not implemented yet. This version supports L4L."
            )

        ending_inventory = (
            beginning_inventory + planned_receipt - gross_qty
        )

        
        # Calculate the required order release date
        if planned_receipt > 0:
            planned_release_date = (
                month - pd.Timedelta(weeks=lead_time_weeks)
            )
        else:
            planned_release_date = pd.NaT

        # Classify the order
        if planned_receipt == 0:
            order_status = "No order required"

        elif planned_release_date < planning_start:
            if planned_release_date < evaluation_date:
                order_status = "URGENT: release date has passed"
            else:
                order_status = "Release before planning horizon"

        else:
            order_status = "Planned order"

        # Save the MRP result
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
            "Planned_Order_Release_Date": planned_release_date,
            "Unit_Cost": unit_cost,
            "Estimated_Purchase_Cost": planned_receipt * unit_cost,
            "Order_Status": order_status
        })

        # Carry inventory into the next month
        projected_inventory = ending_inventory


# 6. Display and export the MRP
mrp_df = pd.DataFrame(mrp_rows)
mrp_df = mrp_df.sort_values(
    ["Component_ID", "Month"]
).reset_index(drop=True)

print("\nMaterial Requirements Planning:")
print(mrp_df.to_string(index=False))

output_file = output_folder / "material_requirements_plan.csv"
mrp_df.to_csv(output_file, index=False)

print(f"\nMRP saved to: {output_file}")


# Create a prioritized purchasing list
purchase_columns = [
    "Component_ID",
    "Month",
    "Net_Requirements",
    "Planned_Order_Receipt",
    "Planned_Order_Release_Date",
    "Lead_Time_Weeks",
    "Unit_Cost",
    "Estimated_Purchase_Cost",
    "Order_Status"
]

purchase_list = mrp_df[
    mrp_df["Planned_Order_Receipt"] > 0
][purchase_columns].copy()

purchase_list = purchase_list.sort_values(
    ["Planned_Order_Release_Date", "Component_ID"]
)

priority_file = output_folder / "prioritized_purchase_list.csv"
purchase_list.to_csv(priority_file, index=False)

print("\nPrioritized Purchasing List:")
print(purchase_list.to_string(index=False))
print(f"\nPriority list saved to: {priority_file}")


# 7. Summarize planned purchasing costs by month
purchase_summary = (
    mrp_df.groupby("Month", as_index=False)
    ["Estimated_Purchase_Cost"].sum()
)

print("\nEstimated Purchase Cost by Month:")
print(purchase_summary.to_string(index=False))

summary_file = output_folder / "mrp_purchase_cost_summary.csv"
purchase_summary.to_csv(summary_file, index=False)

print(f"\nPurchase summary saved to: {summary_file}")
print("\nMRP completed successfully!")

# Summarize purchasing costs by component
component_cost_summary = (
    mrp_df.groupby("Component_ID", as_index=False)
    .agg(
        Total_Units_To_Order=("Planned_Order_Receipt", "sum"),
        Total_Purchase_Cost=("Estimated_Purchase_Cost", "sum")
    )
    .sort_values("Total_Purchase_Cost", ascending=False)
)

print("\nPurchase Cost by Component:")
print(component_cost_summary.to_string(index=False))

component_cost_file = output_folder / "mrp_cost_by_component.csv"
component_cost_summary.to_csv(component_cost_file, index=False)

print(f"\nComponent cost summary saved to: {component_cost_file}")
