-- ============================================================
-- 02_customer_transactions.sql
-- Customer Transactions for a Given Date Range
-- Author  : Matthew Camilleri
-- Layer   : Gold (Transaction Data Mart)
-- Description:
--   Lists every transaction belonging to a specific customer
--   (physical or corporate) within a requested date range.
--   Uses the Bridge_Account_Customer table to resolve the
--   many-to-many account↔customer relationship, so joint
--   accounts and multi-account customers are handled correctly.
--   Parameters:
--     @p_customer_profile_id : Customer's natural key (profile id)
--     @p_start_date          : Inclusive start date (YYYY-MM-DD)
--     @p_end_date            : Inclusive end date   (YYYY-MM-DD)
-- ============================================================

-- ----- Parameter Declarations (adjust values as needed) -----
DECLARE @p_customer_profile_id INT          = 6239;          -- e.g. 6239
DECLARE @p_start_date          DATE         = '2023-01-01';  -- e.g. '2023-01-01'
DECLARE @p_end_date            DATE         = '2023-12-31';  -- e.g. '2023-12-31'

-- ============================================================
-- Step 1: Resolve the customer's surrogate key from the
--         profile ID, and capture their type and display name.
--         SCD Type-2: use the active record (Is_Active = 1).
-- ============================================================
WITH CustomerContext AS (
    SELECT
        dc.Customer_KEY,
        dc.Customer_Profile_ID,
        dc.Customer_Type,
        -- Physical customers have a hashed name; corporate have a company title.
        -- We surface whichever is populated for a single display column.
        COALESCE(
            CAST(dc.First_Name  AS VARCHAR(255)),   -- Physical (hashed)
            CAST(dc.Company_Title AS VARCHAR(255))  -- Corporate (hashed)
        ) AS display_name_hashed
    FROM   Gold.Dim_Customer AS dc
    WHERE  dc.Customer_Profile_ID = @p_customer_profile_id
      AND  dc.Is_Active = 1
),

-- ============================================================
-- Step 2: Find all accounts currently linked to this customer
--         via the bridge table (handles joint accounts and
--         customers with multiple accounts).
-- ============================================================
CustomerAccounts AS (
    SELECT DISTINCT
        bac.Account_KEY,
        bac.Customer_Group_ID
    FROM   Gold.Bridge_Account_Customer AS bac
    INNER JOIN CustomerContext          AS cc
           ON  cc.Customer_KEY = bac.Customer_KEY
),

-- ============================================================
-- Step 3: Get the account details for those accounts.
--         We join to the active SCD-2 record so that we always
--         show the most recent product code for each account.
-- ============================================================
AccountDetails AS (
    SELECT
        da.Account_KEY,
        da.Account_Number,
        da.Product_Code,
        ca.Customer_Group_ID
    FROM   Gold.Dim_Account         AS da
    INNER JOIN CustomerAccounts     AS ca
           ON  ca.Account_KEY = da.Account_KEY
    WHERE  da.Is_Active = 1
),

-- ============================================================
-- Step 4: Pull all transactions within the requested date range
--         that belong to any of the customer's accounts.
-- ============================================================
CustomerTransactions AS (
    SELECT
        ft.Transaction_KEY,
        ft.Transaction_Number,
        ft.Transaction_Date,
        ft.Debit_Credit,
        ft.Amount                       AS transaction_amount,
        ft.data_entry_datetime,
        ad.Account_Number,
        ad.Product_Code,
        ad.Customer_Group_ID
    FROM   Gold.Fact_Transactions   AS ft
    INNER JOIN AccountDetails       AS ad
           ON  ad.Account_KEY = ft.Account_KEY
    WHERE  ft.Transaction_Date BETWEEN @p_start_date AND @p_end_date
)

-- ============================================================
-- Final SELECT: Present the full transaction list
-- ============================================================
SELECT
    cc.Customer_Profile_ID,
    cc.Customer_Type,
    cc.display_name_hashed,
    ct.Account_Number,
    ct.Product_Code,
    ct.Customer_Group_ID,
    ct.Transaction_Number,
    ct.Transaction_Date,
    ct.Debit_Credit,
    CASE ct.Debit_Credit
        WHEN 'C' THEN 'Credit (Deposit)'
        WHEN 'D' THEN 'Debit (Withdrawal)'
    END                                 AS transaction_type_desc,
    ct.transaction_amount,
    -- Running account balance within the result set (per account)
    SUM(
        CASE ct.Debit_Credit
            WHEN 'C' THEN  ct.transaction_amount
            WHEN 'D' THEN -ct.transaction_amount
            ELSE 0
        END
    ) OVER (
        PARTITION BY ct.Account_Number
        ORDER BY     ct.Transaction_Date, ct.Transaction_Number
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )                                   AS running_balance_in_range,
    ct.data_entry_datetime
FROM   CustomerTransactions ct
CROSS JOIN CustomerContext  cc      -- Single-row CTE; safe to cross-join
ORDER BY
    ct.Account_Number,
    ct.Transaction_Date,
    ct.Transaction_Number;
