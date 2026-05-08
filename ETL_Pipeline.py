import polars as pl

def execute_pipeline():
    print("--- 1. Ingestion (Bronze) ---")
    # In a real environment, these are read from S3/ADLS Delta Tables
    df_txns = pl.read_csv("Oracle_Transactions.csv", separator=";")
    df_accs = pl.read_csv("Oracle_Accounts.csv", separator=";", infer_schema_length=10000)
    df_prof = pl.read_csv("Oracle_Profile_Groups.csv", separator=";", infer_schema_length=10000)
    
    df_cust = pl.read_csv("SQLServer_BANKING_CUSTOMERS.csv", separator=";")
    df_phys = pl.read_csv("SQLServer_PHYSICAL_CUSTOMERS.csv", separator=";")
    df_corp = pl.read_csv("SQLServer_CORPORATE_CUSTOMERS.csv", separator=";")

    print("--- 2. Transformation (Silver) ---")
    # Standardize Dates and numeric formats
    df_txns = df_txns.with_columns(
        pl.col("TRANSACTION_DATE").str.strptime(pl.Date, "%d/%m/%Y"),
        pl.col("TRANSACTION_AMOUNT").cast(pl.Float64)
    )

    # Resolve Customer Types
    df_cust_enriched = df_cust.join(df_phys, on="CUSTOMER_PK", how="left").join(
        df_corp, on="CUSTOMER_PK", how="left"
    ).with_columns(
        pl.when(pl.col("COMPANY_TITLE").is_not_null())
        .then(pl.lit("CORPORATE"))
        .otherwise(pl.lit("PHYSICAL"))
        .alias("CUSTOMER_TYPE")
    )

    print("--- 3. Modeling (Gold - Data Mart) ---")
    # In a real DW, we generate Surrogate Keys. Using natural keys for this exercise.
    fact_transactions = df_txns
    dim_account = df_accs
    dim_customer = df_cust_enriched

    # Create Bridge Table to handle Many-to-Many Account/Customer Relationship
    # Account -> Customer Group -> Profiles
    bridge_account_customer = dim_account.select(["ACCOUNT_NUMBER", "CUSTOMER_GROUP_ID"]).join(
        df_prof, on="CUSTOMER_GROUP_ID", how="inner"
    ).select([
        pl.col("ACCOUNT_NUMBER"),
        pl.col("PROFILE_NUMBER").alias("CUSTOMER_PROFILE")
    ])

    print("--- 4. Business Intelligence Queries (Polars Execution) ---")

    # Q1: Monthly Account Balances
    # Assume 0 start on 01/01/2026.
    # Group by Account and Month
    q1_monthly_net = fact_transactions.with_columns(
        pl.col("TRANSACTION_DATE").dt.truncate("1mo").alias("MONTH"),
        pl.when(pl.col("DEBIT_CREDIT") == "C")
        .then(pl.col("TRANSACTION_AMOUNT"))
        .otherwise(-pl.col("TRANSACTION_AMOUNT"))
        .alias("NET_AMOUNT")
    ).group_by(["TRANSACTION_ACCOUNT_NUMBER", "MONTH"]).agg(
        pl.sum("NET_AMOUNT").alias("MONTHLY_NET")
    ).sort(["TRANSACTION_ACCOUNT_NUMBER", "MONTH"])

    # Calculate Cumulative Sum using Window functions
    q1_balances = q1_monthly_net.with_columns(
        pl.col("MONTHLY_NET").cum_sum().over("TRANSACTION_ACCOUNT_NUMBER").alias("RUNNING_BALANCE")
    )
    print("\nQ1: Sample Monthly Account Balances:")
    print(q1_balances.head(5))

    # Q2: Customer Transactions for Date Range
    target_profile = 29235  # Sample Profile
    start_date, end_date = pl.date(2026, 1, 1), pl.date(2026, 12, 31)
    
    # Traverse Fact -> Bridge -> Customer
    q2_cust_txns = fact_transactions.join(
        bridge_account_customer, left_on="TRANSACTION_ACCOUNT_NUMBER", right_on="ACCOUNT_NUMBER", how="inner"
    ).filter(
        (pl.col("CUSTOMER_PROFILE") == target_profile) &
        (pl.col("TRANSACTION_DATE") >= start_date) &
        (pl.col("TRANSACTION_DATE") <= end_date)
    )
    print(f"\nQ2: Transactions for Profile {target_profile} in 2026: {q2_cust_txns.height} found.")

    # Q3: Month with Highest Deposits Total
    q3_top_month = fact_transactions.filter(
        pl.col("DEBIT_CREDIT") == "C"
    ).with_columns(
        pl.col("TRANSACTION_DATE").dt.truncate("1mo").alias("MONTH")
    ).group_by("MONTH").agg(
        pl.sum("TRANSACTION_AMOUNT").alias("TOTAL_DEPOSITS")
    ).sort("TOTAL_DEPOSITS", descending=True).head(1)
    
    print("\nQ3: Month with Highest Deposits Total:")
    print(q3_top_month)

if __name__ == "__main__":
    execute_pipeline()
