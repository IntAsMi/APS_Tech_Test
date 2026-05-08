import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==========================================
# 1. PAGE CONFIGURATION
# ==========================================
st.set_page_config(page_title="Transactions BI Dashboard", layout="wide", page_icon="📊")
st.title("📊 Demo: Business Intelligence Transactions Dashboard")

# ==========================================
# 2. DATA EXTRACTION & TRANSFORMATION
# ==========================================
@st.cache_data
def load_and_transform_data():
    """
    Reads the Oracle and SQLServer Excel files, normalizes the data, 
    and merges them into a single comprehensive BI dataset.
    """
    try:
        # Load Oracle Data
        transactions, accounts, profile_groups = [df.set_axis(df.columns.str.lower().str.replace(' ', '_'), axis=1) for df in pd.read_excel('Oracle.xlsx', sheet_name=None).values()]
        
        # Load SQL Server Data
        banking_customers, physical_customers, corporate_customers =  [df.set_axis(df.columns.str.lower().str.replace(' ', '_'), axis=1) for df in pd.read_excel('SQLServer.xlsx', sheet_name=None).values()]
    
    except FileNotFoundError:
        st.error("Error: Could not find 'Oracle.xlsx' or 'SQLServer.xlsx'. Please ensure they are in the same directory.")
        st.stop()

    # --- Transform SQL Server Customers ---
    # Standardize physical customers
    physical_customers['customer_name'] = physical_customers['customer_firstname'] + ' ' + physical_customers['customer_lastname']
    physical_customers['customer_type'] = 'Physical'
    
    # Standardize corporate customers
    corporate_customers['customer_name'] = corporate_customers['company_title']
    corporate_customers['customer_type'] = 'Corporate'
    
    # Combine all customer details
    all_customers = pd.concat([
        physical_customers[['customer_pk', 'customer_name', 'customer_type']],
        corporate_customers[['customer_pk', 'customer_name', 'customer_type']]
    ])
    
    # Merge with Banking Customers link table
    customers_df = pd.merge(banking_customers, all_customers, on='customer_pk', how='left')

    # --- Transform Oracle Data ---
    # Merge Accounts with Profile Groups
    accounts_profiles = pd.merge(accounts, profile_groups, on='customer_group_id', how='left')
    
    # Merge Transactions with Account Profiles
    oracle_df = pd.merge(transactions, accounts_profiles, left_on='transaction_account_number', right_on='account_number', how='left')

    # --- Final Data Integration ---
    # Join Oracle merged data with SQL Server customer data
    master_df = pd.merge(oracle_df, customers_df, left_on='profile_number', right_on='customer_profile', how='left')

    # --- Feature Engineering ---
    # Convert dates to datetime objects
    master_df['transaction_date'] = pd.to_datetime(master_df['transaction_date'])
    
    # Calculate Real Financial Impact (Deposits = Positive, Withdrawals = Negative)
    master_df['actual_amount'] = master_df.apply(
        lambda row: row['transaction_amount'] if row['debit_credit'] == 'C' else -row['transaction_amount'], 
        axis=1
    )
    
    return master_df

# Load the data
df = load_and_transform_data()

# ==========================================
# 3. SIDEBAR FILTERS
# ==========================================
st.sidebar.header("Dashboard Filters")

# Date Filter
min_date = df['transaction_date'].min().date()
max_date = df['transaction_date'].max().date()

try:
    start_date, end_date = st.sidebar.date_input("Date Range", [min_date, max_date])
except ValueError:
    st.sidebar.error("Please select a valid date range.")
    st.stop()

# Customer Type Filter
customer_types = df['customer_type'].dropna().unique().tolist()
selected_types = st.sidebar.multiselect("Customer Type", customer_types, default=customer_types)

# Product Code Filter
product_codes = df['product_code'].dropna().unique().tolist()
selected_products = st.sidebar.multiselect("Product Code", product_codes, default=product_codes)

# Apply Filters
mask = (
    (df['transaction_date'].dt.date >= start_date) & 
    (df['transaction_date'].dt.date <= end_date) &
    (df['customer_type'].isin(selected_types)) &
    (df['product_code'].isin(selected_products))
)
filtered_df = df.loc[mask].copy()

# ==========================================
# 4. KEY PERFORMANCE INDICATORS (KPIs)
# ==========================================
st.markdown("### 📈 Key Performance Indicators")

total_transactions = len(filtered_df)
total_volume = filtered_df['transaction_amount'].sum()
total_deposits = filtered_df[filtered_df['debit_credit'] == 'C']['transaction_amount'].sum()
total_withdrawals = filtered_df[filtered_df['debit_credit'] == 'D']['transaction_amount'].sum()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Transactions", f"{total_transactions:,}")
col2.metric("Total Volume ($)", f"${total_volume:,.2f}")
col3.metric("Total Deposits (C)", f"${total_deposits:,.2f}")
col4.metric("Total Withdrawals (D)", f"${total_withdrawals:,.2f}")

st.divider()

# ==========================================
# 5. VISUALIZATIONS
# ==========================================

# --- COMBINED DUAL-AXIS TIME SERIES CHART ---
st.markdown("### Monthly Transaction Trends: Value vs. Volume")

# Group data by Month
filtered_df['month_year'] = filtered_df['transaction_date'].dt.to_period('M').dt.to_timestamp()
monthly_df = filtered_df.groupby('month_year').agg(
    total_value=('transaction_amount', 'sum'),
    transaction_count=('transaction_number', 'count')
).reset_index()

# Create subplots with secondary y-axis
fig_time = make_subplots(specs=[[{"secondary_y": True}]])

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

st.plotly_chart(fig_time, use_container_width=True)

st.divider()

# --- ADDITIONAL VISUALIZATIONS ---
col_chart1, col_chart2, col_chart3 = st.columns(3)

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
    st.plotly_chart(fig_cust, use_container_width=True)

# Chart: Top Customers by Volume
with col_chart2:
    st.markdown("#### Top 10 Customers")
    top_cust = filtered_df.groupby('customer_name')['transaction_amount'].sum().nlargest(10).reset_index()
    fig_top = px.bar(
        top_cust, 
        x='transaction_amount', 
        y='customer_name', 
        orientation='h',
        labels={'transaction_amount': 'Total Volume', 'customer_name': ''},
        color='transaction_amount',
        color_continuous_scale='Blues'
    )
    fig_top.update_layout(yaxis={'categoryorder':'total ascending'}, coloraxis_showscale=False)
    st.plotly_chart(fig_top, use_container_width=True)

# Chart: Volume by Product Code
with col_chart3:
    st.markdown("#### Volume by Product Code")
    prod_df = filtered_df.groupby('product_code')['transaction_amount'].sum().reset_index()
    fig_prod = px.bar(
        prod_df, 
        x='product_code', 
        y='transaction_amount',
        labels={'product_code': 'Product', 'transaction_amount': 'Total Volume'},
        color='product_code'
    )
    fig_prod.update_layout(showlegend=False)
    st.plotly_chart(fig_prod, use_container_width=True)

st.divider()

# ==========================================
# 6. DETAILED DATA VIEW
# ==========================================
st.markdown("### 📋 Detailed Transaction Records")
st.dataframe(
    filtered_df[[
        'transaction_number', 'transaction_date', 'customer_name', 'customer_type', 
        'account_number', 'product_code', 'debit_credit', 'transaction_amount'
    ]].sort_values(by='transaction_date', ascending=False),
    use_container_width=True
)