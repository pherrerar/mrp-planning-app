import plotly.express as px
import streamlit as st
import pandas as pd
import mrp_engine


st.set_page_config(
    page_title="MRP Planning System",
    layout="wide"
)

# ---------------------------------------------------------
# PROFESSIONAL INTERFACE STYLING
# ---------------------------------------------------------
st.markdown(
    """
    <style>
        :root {
            --navy: #17324D;
            --blue: #2F6690;
            --teal: #3A7D82;
            --ink: #243447;
            --muted: #68788A;
            --surface: #FFFFFF;
            --canvas: #F4F7FA;
            --line: #E2E8F0;
        }

        [data-testid="stAppViewContainer"] {
            background: var(--canvas);
        }

        [data-testid="stHeader"] {
            background: rgba(244, 247, 250, 0.92);
        }

        .block-container {
            max-width: 1440px;
            padding-top: 2rem;
            padding-bottom: 3rem;
        }

        h1, h2, h3 {
            color: var(--navy);
            letter-spacing: -0.025em;
        }

        h1 {
            font-weight: 700;
            font-size: 2rem;
            padding-bottom: 0.25rem;
        }

        h2, h3 {
            font-weight: 650;
        }

        [data-testid="stCaptionContainer"] {
            color: var(--muted);
        }

        [data-testid="stSidebar"] {
            background: #14283F;
            border-right: 1px solid #203B57;
        }

        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
            color: #F2F6FA;
        }

        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
            color: #B8C7D6;
        }

        [data-testid="stSidebar"] [data-testid="stRadio"] label {
            color: #E8EFF5;
        }

        [data-testid="stSidebar"] [data-testid="stSelectbox"] label,
        [data-testid="stSidebar"] [data-testid="stDateInput"] label,
        [data-testid="stSidebar"] [data-testid="stNumberInput"] label {
            color: #D7E1EA;
        }

        [data-testid="stMetric"] {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 1rem 1.1rem;
            box-shadow: 0 2px 8px rgba(20, 40, 63, 0.04);
        }

        [data-testid="stMetricLabel"] {
            color: var(--muted);
            font-weight: 600;
        }

        [data-testid="stMetricValue"] {
            color: var(--navy);
            font-weight: 700;
        }

        [data-testid="stDataFrame"],
        [data-testid="stTable"],
        [data-testid="stPlotlyChart"] {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 0.35rem;
        }

        [data-testid="stExpander"] {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 10px;
        }

        div.stButton > button,
        div.stDownloadButton > button {
            background: var(--navy);
            color: white;
            border: 1px solid var(--navy);
            border-radius: 8px;
            font-weight: 600;
            transition: background 0.15s ease, border-color 0.15s ease;
        }

        div.stButton > button:hover,
        div.stDownloadButton > button:hover {
            background: var(--blue);
            color: white;
            border-color: var(--blue);
        }

        hr {
            border-color: var(--line);
        }
    </style>
    """,
    unsafe_allow_html=True
)

# ---------------------------------------------------------
# LOAD PROJECT DATA
# ---------------------------------------------------------
def load_project_data():
    return mrp_engine.load_data()


try:
    data = load_project_data()
except Exception as error:
    st.error(f"Could not load project data: {error}")
    st.stop()


open_purchase_orders = data["open_purchase_orders"].copy()
inventory = data["tblInventory"].copy()

# ---------------------------------------------------------
# SIDEBAR: NAVIGATION AND PLANNING CONTROLS
# ---------------------------------------------------------
st.sidebar.title("MRP Planning System")
st.sidebar.caption("Production planning and purchasing decisions")
st.sidebar.divider()

page = st.sidebar.radio(
    "Navigation",
    [
        "Overview",
        "Demand Forecast",
        "Production Planning",
        "Material Requirements",
        "Purchasing",
        "Scenario & Cost Analysis",
    ],
    key="page_navigation"
)

st.sidebar.divider()
st.sidebar.header("Planning Parameters")

planning_start = st.sidebar.date_input(
    "Planning start date",
    value=pd.Timestamp("2026-01-01").date()
)

evaluation_date = st.sidebar.date_input(
    "Evaluation date",
    value=pd.Timestamp("2025-12-01").date()
)

scenario = st.sidebar.selectbox(
    "Demand scenario",
    ["Base forecast", "Demand +10%", "Demand -10%"],
    index=0
)

st.sidebar.divider()
st.sidebar.subheader("Initial Inventory")
st.sidebar.caption("Adjust initial stock and safety stock for the planning run.")


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

# ---------------------------------------------------------
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
forecast["Forecast_Month"] = pd.to_datetime(forecast["Forecast_Month"])

if "saved_forecast" not in st.session_state:
    st.session_state["saved_forecast"] = forecast[
        ["Product_ID", "Forecast_Month", "Forecast_Units"]
    ].copy()

# ---------------------------------------------------------
# FORECAST EDITOR
# ---------------------------------------------------------
if page == "Demand Forecast":
    st.title("Demand Forecast")
    st.caption("Review historical demand forecasts and adjust forecast quantities.")

    edited_forecast = st.data_editor(
        st.session_state["saved_forecast"],
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
        width="stretch",
        key="forecast_editor"
    )

    st.session_state["saved_forecast"] = edited_forecast.copy()

