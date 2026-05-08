-- ============================================================
-- 01_monthly_balances.sql
-- Monthly Account Balances
-- Author  : Matthew Camilleri
-- Layer   : Gold (Transaction Data Mart)
-- Description:
--   Calculates a running account balance per account per month.
--   All accounts are assumed to have opened on 1st January 2023
--   with a starting balance of 0.
--   Credits (C) increase the balance; Debits (D) decrease it.
--   Parameters:
--     @p_start_month  : First month to include  (format: YYYY-MM)
--     @p_end_month    : Last month to include   (format: YYYY-MM)
--     @p_account_number : Account natural key   (NULL = all accounts)
-- ============================================================

-- ----- Parameter Declarations (adjust values as needed) -----
DECLARE @p_start_month    VARCHAR(7) = '2023-01';
DECLARE @p_end_month      VARCHAR(7) = '2023-12';
DECLARE @p_account_number VARCHAR(255) = NULL;       -- NULL = all accounts

-- ============================================================
-- Step 1: Build a complete month spine for the requested range
--         so that every account has a row even in months with
--         no activity.
-- ============================================================
WITH MonthSpine AS (
    -- Generate one row per month between the two parameters.
    -- Uses a recursive CTE for broad RDBMS compatibility.
    SELECT
        CAST(DATEADD(MONTH, 0,  DATEFROMPARTS(LEFT(@p_start_month,4), RIGHT(@p_start_month,2), 1)) AS DATE) AS month_start
    UNION ALL
    SELECT
        CAST(DATEADD(MONTH, 1, month_start) AS DATE)
    FROM   MonthSpine
    WHERE  DATEADD(MONTH, 1, month_start) <= DATEFROMPARTS(LEFT(@p_end_month,4), RIGHT(@p_end_month,2), 1)
),

-- ============================================================
-- Step 2: Retrieve the active (current) account dimension rows
--         filtered by the optional account parameter.
-- ============================================================
ActiveAccounts AS (
    SELECT
        da.Account_KEY,
        da.Account_Number,
        da.Product_Code
    FROM   Gold.Dim_Account AS da
    WHERE  da.Is_Active = 1
      AND  (@p_account_number IS NULL OR da.Account_Number = @p_account_number)
),

-- ============================================================
-- Step 3: Cross-join every active account with every month in
--         the spine, giving us the full account x month grid.
-- ============================================================
AccountMonthGrid AS (
    SELECT
        aa.Account_KEY,
        aa.Account_Number,
        aa.Product_Code,
        ms.month_start,
        FORMAT(ms.month_start, 'yyyy-MM') AS year_month
    FROM   ActiveAccounts   aa
    CROSS JOIN MonthSpine   ms
),

-- ============================================================
-- Step 4: Aggregate monthly transaction activity per account.
--         Credits add to the balance, Debits subtract from it.
-- ============================================================
MonthlyActivity AS (
    SELECT
        ft.Account_KEY,
        FORMAT(CAST(ft.Transaction_Date AS DATE), 'yyyy-MM') AS year_month,
        SUM(
            CASE ft.Debit_Credit
                WHEN 'C' THEN  ft.Amount
                WHEN 'D' THEN -ft.Amount
                ELSE 0
            END
        ) AS net_movement
    FROM   Gold.Fact_Transactions AS ft
    WHERE  ft.Transaction_Date >= DATEFROMPARTS(LEFT(@p_start_month,4), RIGHT(@p_start_month,2), 1)
      AND  ft.Transaction_Date <  DATEADD(MONTH, 1, DATEFROMPARTS(LEFT(@p_end_month,4),   RIGHT(@p_end_month,2),   1))
    GROUP BY
        ft.Account_KEY,
        FORMAT(CAST(ft.Transaction_Date AS DATE), 'yyyy-MM')
),

-- ============================================================
-- Step 5: Combine the grid with monthly activity.
--         Months with no activity default to 0 movement.
-- ============================================================
GridWithActivity AS (
    SELECT
        amg.Account_KEY,
        amg.Account_Number,
        amg.Product_Code,
        amg.year_month,
        amg.month_start,
        COALESCE(ma.net_movement, 0) AS net_movement
    FROM       AccountMonthGrid  amg
    LEFT JOIN  MonthlyActivity   ma
           ON  ma.Account_KEY = amg.Account_KEY
           AND ma.year_month  = amg.year_month
),

-- ============================================================
-- Step 6: Apply a running SUM over the net monthly movements
--         to derive the cumulative end-of-month balance.
--         The starting balance on 2023-01-01 is 0 per spec.
-- ============================================================
BalanceCalc AS (
    SELECT
        Account_KEY,
        Account_Number,
        Product_Code,
        year_month,
        net_movement,
        SUM(net_movement) OVER (
            PARTITION BY Account_KEY
            ORDER BY     month_start
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS closing_balance
    FROM   GridWithActivity
)

-- ============================================================
-- Final SELECT: Expose the result set
-- ============================================================
SELECT
    bc.Account_Number,
    bc.Product_Code,
    bc.year_month,
    bc.net_movement          AS monthly_net_movement,
    bc.closing_balance       AS end_of_month_balance
FROM   BalanceCalc bc
ORDER BY
    bc.Account_Number,
    bc.year_month
OPTION (MAXRECURSION 500);   -- Safety cap; 500 covers >40 years of months
