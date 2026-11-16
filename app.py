import plotly.express as px
import streamlit as st
import pandas as pd
import mrp_engine

st.set_page_config(
    page_title="MRP Planning System",
    page_icon="🏭",
    layout="wide"
)

st.title("🏭 Material Requirements Planning")
st.caption("Production planning, inventory control, and purchasing decisions")

# Load Excel data
def load_project_data():
    return mrp_engine.load_data()

try:
    data = load_project_data()
except Exception as error:
    st.error(f"Could not load Excel data: {error}")
    st.stop()

# Open purchase orders
open_purchase_orders = data["open_purchase_orders"].copy()
st.write("DEBUG - PO columns:", open_purchase_orders.columns.tolist())
st.write("DEBUG - PO file path:", mrp_engine.OPEN_PO_FILE)
st.header("Open Purchase Orders")

st.write(
    "Purchase orders already placed with suppliers "
    "that are waiting to be received."
)

st.dataframe(
    open_purchase_orders,
    hide_index=True,
    use_container_width=True
)

open_orders_count = (
    open_purchase_orders["Status"].str.strip().str.upper() == "OPEN"
).sum()

received_orders_count = (
    open_purchase_orders["Status"].str.strip().str.upper() == "RECEIVED"
).sum()

col1, col2 = st.columns(2)

with col1:
    st.metric("Open Purchase Orders", int(open_orders_count))

with col2:
    st.metric("Received Purchase Orders", int(received_orders_count))

# Sidebar controls
st.sidebar.header("Planning Parameters")

planning_start = st.sidebar.date_input(
    "Planning start date",
    value=pd.Timestamp("2026-01-01").date()
)

evaluation_date = st.sidebar.date_input(
    "Evaluation date",
    value=pd.Timestamp("2025-12-01").date()
)

st.sidebar.divider()
st.sidebar.subheader("Initial Inventory")

inventory = data["tblInventory"].copy()

# Allow the user to modify starting inventory and safety stock
for index, row in inventory.iterrows():
    item = row["Item_ID"]

    inventory.loc[index, "Initial_Stock"] = st.sidebar.number_input(
        f"{item} initial stock",
        min_value=0,
        value=int(row["Initial_Stock"]),
        step=10,
        key=f"initial_{item}"
    )

    inventory.loc[index, "Safety_Stock"] = st.sidebar.number_input(
        f"{item} safety stock",
        min_value=0,
        value=int(row["Safety_Stock"]),
        step=5,
        key=f"safety_{item}"
    )

# Load existing demand forecast
forecast_path = (
    mrp_engine.PROJECT_FOLDER
    / "outputs"
    / "demand_forecast_next_3_months.csv"
)

if not forecast_path.exists():
    st.error(
        "Forecast file not found. "
        "Expected: outputs/demand_forecast_next_3_months.csv"
    )
    st.stop()

forecast = pd.read_csv(forecast_path)
forecast["Forecast_Units"] = forecast["Forecast_Units"].round(2)
forecast["Forecast_Month"] = pd.to_datetime(
    forecast["Forecast_Month"]
)

st.header("1. Demand Forecast")
st.write(
    "Adjust the forecast quantities to test different demand scenarios."
)

edited_forecast = st.data_editor(
    forecast[["Product_ID", "Forecast_Month", "Forecast_Units"]],
    column_config={
        "Product_ID": st.column_config.TextColumn(
            "Product",
            disabled=True
        ),
        "Forecast_Month": st.column_config.DateColumn(
            "Forecast Month",
            disabled=True
        ),
        "Forecast_Units": st.column_config.NumberColumn(
    "Forecast Units",
    min_value=0.00,
    step=0.01,
    format="localized"
)
    },
    disabled=["Product_ID", "Forecast_Month"],
    hide_index=True,
    use_container_width=True,
    key="forecast_editor"
)
# Display total forecast demand
total_forecast_demand = edited_forecast["Forecast_Units"].sum()

st.metric(
    "Total Forecast Demand",
    f"{total_forecast_demand:,.2f}"
)

# Demand scenario analysis
st.header("Demand Scenario Analysis")

scenario = st.selectbox(
    "Select a demand scenario",
    [
        "Base forecast",
        "Demand +10%",
        "Demand -10%"
    ]
)

if scenario == "Demand +10%":
    scenario_forecast = edited_forecast.copy()
    scenario_forecast["Forecast_Units"] *= 1.10

elif scenario == "Demand -10%":
    scenario_forecast = edited_forecast.copy()
    scenario_forecast["Forecast_Units"] *= 0.90