else:
    edited_forecast = st.session_state["saved_forecast"].copy()

edited_forecast["Forecast_Month"] = pd.to_datetime(
    edited_forecast["Forecast_Month"]
)

total_forecast_demand = edited_forecast["Forecast_Units"].sum()

# ---------------------------------------------------------
# APPLY SELECTED SCENARIO AND CALCULATE MPS / MRP
# ---------------------------------------------------------
if scenario == "Demand +10%":
    scenario_forecast = edited_forecast.copy()
    scenario_forecast["Forecast_Units"] *= 1.10
elif scenario == "Demand -10%":
    scenario_forecast = edited_forecast.copy()
    scenario_forecast["Forecast_Units"] *= 0.90
else:
    scenario_forecast = edited_forecast.copy()

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

# Purchasing alerts: planned orders whose release date has arrived
# or passed as of the selected evaluation date.
mrp["Planned_Order_Release_Date"] = pd.to_datetime(
    mrp["Planned_Order_Release_Date"],
    errors="coerce"
)

urgent_orders = mrp[
    (mrp["Planned_Order_Receipt"] > 0)
    & (mrp["Planned_Order_Release_Date"].dt.date <= evaluation_date)
].copy()

# ---------------------------------------------------------
# SHARED DATA PREPARATION
# ---------------------------------------------------------
bom_display = data["tblBOM"].copy()

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

consolidated_requirements = (
    gross_display
    .groupby(["Month", "Component"], as_index=False)
    ["Gross Requirement"]
    .sum()
)

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

monthly_purchase_cost = (
    mrp.groupby("Month", as_index=False)["Estimated_Purchase_Cost"]
    .sum()
)

monthly_purchase_cost["Month"] = pd.to_datetime(
    monthly_purchase_cost["Month"]
).dt.strftime("%b %Y")

total_purchase_cost = mrp["Estimated_Purchase_Cost"].sum()
total_products = mps["Product_ID"].nunique()
planning_months = mps["Month"].nunique()
total_components = data["tblBOM"]["Component_ID"].nunique()

open_orders_count = (
    open_purchase_orders["Status"].str.strip().str.upper() == "OPEN"
).sum()

received_orders_count = (
    open_purchase_orders["Status"].str.strip().str.upper() == "RECEIVED"
).sum()

if page == "Overview":
    st.title("Production Planning Dashboard")
    st.caption("Summary of demand, production, material requirements, and purchasing.")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Products", total_products)

    with col2:
        st.metric("Planning Horizon", f"{planning_months} Months")

    with col3:
        st.metric("Components", total_components)

    with col4:
        st.metric("Total Purchase Orders", len(open_purchase_orders))

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Planned Production",
            f"{mps['Planned_Production'].sum():,.0f} units"
        )

    with col2:
        st.metric(
            "Estimated Purchase Cost",
            f"${total_purchase_cost:,.2f}"
        )

    with col3:
        st.metric(
            "Open Purchase Orders",
            int(open_orders_count)
        )

    st.divider()
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

    st.subheader("Estimated Purchase Cost by Month")

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
        texttemplate="$%{y:,.2f}",
        hovertemplate="Month: %{x}<br>Cost: $%{y:,.2f}<extra></extra>"
    )
    cost_chart.update_yaxes(tickprefix="$", tickformat=",.0f")

    st.plotly_chart(cost_chart, width="stretch")

    st.subheader("Purchasing Alerts")

    if urgent_orders.empty:
        st.success("No purchasing alerts for the selected planning scenario.")
    else:
        st.warning(
            f"{len(urgent_orders)} planned orders have a release date "
            "on or before the evaluation date. Review them in Purchasing."
        )

    st.caption(f"Selected demand scenario: {scenario}")

# ---------------------------------------------------------
# PAGE 2: DEMAND FORECAST
# ---------------------------------------------------------
elif page == "Demand Forecast":
    st.title("Demand Forecast")
    st.caption("Review and adjust the forecast used by the planning calculations.")

    st.metric("Total Forecast Demand", f"{total_forecast_demand:,.2f}")

    st.subheader("Forecast by Product")

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

    st.info(
        "Changes made in the table are saved during this app session "
        "and are used in the MPS and MRP calculations."
    )

# ---------------------------------------------------------
# PAGE 3: PRODUCTION PLANNING
# ---------------------------------------------------------
elif page == "Production Planning":
    st.title("Production Planning")
    st.caption("Master Production Schedule (MPS)")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Products", mps["Product_ID"].nunique())

    with col2:
        st.metric(
            "Planned Production",
            f"{mps['Planned_Production'].sum():,.0f} units"
        )

    with col3:
        st.metric("Planning Periods", mps["Month"].nunique())

    st.subheader("Master Production Schedule")

    st.dataframe(
        mps,
        hide_index=True,
        width="stretch"
    )

