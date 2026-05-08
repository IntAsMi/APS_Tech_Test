import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==========================================
# 1. PAGE CONFIGURATION
# ==========================================
st.set_page_config(page_title="Transactions BI Dashboard", layout="wide", page_icon="📊")
st.title("📊 Transaction Metrics Dashboard")

# ==========================================
# 2. DATA EXTRACTION & TRANSFORMATION
# ==========================================
@st.cache_data
def load_and_transform_data():
    try:
        # Load Oracle Data
        transactions, accounts, profile_groups = [df.set_axis(df.columns.str.lower().str.replace(' ', '_'), axis=1) for df in pd.read_excel('Oracle.xlsx', sheet_name=None).values()]
        # Load SQL Server Data
        banking_customers, physical_customers, corporate_customers =  [df.set_axis(df.columns.str.lower().str.replace(' ', '_'), axis=1) for df in pd.read_excel('SQLServer.xlsx', sheet_name=None).values()]
    except FileNotFoundError:
        st.error("Error: Could not find 'Oracle.xlsx' or 'SQLServer.xlsx'.")
        st.stop()

    # Normalize Customers
    physical_customers['customer_name'] = physical_customers['customer_firstname'] + ' ' + physical_customers['customer_lastname']
    physical_customers['customer_type'] = 'Physical'
    corporate_customers['customer_name'] = corporate_customers['company_title']
    corporate_customers['customer_type'] = 'Corporate'
    
    all_customers = pd.concat([
        physical_customers[['customer_pk', 'customer_name', 'customer_type']],
        corporate_customers[['customer_pk', 'customer_name', 'customer_type']]
    ])
    customers_df = pd.merge(banking_customers, all_customers, on='customer_pk', how='left')

    # Merge Oracle Data
    accounts_profiles = pd.merge(accounts, profile_groups, on='customer_group_id', how='left')
    oracle_df = pd.merge(transactions, accounts_profiles, left_on='transaction_account_number', right_on='account_number', how='left')

    # Final Join
    master_df = pd.merge(oracle_df, customers_df, left_on='profile_number', right_on='customer_profile', how='left')
    master_df['transaction_date'] = pd.to_datetime(master_df['transaction_date'])
    
    return master_df

df = load_and_transform_data()

# ==========================================
# 3. SIDEBAR FILTERS (Start and End Date)
# ==========================================
st.sidebar.header("Date Filters")
min_date = df['transaction_date'].min().date()
max_date = df['transaction_date'].max().date()

dates_selection = st.sidebar.date_input("Select Date Range",
    [min_date, max_date],
    key="date_range_1"
)

if dates_selection.__len__()>1 and not ((min_date, max_date) == dates_selection):
    start_date, end_date = dates_selection
    dates_selection_idx = True
else:
    start_date, end_date = min_date, max_date
    dates_selection_idx = False

# Apply Filters
mask = (df['transaction_date'].dt.date >= start_date) & (df['transaction_date'].dt.date <= end_date)
filtered_df = df.loc[mask].copy()

# Prepare Monthly Data for Averages and Trends
filtered_df['month_year'] = filtered_df['transaction_date'].dt.to_period('M').dt.to_timestamp()
monthly_df = filtered_df.groupby('month_year').agg(
    total_value=('transaction_amount', 'sum'),
    transaction_count=('transaction_number', 'count')
).reset_index()

# ==========================================
# 4. KEY PERFORMANCE INDICATORS (Averages)
# ==========================================
st.markdown("### 📈 Key Metrics")

# Calculate Monthly Averages
avg_monthly_value = monthly_df['total_value'].mean() if not monthly_df.empty else 0
avg_monthly_count = monthly_df['transaction_count'].mean() if not monthly_df.empty else 0

col1, col2 = st.columns(2)
col1.metric("Avg. Monthly Transaction Value", f"${avg_monthly_value:,.2f}")
col2.metric("Avg. Monthly Transaction Count", f"{int(avg_monthly_count):,}")