else:
    scenario_forecast = edited_forecast.copy()

st.write(f"Selected scenario: **{scenario}**")


# Calculate MPS and MRP
try:
    mps = mrp_engine.build_mps(
        scenario_forecast,
        inventory
    )

    mrp = mrp_engine.build_mrp(
        mps,
        data["tblBOM"],
        inventory,
        data["tblPurchasing"],
        planning_start=str(planning_start),
        evaluation_date=str(evaluation_date),
        open_purchase_orders_df=open_purchase_orders
    )

except Exception as error:
    st.error(f"Calculation error: {error}")
    st.stop()

# Main Dashboard
st.header("Production Planning Dashboard")

# KPI calculations
total_forecast = edited_forecast["Forecast_Units"].sum()

total_products = mps["Product_ID"].nunique()

planning_months = mps["Month"].nunique()

total_components = data["tblBOM"]["Component_ID"].nunique()

# KPI layout
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Total Forecast Demand",
        f"{total_forecast:,.2f}"
    )

with col2:
    st.metric(
        "Products",
        total_products
    )

with col3:
    st.metric(
        "Planning Horizon",
        f"{planning_months} Months"
    )

with col4:
    st.metric("Components", total_components)

# Total Estimated Purchase Cost
total_purchase_cost = mrp["Estimated_Purchase_Cost"].sum()

st.metric(
    "Total Estimated Purchase Cost",
    f"${total_purchase_cost:,.2f}"
)
# Monthly Purchase Cost Chart
st.subheader("Estimated Purchase Cost by Month")

monthly_purchase_cost = (
    mrp.groupby("Month", as_index=False)["Estimated_Purchase_Cost"]
    .sum()
)

cost_chart = px.bar(
    monthly_purchase_cost,
    x="Month",
    y="Estimated_Purchase_Cost",
    title="Monthly Estimated Purchase Cost",
    labels={
        "Month": "Month",
        "Estimated_Purchase_Cost": "Estimated Cost ($)"
    },
    text_auto=",.2f"
)

cost_chart.update_traces(
    textposition="outside",
    hovertemplate="Month: %{x}<br>Cost: $%{y:,.2f}<extra></extra>"
)

st.plotly_chart(cost_chart, use_container_width=True)
st.divider()
# Demand Forecast Chart
st.subheader("Demand Forecast by Product")

forecast_chart = edited_forecast.copy()

forecast_chart["Forecast_Month"] = (
    forecast_chart["Forecast_Month"].dt.strftime("%b %Y")
)

forecast_pivot = forecast_chart.pivot(
    index="Forecast_Month",
    columns="Product_ID",
    values="Forecast_Units"
)

st.bar_chart(
    forecast_pivot,
    y_label="Forecast Units",
    x_label="Month"
)
# Bill of Materials
with st.expander("3. Bill of Materials", expanded=False):

    st.write(
        "The BOM shows which components are required "
        "to manufacture each finished product."
    )

    bom_display = data["tblBOM"].copy()

    st.dataframe(
        bom_display,
        hide_index=True,
        width="stretch"
    )
# Gross Requirements Breakdown
with st.expander("4. Gross Requirements Breakdown", expanded=False):

    gross_requirements = mps.merge(
        bom_display,
        on="Product_ID",
        how="left"
    )

    gross_requirements["Gross_Requirement"] = (
        gross_requirements["Planned_Production"]
        * gross_requirements["Quantity_Per_Unit"]
    )

    gross_display = gross_requirements[
        [
            "Product_ID",
            "Month",
            "Component_ID",
            "Planned_Production",
            "Quantity_Per_Unit",
            "Gross_Requirement"
        ]
    ].copy()

    gross_display = gross_display.rename(columns={
        "Product_ID": "Product",
        "Month": "Month",
        "Component_ID": "Component",
        "Planned_Production": "Planned Production",
        "Quantity_Per_Unit": "Qty per Unit",
        "Gross_Requirement": "Gross Requirement"
    })

    st.dataframe(
        gross_display.style.format({
            "Planned Production": "{:,.0f}",
            "Qty per Unit": "{:,.0f}",
            "Gross Requirement": "{:,.0f}"
        }),
        hide_index=True,
        width="stretch"
    )
# Consolidated Component Requirements
with st.expander("5. Consolidated Component Requirements", expanded=False):

    consolidated_requirements = (
        gross_display
        .groupby(["Month", "Component"], as_index=False)
        ["Gross Requirement"]
        .sum()
    )

    st.dataframe(
        consolidated_requirements.style.format({
            "Gross Requirement": "{:,.0f}"
        }),
        hide_index=True,
        width="stretch"
    )

    # Component Requirements Chart