# ---------------------------------------------------------
# PAGE 4: MATERIAL REQUIREMENTS
# ---------------------------------------------------------
elif page == "Material Requirements":

    st.title("Material Requirements")
    st.caption("Bill of Materials, gross requirements, and net requirements.")

    with st.expander("Bill of Materials (BOM)", expanded=True):
        st.write(
            "The BOM shows which components are required "
            "to manufacture each finished product."
        )
        st.dataframe(
            bom_display,
            hide_index=True,
            width="stretch"
        )

    with st.expander("Gross Requirements Breakdown", expanded=False):
        st.dataframe(
            gross_display.style.format({
                "Planned Production": "{:,.0f}",
                "Qty per Unit": "{:,.0f}",
                "Gross Requirement": "{:,.0f}"
            }),
            hide_index=True,
            width="stretch"
        )

    st.subheader("Consolidated Component Requirements")

    st.dataframe(
        consolidated_requirements.style.format({
            "Gross Requirement": "{:,.0f}"
        }),
        hide_index=True,
        width="stretch"
    )

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

    st.plotly_chart(component_chart, width="stretch")

    st.divider()
    st.subheader("Net Requirements Breakdown")

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
    st.subheader("Material Requirements Plan (MRP)")
    st.dataframe(
        mrp.style.format({
            "Estimated_Purchase_Cost": "${:,.2f}"
        }),
        hide_index=True,
        width="stretch"
    )

    st.download_button(
        "Download MRP (CSV)",
        data=mrp.to_csv(index=False).encode("utf-8"),
        file_name="material_requirements_plan.csv",
        mime="text/csv"
    )

# ---------------------------------------------------------
# PAGE 5: PURCHASING
# ---------------------------------------------------------
elif page == "Purchasing":
    st.title("Purchasing")
    st.caption("Open purchase orders, purchasing recommendations, and alerts.")

    st.subheader("Purchase Order Status")

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Open Purchase Orders", int(open_orders_count))

    with col2:
        st.metric("Received Purchase Orders", int(received_orders_count))

    st.dataframe(
        open_purchase_orders,
        hide_index=True,
        width="stretch"
    )

    st.divider()
    st.subheader("Purchase Recommendations")

    st.dataframe(
        purchase_display.style.format({
            "Recommended Order Quantity": "{:,.0f}",
            "Estimated Cost": "${:,.2f}"
        }),
        hide_index=True,
        width="stretch"
    )

    st.divider()
    st.subheader("Purchasing Alerts")

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
            width="stretch"
        )
        
        st.download_button(
            "Download Purchasing Alerts (CSV)",
            data=urgent_orders.to_csv(index=False).encode("utf-8"),
            file_name="purchasing_alerts.csv",
            mime="text/csv"
        )

    st.divider()
    st.subheader("Purchase Recommendations Download")

    st.download_button(
        "Download Purchase Recommendations (CSV)",
        data=purchase_display.to_csv(index=False).encode("utf-8"),
        file_name="purchase_recommendations.csv",
        mime="text/csv"
    )

# ---------------------------------------------------------
# PAGE 6: SCENARIO AND COST ANALYSIS
# ---------------------------------------------------------
elif page == "Scenario & Cost Analysis":
    st.title("Scenario & Cost Analysis")
    st.caption("Compare demand scenarios and review estimated purchasing costs.")

    st.subheader("Scenario Comparison")

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
        width="stretch"
    )

    scenario_cost_chart = px.bar(
        comparison,
        x="Scenario",
        y="Estimated Purchase Cost",
        title="Estimated Purchase Cost by Demand Scenario",
        labels={
            "Scenario": "Demand Scenario",
            "Estimated Purchase Cost": "Estimated Cost ($)"
        },
        text_auto=",.2f"
    )
    scenario_cost_chart.update_traces(
        texttemplate="$%{y:,.2f}",
        textposition="outside",
        hovertemplate="Scenario: %{x}<br>Cost: $%{y:,.2f}<extra></extra>"
    )
    scenario_cost_chart.update_yaxes(tickprefix="$", tickformat=",.0f")

    st.plotly_chart(scenario_cost_chart, width="stretch")

    st.divider()
    st.subheader("Estimated Purchase Cost by Month")

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
        texttemplate="$%{y:,.2f}",
        hovertemplate="Month: %{x}<br>Cost: $%{y:,.2f}<extra></extra>"
    )
    cost_chart.update_yaxes(tickprefix="$", tickformat=",.0f")

    st.plotly_chart(cost_chart, width="stretch")

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
        texttemplate="$%{y:,.2f}",
        hovertemplate="Component: %{x}<br>Cost: $%{y:,.2f}<extra></extra>"
    )
    component_cost_chart.update_yaxes(tickprefix="$", tickformat=",.0f")

    st.plotly_chart(component_cost_chart, width="stretch")

    st.metric("Total Estimated Purchase Cost", f"${total_purchase_cost:,.2f}")

# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
st.sidebar.caption(
    "Planning estimates only. Verify supplier lead times, open purchase orders, "
    "and production constraints before using results for actual purchasing decisions."
)