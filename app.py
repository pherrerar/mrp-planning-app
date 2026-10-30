
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
@st.cache_data
def load_project_data():
    return mrp_engine.load_data()

try:
    data = load_project_data()
except Exception as error:
    st.error(f"Could not load Excel data: {error}")
    st.stop()

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
            min_value=0,
            step=10,
            format="%.2f"
        )
    },
    disabled=["Product_ID", "Forecast_Month"],
    hide_index=True,
    use_container_width=True,
    key="forecast_editor"
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
        evaluation_date=str(evaluation_date)
    )

except Exception as error:
    st.error(f"Calculation error: {error}")
    st.stop()

# Compare all demand scenarios
st.header("Scenario Comparison")

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
        evaluation_date=str(evaluation_date)
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