st.subheader("Gross Requirements by Component")

component_chart = px.bar(
    consolidated_requirements,
    x="Component",
    y="Gross Requirement",
    color="Month",
    barmode="group",
    title="Monthly Component Requirements",
    labels={
        "Component": "Component",
        "Gross Requirement": "Required Units",
        "Month": "Month"
    },
    text_auto=True
)

st.plotly_chart(
    component_chart,
    use_container_width=True
)
# Net Requirements Breakdown
with st.expander("6. Net Requirements Breakdown", expanded=False):

    net_display = mrp[
        [
            "Component_ID",
            "Month",
            "Gross_Requirements",
            "Safety_Stock",
            "Beginning_Inventory",
            "Open_PO_Receipts",
            "Net_Requirements"
        ]
    ].copy()

    net_display = net_display.rename(columns={
        "Component_ID": "Component",
        "Month": "Month",
        "Gross_Requirements": "Gross Requirements",
        "Safety_Stock": "Safety Stock",
        "Beginning_Inventory": "Beginning Inventory",
        "Open_PO_Receipts": "Open PO Receipts",
        "Net_Requirements": "Net Requirements"
    })

    st.dataframe(
        net_display.style.format({
            "Gross Requirements": "{:,.0f}",
            "Safety Stock": "{:,.0f}",
            "Beginning Inventory": "{:,.0f}",
            "Open PO Receipts": "{:,.0f}",
            "Net Requirements": "{:,.0f}"
        }),
        hide_index=True,
        width="stretch"
    )

    # Net Requirements Chart
    st.subheader("Net Requirements by Component")

    net_chart = px.bar(
        net_display,
        x="Component",
        y="Net Requirements",
        color="Month",
        barmode="group",
        title="Monthly Net Component Requirements",
        labels={
            "Component": "Component",
            "Net Requirements": "Required Units",
            "Month": "Month"
        },
        text_auto=True
    )

    st.plotly_chart(
        net_chart,
        use_container_width=True
    )
# Purchase Recommendations
with st.expander("7. Purchase Recommendations", expanded=False):

    purchase_display = mrp[
        [
            "Component_ID",
            "Month",
            "Planned_Order_Receipt",
            "Planned_Order_Release_Date",
            "Estimated_Purchase_Cost",
            "Order_Status"
        ]
    ].copy()

    purchase_display = purchase_display.rename(columns={
        "Component_ID": "Component",
        "Month": "Required Month",
        "Planned_Order_Receipt": "Recommended Order Quantity",
        "Planned_Order_Release_Date": "Order Release Date",
        "Estimated_Purchase_Cost": "Estimated Cost",
        "Order_Status": "Status"
    })

    st.dataframe(
        purchase_display.style.format({
            "Recommended Order Quantity": "{:,.0f}",
            "Estimated Cost": "${:,.2f}"
        }),
        hide_index=True,
        width="stretch"
    )
        # Purchase Cost by Component
    st.subheader("Purchase Cost by Component")

    component_purchase_cost = (
        mrp.groupby("Component_ID", as_index=False)["Estimated_Purchase_Cost"]
        .sum()
        .sort_values("Estimated_Purchase_Cost", ascending=False)
    )

    component_cost_chart = px.bar(
        component_purchase_cost,
        x="Component_ID",
        y="Estimated_Purchase_Cost",
        title="Total Purchase Cost by Component",
        labels={
            "Component_ID": "Component",
            "Estimated_Purchase_Cost": "Estimated Cost ($)"
        },
        text_auto=",.2f"
    )

    component_cost_chart.update_traces(
        textposition="outside",
        hovertemplate="Component: %{x}<br>Cost: $%{y:,.2f}<extra></extra>"
    )

    st.plotly_chart(
        component_cost_chart,
        use_container_width=True
    )
# Compare all demand scenarios
st.header("Scenario Comparison")
st.caption(
    "Forecast Demand represents the integer demand used for MPS "
    "planning. Each monthly forecast is rounded up to a whole unit."
)
scenario_results = []

scenarios = {
    "Demand -10%": 0.90,
    "Base forecast": 1.00,
    "Demand +10%": 1.10
}

