WITH recursive_months AS (
    SELECT CAST('2023-01-01' AS DATE) AS report_month
    UNION ALL
    SELECT report_month + INTERVAL '1 month'
    FROM recursive_months
    WHERE report_month < CURRENT_DATE
),
accounts_and_months AS (
    -- Create a row for every account for every month
    SELECT a.account_number, rm.report_month
    FROM Dim_Account a
    CROSS JOIN recursive_months rm
),
monthly_nets AS (
    -- Calculate net transaction amount per account per month
    SELECT 
        transaction_account_number AS account_number,
        DATE_TRUNC('month', transaction_date) AS report_month,
        SUM(CASE WHEN debit_credit = 'C' THEN transaction_amount ELSE -transaction_amount END) AS net_amount
    FROM Fact_Transactions
    GROUP BY 1, 2
)
-- Join the generated calendar with nets and compute running total
SELECT 
    am.account_number,
    am.report_month,
    COALESCE(mn.net_amount, 0) AS monthly_net_change,
    SUM(COALESCE(mn.net_amount, 0)) OVER (
        PARTITION BY am.account_number 
        ORDER BY am.report_month 
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_balance
FROM accounts_and_months am
LEFT JOIN monthly_nets mn 
    ON am.account_number = mn.account_number 
    AND am.report_month = mn.report_month
WHERE am.report_month BETWEEN @StartDate AND @EndDate
ORDER BY am.account_number, am.report_month;