-- =====================================================================
-- INTRM TRANSFORMATION  | DB4.stg_beeline_worker  ->  DB4.intrm_beeline_worker
-- Run against: db/db4_analytics.db
-- Run order: 2 of 3 (SmartTime depends on this table).
-- Pattern: rebuild from the current stage extract. Rows with no email are dropped.
-- Requires SQLite >= 3.25 (window functions).
-- =====================================================================

BEGIN;

-- clean + dedup (latest last_modified per person).
-- Email is the identity key here, so rows without one are dropped by the WHERE
-- filter in `cleaned`.
DELETE FROM intrm_beeline_worker;
INSERT INTO intrm_beeline_worker (
    emp_key, beeline_worker_id, first_name, last_name, email, supplier_name, work_order_id,
    bill_rate, bill_currency, assignment_start_date, assignment_end_date, assignment_status,
    cost_center, derived_department_code, hiring_manager_emp_key, job_posting_title,
    src_last_modified
)
WITH cleaned AS (
    SELECT
        UPPER(TRIM(worker_id))                                         AS beeline_worker_id,
        LOWER(TRIM(email_address))                                     AS email,
        -- 'Last, First' split
        CASE WHEN INSTR(worker_name, ',') > 0
             THEN TRIM(SUBSTR(worker_name, INSTR(worker_name, ',') + 1))
             ELSE TRIM(worker_name) END                                AS raw_first,
        CASE WHEN INSTR(worker_name, ',') > 0
             THEN TRIM(SUBSTR(worker_name, 1, INSTR(worker_name, ',') - 1))
        END                                                            AS raw_last,
        TRIM(supplier_name)                                            AS supplier_name,
        UPPER(TRIM(work_order_id))                                     AS work_order_id,
        -- '$4,500.00' -> 4500.0
        CAST(REPLACE(REPLACE(TRIM(bill_rate), '$', ''), ',', '') AS REAL) AS bill_rate,
        UPPER(TRIM(currency))                                          AS bill_currency,
        -- MM/DD/YYYY -> YYYY-MM-DD
        date(SUBSTR(TRIM(assignment_start),7,4) || '-' || SUBSTR(TRIM(assignment_start),1,2) || '-' ||
             SUBSTR(TRIM(assignment_start),4,2))                      AS assignment_start_date,
        date(SUBSTR(TRIM(assignment_end),7,4)   || '-' || SUBSTR(TRIM(assignment_end),1,2)   || '-' ||
             SUBSTR(TRIM(assignment_end),4,2))                        AS assignment_end_date,
        CASE UPPER(TRIM(worker_status))
            WHEN 'ACTIVE' THEN 'ACTIVE' WHEN 'ENDED' THEN 'ENDED' WHEN 'PENDING' THEN 'PENDING'
            ELSE 'UNKNOWN' END                                         AS assignment_status,
        UPPER(TRIM(cost_center))                                       AS cost_center,
        LOWER(NULLIF(TRIM(hiring_manager_email), ''))                  AS hiring_manager_emp_key,
        TRIM(job_posting_title)                                        AS job_posting_title,
        -- MM/DD/YYYY HH:MM -> YYYY-MM-DD HH:MM:SS  (must convert BEFORE ordering)
        datetime(SUBSTR(TRIM(last_modified),7,4) || '-' || SUBSTR(TRIM(last_modified),1,2) || '-' ||
                 SUBSTR(TRIM(last_modified),4,2) || ' ' || SUBSTR(TRIM(last_modified),12,5) || ':00')
                                                                       AS src_last_modified
    FROM stg_beeline_worker
    WHERE NULLIF(TRIM(email_address), '') IS NOT NULL
),
ranked AS (
    SELECT c.*,
           ROW_NUMBER() OVER (PARTITION BY email ORDER BY src_last_modified DESC) AS rn
    FROM cleaned c
)
SELECT
    email                                                               AS emp_key,
    beeline_worker_id,
    UPPER(SUBSTR(raw_first,1,1)) || LOWER(SUBSTR(raw_first,2))          AS first_name,
    UPPER(SUBSTR(raw_last,1,1))  || LOWER(SUBSTR(raw_last,2))           AS last_name,
    email,
    supplier_name,
    work_order_id,
    bill_rate,
    bill_currency,
    assignment_start_date,
    assignment_end_date,
    assignment_status,
    cost_center,
    CASE WHEN INSTR(cost_center, '-') > 0
         THEN SUBSTR(cost_center, 1, INSTR(cost_center, '-') - 1)
         ELSE cost_center END                                           AS derived_department_code,
    hiring_manager_emp_key,
    job_posting_title,
    src_last_modified
FROM ranked
WHERE rn = 1;

COMMIT;
