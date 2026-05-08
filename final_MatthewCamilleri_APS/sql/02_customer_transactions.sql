SELECT 
    t.transaction_number,
    t.transaction_date,
    t.debit_credit,
    t.transaction_amount,
    a.account_number,
    c.customer_profile,
    c.customer_type
FROM Fact_Transactions t
-- Bridge handles the M:N relationship
JOIN Bridge_Account_Customer b 
    ON t.account_sk = b.account_sk
JOIN Dim_Account a 
    ON t.account_sk = a.account_sk
JOIN Dim_Customer c 
    ON b.customer_sk = c.customer_sk
WHERE c.customer_profile = @CustomerProfileId
  AND t.transaction_date BETWEEN @StartDate AND @EndDate
ORDER BY t.transaction_date DESC;