st.divider()

# ==========================================
# 5. VISUALIZATIONS
# ==========================================

# Create subplots with secondary y-axis
fig_time = make_subplots(specs=[[{"secondary_y": True}]])

if dates_selection_idx:
    monthly_df = filtered_df.groupby('transaction_date').agg(
        total_value=('transaction_amount', 'sum'),
        transaction_count=('transaction_number', 'count')
    ).reset_index()
    
    # Add Value Trace (Left Y-Axis)
    fig_time.add_trace(
        go.Scatter(
            x=monthly_df['transaction_date'], 
            y=monthly_df['total_value'], 
            name="Value of Transactions ($)", 
            mode='lines+markers',
            line=dict(color='#1f77b4', width=3),
            marker=dict(size=8)
        ),
        secondary_y=False,
    )

    # Add Count Trace (Right Y-Axis)
    fig_time.add_trace(
        go.Bar(
            x=monthly_df['transaction_date'], 
            y=monthly_df['transaction_count'], 
            name="Number of Transactions", 
            marker_color='#ff7f0e',
            opacity=0.4
        ),
        secondary_y=True,
    )
else:

    # Add Value Trace (Left Y-Axis)
    fig_time.add_trace(
        go.Scatter(
            x=monthly_df['month_year'], 
            y=monthly_df['total_value'], 
            name="Value of Transactions ($)", 
            mode='lines+markers',
            line=dict(color='#1f77b4', width=3),
            marker=dict(size=8)
        ),
        secondary_y=False,
    )

    # Add Count Trace (Right Y-Axis)
    fig_time.add_trace(
        go.Bar(
            x=monthly_df['month_year'], 
            y=monthly_df['transaction_count'], 
            name="Number of Transactions", 
            marker_color='#ff7f0e',
            opacity=0.4
        ),
        secondary_y=True,
    )

# Refine Layout
fig_time.update_layout(
    height=450,
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
fig_time.update_yaxes(title_text="<b>Value</b> ($)", secondary_y=False, color="#1f77b4")
fig_time.update_yaxes(title_text="<b>Number</b> of Transactions", secondary_y=True, color="#d62728", showgrid=False)

st.plotly_chart(fig_time, width='stretch')

st.divider()

# --- ADDITIONAL VISUALIZATIONS ---
col_chart1, col_chart2 = st.columns([1,2])

# Chart: Customer Type Distribution
with col_chart1:
    st.markdown("#### Volume by Customer Type")
    cust_df = filtered_df.groupby('customer_type')['transaction_amount'].sum().reset_index()
    fig_cust = px.pie(
        cust_df, 
        names='customer_type', 
        values='transaction_amount',
        hole=0.4,
        color_discrete_sequence=px.colors.sequential.Teal
    )
    st.plotly_chart(fig_cust, width='stretch')


# --- 5b. Top 3 Customers ---
with col_chart2:
    st.markdown("### Top 3 Customers by Transaction Value")
    top_3_cust = filtered_df.groupby('customer_name')['transaction_amount'].sum().nlargest(3).reset_index()

    fig_top3 = px.bar(
        top_3_cust, 
        x='transaction_amount', 
        y='customer_name', 
        orientation='h',
        labels={'transaction_amount': 'Total Volume', 'customer_name': ''},
        color='transaction_amount',
        color_continuous_scale='Blues'
    )
    fig_top3.update_layout(yaxis={'categoryorder':'total ascending', 'type': 'category'}, 
                           showlegend=False, 
                           coloraxis_showscale=False)
    st.plotly_chart(fig_top3, width='stretch')
    

st.divider()

st.markdown("### 📋 Detailed Transaction Records")
st.dataframe(
    filtered_df[[
        'transaction_number', 'transaction_date', 'customer_name', 'customer_type', 
        'account_number', 'product_code', 'debit_credit', 'transaction_amount'
    ]].sort_values(by='transaction_date', ascending=False),
    width='stretch'
)