import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

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
max_date = df['transaction_date'].min().date()

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
filtered_df = df.loc[mask]

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
col_chart1, col_chart2 = st.columns(2)

# Chart 1: Transaction Volume Over Time
with col_chart1:
    st.markdown("#### Transaction Volume Over Time")
    time_df = filtered_df.groupby(['transaction_date', 'debit_credit'])['transaction_amount'].sum().reset_index()
    fig_time = px.line(
        time_df, 
        x='transaction_date', 
        y='transaction_amount', 
        color='debit_credit',
        labels={'transaction_date': 'Date', 'transaction_amount': 'Amount', 'debit_credit': 'Type'},
        color_discrete_map={'C': 'green', 'D': 'red'}
    )
    st.plotly_chart(fig_time, width=True)

# Chart 2: Customer Type Distribution
with col_chart2:
    st.markdown("#### Transaction Volume by Customer Type")
    cust_df = filtered_df.groupby('customer_type')['transaction_amount'].sum().reset_index()
    fig_cust = px.pie(
        cust_df, 
        names='customer_type', 
        values='transaction_amount',
        hole=0.4,
        color_discrete_sequence=px.colors.sequential.Teal
    )
    st.plotly_chart(fig_cust, width=True)


col_chart3, col_chart4 = st.columns(2)

# Chart 3: Top 10 Customers by Transaction Volume
with col_chart3:
    st.markdown("#### Top 10 Customers by Volume")
    top_cust = filtered_df.groupby('customer_name')['transaction_amount'].sum().nlargest(10).reset_index()
    fig_top = px.bar(
        top_cust, 
        x='transaction_amount', 
        y='customer_name', 
        orientation='h',
        labels={'transaction_amount': 'Total Volume', 'customer_name': 'Customer Name'},
        color='transaction_amount',
        color_continuous_scale='Blues'
    )
    fig_top.update_layout(yaxis={'categoryorder':'total ascending'})
    st.plotly_chart(fig_top, width=True)

# Chart 4: Volume by Product Code
with col_chart4:
    st.markdown("#### Transaction Volume by Product Code")
    prod_df = filtered_df.groupby('product_code')['transaction_amount'].sum().reset_index()
    fig_prod = px.bar(
        prod_df, 
        x='product_code', 
        y='transaction_amount',
        labels={'product_code': 'Product Code', 'transaction_amount': 'Volume'},
        color='product_code'
    )
    st.plotly_chart(fig_prod, width=True)

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
    width=True
)