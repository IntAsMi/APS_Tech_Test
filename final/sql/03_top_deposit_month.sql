SELECT 
    DATE_TRUNC('month', transaction_date) AS deposit_month,
    SUM(transaction_amount) AS total_deposits
FROM Fact_Transactions
WHERE debit_credit = 'C' 
  AND transaction_date >= '2026-01-01'
GROUP BY DATE_TRUNC('month', transaction_date)
ORDER BY total_deposits DESC
LIMIT 1;