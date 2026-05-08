-- ============================================================
-- 03_top_deposit_month.sql
-- Month with the Highest Sum of Deposits in a Given Year
-- Author  : Matthew Camilleri
-- Layer   : Gold (Transaction Data Mart)
-- Description:
--   Identifies the calendar month within a specified year that
--   recorded the largest total deposit (Credit / 'C') value.
--   Ties are broken by the month number so a single row is
--   always returned. The query also returns all other months
--   ranked for full-year context.
--   Parameters:
--     @p_year : The four-digit calendar year to analyse (INT)
-- ============================================================

-- ----- Parameter Declaration (adjust value as needed) -------
DECLARE @p_year INT = 2023;     -- e.g. 2023

-- ============================================================
-- Step 1: Aggregate total deposits (Credits only) by month for
--         the requested year.
-- ============================================================
WITH MonthlyDeposits AS (
    SELECT
        YEAR(ft.Transaction_Date)                   AS txn_year,
        MONTH(ft.Transaction_Date)                  AS txn_month_num,
        -- Human-readable month label (e.g. "January")
        DATENAME(MONTH, ft.Transaction_Date)        AS txn_month_name,
        -- ISO-style label for easy sorting / slicing
        FORMAT(ft.Transaction_Date, 'yyyy-MM')      AS year_month,
        COUNT(*)                                    AS deposit_count,
        SUM(ft.Amount)                              AS total_deposits
    FROM   Gold.Fact_Transactions AS ft
    WHERE  ft.Debit_Credit    = 'C'              -- Credits = Deposits only
      AND  YEAR(ft.Transaction_Date) = @p_year
    GROUP BY
        YEAR(ft.Transaction_Date),
        MONTH(ft.Transaction_Date),
        DATENAME(MONTH, ft.Transaction_Date),
        FORMAT(ft.Transaction_Date, 'yyyy-MM')
),

-- ============================================================
-- Step 2: Rank months by deposit total (highest first).
--         Secondary sort by month number to resolve ties
--         deterministically (earliest month wins on ties).
-- ============================================================
RankedMonths AS (
    SELECT
        txn_year,
        txn_month_num,
        txn_month_name,
        year_month,
        deposit_count,
        total_deposits,
        RANK() OVER (
            ORDER BY total_deposits DESC,
                     txn_month_num   ASC
        ) AS deposit_rank
    FROM   MonthlyDeposits
)

-- ============================================================
-- Final SELECT: Return all months ranked, with the winner
--              clearly flagged. Consumers can filter WHERE
--              deposit_rank = 1 for just the top month.
-- ============================================================
SELECT
    txn_year                                            AS [Year],
    txn_month_num                                       AS [Month_Number],
    txn_month_name                                      AS [Month_Name],
    year_month                                          AS [Year_Month],
    deposit_count                                       AS [Number_of_Deposits],
    total_deposits                                      AS [Total_Deposit_Amount],
    deposit_rank                                        AS [Deposit_Rank],
    CASE WHEN deposit_rank = 1 THEN 'YES' ELSE 'NO'
    END                                                 AS [Is_Highest_Month],
    -- Percentage share of the year's total deposits
    ROUND(
        100.0 * total_deposits
              / NULLIF(SUM(total_deposits) OVER (), 0),
        2
    )                                                   AS [Pct_Of_Year_Deposits]
FROM   RankedMonths
ORDER BY deposit_rank;