for scenario_name, multiplier in scenarios.items():
    test_forecast = edited_forecast.copy()
    test_forecast["Forecast_Units"] *= multiplier

    test_mps = mrp_engine.build_mps(
        test_forecast,
        inventory
    )

    
    test_mrp = mrp_engine.build_mrp(
        test_mps,
        data["tblBOM"],
        inventory,
        data["tblPurchasing"],
        planning_start=str(planning_start),
        evaluation_date=str(evaluation_date),
        open_purchase_orders_df=open_purchase_orders
    )


    scenario_results.append({
        "Scenario": scenario_name,
        "Forecast Demand": test_mps["Forecast_Demand"].sum(),
        "Planned Production": test_mps["Planned_Production"].sum(),
        "Estimated Purchase Cost": test_mrp[
            "Estimated_Purchase_Cost"
        ].sum()
    })

comparison = pd.DataFrame(scenario_results)

base_cost = comparison.loc[
    comparison["Scenario"] == "Base forecast",
    "Estimated Purchase Cost"
].iloc[0]

comparison["Cost Difference vs. Base"] = (
    comparison["Estimated Purchase Cost"] - base_cost
)

st.dataframe(
    comparison.style.format({
        "Forecast Demand": "{:,.0f}",
        "Planned Production": "{:,.0f}",
        "Estimated Purchase Cost": "${:,.2f}",
        "Cost Difference vs. Base": "${:+,.2f}"
    }),
    hide_index=True,
    use_container_width=True
)

st.bar_chart(
    comparison,
    x="Scenario",
    y="Estimated Purchase Cost"
)

# MPS section
st.header("2. Master Production Schedule (MPS)")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Products", mps["Product_ID"].nunique())

with col2:
    st.metric("Planned Production", f"{mps['Planned_Production'].sum():,.0f} units")

with col3:
    st.metric("Planning Periods", mps["Month"].nunique())

st.dataframe(
    mps,
    hide_index=True,
    use_container_width=True
)

# Purchasing alerts
st.header("Purchasing Alerts")

urgent_orders = mrp[
    mrp["Order_Status"] != "Planned order"
].copy()

if urgent_orders.empty:
    st.success("No purchasing alerts for the selected planning scenario.")
else:
    st.warning(
        f"{len(urgent_orders)} material planning records need attention."
    )

    urgent_orders["Planned_Order_Release_Date"] = pd.to_datetime(
        urgent_orders["Planned_Order_Release_Date"]
    )

    urgent_orders = urgent_orders.sort_values(
        "Planned_Order_Release_Date"
    )

    st.dataframe(
        urgent_orders[
            [
                "Component_ID",
                "Month",
                "Net_Requirements",
                "Lead_Time_Weeks",
                "Planned_Order_Release_Date",
                "Estimated_Purchase_Cost",
                "Order_Status"
            ]
        ],
        hide_index=True,
        use_container_width=True
    )

    st.download_button(
        "Download Purchasing Alerts (CSV)",
        data=urgent_orders.to_csv(index=False).encode("utf-8"),
        file_name="purchasing_alerts.csv",
        mime="text/csv"
    )

# MRP section
st.header("3. Material Requirements Plan (MRP)")

total_cost = mrp["Estimated_Purchase_Cost"].sum()
total_components = mrp["Component_ID"].nunique()

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Components", total_components)

with col2:
    st.metric("Planned Purchase Cost", f"${total_cost:,.2f}")

with col3:
    orders_to_review = (
        mrp["Order_Status"] != "Planned order"
    ).sum()
    st.metric("Orders to Review", int(orders_to_review))

st.subheader("Material Requirements")
st.dataframe(
    mrp,
    hide_index=True,
    use_container_width=True
)

# Purchasing summary
st.subheader("Purchase Cost by Month")

monthly_cost = (
    mrp.groupby("Month", as_index=False)
    ["Estimated_Purchase_Cost"]
    .sum()
)

monthly_cost["Month"] = pd.to_datetime(
    monthly_cost["Month"]
).dt.strftime("%b %Y")

st.bar_chart(
    monthly_cost,
    x="Month",
    y="Estimated_Purchase_Cost"
)

# Downloads
st.header("4. Download Results")

col1, col2 = st.columns(2)

with col1:
    st.download_button(
        "Download MPS (CSV)",
        data=mps.to_csv(index=False).encode("utf-8"),
        file_name="master_production_schedule.csv",
        mime="text/csv"
    )

with col2:
    st.download_button(
        "Download MRP (CSV)",
        data=mrp.to_csv(index=False).encode("utf-8"),
        file_name="material_requirements_plan.csv",
        mime="text/csv"
    )

st.caption(
    "Planning estimates only. Verify supplier lead times, "
    "open purchase orders, and production constraints before "
    "using results for actual purchasing decisions."
)
