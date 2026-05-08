**Data Flow Architecture**

```text
[Oracle DB] ──────────(Daily Incremental)─────┐
                                              ▼
                                   [ Bronze Layer (Raw Delta) ]
                                              │
[SQL Server] ─────────(Daily Snapshot)────────┘
                                              │
                                    (Polars / Spark ETL)
                                              │
                                              ▼
                                   [ Silver Layer (Cleansed) ]
                                              │
                                       (Aggregations)
                                              │
                                              ▼
                                  [ Gold Layer (Star Schema) ]
                                              │
                                              ▼
                                    ( PowerBI Dashboard )
```

**Logical Data Model (Data Mart ERD)**

Here is the entity-relationship diagram represented, followed by the table structures. 

```text
                            +-------------------------+
                            |      Dim_Account        |
                            +-------------------------+             
                            | PK: account_sk          |             
                            | NK: account_number      |             
                            +-------------------------+             
                                       | 1                          
                                       |                            
      +-------------------+            | M                              +-------------------------+
      | Fact_Transactions |            |                                |      Dim_Customer       |
      +-------------------+  M         |                                +-------------------------+
      | PK: transaction_sk|------> +-------------------------+          | PK: customer_sk         |
      | FK: account_sk    |      1 | Bridge_Account_Customer |          | NK: customer_profile    |
      +-------------------+        +-------------------------+          +-------------------------+
                                   | FK: account_sk          |                      | 1
                                   | FK: customer_sk         | <--------------------+
                                   +-------------------------+  M           
```
*(Notation: `1` = One side of the relationship, `M` = Many side of the relationship. `PK` = Primary Key, `NK` = Natural Key, `FK` = Foreign Key).*

**Table Definitions & Grain**

*   **`Fact_Transactions`** (Grain: 1 row per transaction event)
    *   `transaction_sk` (PK, integer)
    *   `account_sk` (FK, integer)
    *   `transaction_date` (datetime)
    *   `dr_cr_indicator` (string)
    *   `transaction_amount` (float)
    *   `data_entry_datetime` (datetime)
    *   `data_entry_id` (string)

*   **`Dim_Account`** (Grain: 1 row per account version)
    *   `account_sk` (PK, integer)
    *   `account_number` (NK, string)
    *   `customer_group_id` (string)
    *   `product_code` (string)
    *   `account_designation` (string)
    *   `valid_from` (datetime), `valid_to` (datetime), `is_active` (boolean)
    *   `data_entry_datetime` (datetime), `data_entry_id` (string)

*   **`Dim_Customer`** (Grain: 1 row per customer profile version)
    *   `customer_sk` (PK, integer)
    *   `customer_profile` (NK, string)
    *   `customer_type` (string) - *Derived as Physical or Corporate*
    *   `salutation` (string)
    *   `hashed_firstname`, `hashed_lastname`, `hashed_company_title` (string)
    *   `valid_from` (datetime), `valid_to` (datetime), `is_active` (boolean)
    *   `data_entry_datetime` (datetime), `data_entry_id` (string)

*   **`Bridge_Account_Customer`** (Grain: 1 row per Account-to-Customer mapping)
    *   `account_sk` (PK/FK, integer)
    *   `customer_sk` (PK/FK, integer)
    *   `customer_group_id` (string)
    *   `data_entry_datetime` (datetime), `data_entry_id` (string)


**Explanation of Modelling Choices and Trade-offs**

*   **Star Schema Selection:** The Star Schema is selected here over alternatives to balance between query performace and ease of analysis/interpretability. 
    *   *Trade-off:* This requires upfront robust ETL transformation logic to build. However, it drastically improves query speed, epxecially for large scale data, for BI tools (like PowerBI) and makes the model highly intuitive for end-users to navigate through.
*   **Bridge Table Implementation:** In banking, joint accounts mean one `Account` can belong to multiple `Customers` (a Many-to-Many relationship).
    *   *Trade-off:* If we joined `Fact_Transactions` directly to `Dim_Customer`, joint accounts would duplicate the transaction rows, causing BI tools to mathematically double the financial totals. Adding the `Bridge_Account_Customer` table requires an extra `JOIN` step (slightly impacting performance), but guarantees mathematical accuracy when aggregating funds across different customer profiles.
*   **History Strategy:** To maintain accurate historical reporting, Dimensions utilize Slowly Changing Dimension (SCD) Type 2 tracking (`valid_from`, `valid_to`, `is_active`).
    *   *Trade-off:* This increases table storage size over time compared to simple overwrites (Type 1), but is strictly necessary in banking to ensure point-in-time compliance and auditability.
