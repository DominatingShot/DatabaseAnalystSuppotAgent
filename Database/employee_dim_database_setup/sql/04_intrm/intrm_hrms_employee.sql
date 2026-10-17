-- =====================================================================
-- INTRM TRANSFORMATION  | DB4.stg_hrms_employee  ->  DB4.intrm_hrms_employee
-- Run against: db/db4_analytics.db
-- Run order: 1 of 3 (SmartTime depends on this table).
-- Pattern: rebuild from the current stage extract. Rows with no usable key are dropped.
-- Requires SQLite >= 3.25 (window functions).
-- =====================================================================

BEGIN;

-- clean + dedup (latest updated_at per employee_number) + resolve manager email.
-- Rows with no employee_number or no work_email cannot be tied to a person and are
-- dropped by the WHERE filter in `cleaned`.
DELETE FROM intrm_hrms_employee;
INSERT INTO intrm_hrms_employee (
    emp_key, hrms_employee_number, first_name, last_name, email, hire_date, termination_date,
    employment_status, employment_type, department_code, department_name, job_title, job_grade,
    manager_employee_number, manager_emp_key, work_location, src_updated_at
)
WITH cleaned AS (
    SELECT
        UPPER(TRIM(employee_number))                                         AS hrms_employee_number,
        LOWER(TRIM(work_email))                                              AS email,
        -- proper-case single-token names: 'divya' -> 'Divya', 'KRISHNAN' -> 'Krishnan'
        UPPER(SUBSTR(TRIM(first_name),1,1)) || LOWER(SUBSTR(TRIM(first_name),2)) AS first_name,
        UPPER(SUBSTR(TRIM(last_name),1,1))  || LOWER(SUBSTR(TRIM(last_name),2))  AS last_name,
        date(REPLACE(TRIM(hire_date), '/', '-'))                             AS hire_date,
        date(REPLACE(NULLIF(TRIM(termination_date), ''), '/', '-'))          AS termination_date,
        CASE UPPER(TRIM(employment_status))
            WHEN 'A' THEN 'ACTIVE' WHEN 'L' THEN 'ON_LEAVE' WHEN 'T' THEN 'TERMINATED'
            ELSE 'UNKNOWN' END                                               AS employment_status,
        CASE UPPER(TRIM(employment_type))
            WHEN 'FT' THEN 'FULL_TIME' WHEN 'PT' THEN 'PART_TIME'
            ELSE 'UNKNOWN' END                                               AS employment_type,
        UPPER(TRIM(department_code))                                         AS department_code,
        TRIM(department_name)                                                AS department_name,
        TRIM(job_title)                                                      AS job_title,
        UPPER(TRIM(job_grade))                                               AS job_grade,
        UPPER(NULLIF(TRIM(manager_employee_number), ''))                     AS manager_employee_number,
        TRIM(work_location)                                                  AS work_location,
        datetime(TRIM(updated_at))                                           AS src_updated_at
    FROM stg_hrms_employee
    WHERE NULLIF(TRIM(employee_number), '') IS NOT NULL
      AND NULLIF(TRIM(work_email), '')      IS NOT NULL
),
ranked AS (
    SELECT c.*,
           ROW_NUMBER() OVER (PARTITION BY hrms_employee_number
                              ORDER BY src_updated_at DESC) AS rn
    FROM cleaned c
),
latest AS (
    SELECT * FROM ranked WHERE rn = 1
)
SELECT
    e.email                     AS emp_key,
    e.hrms_employee_number,
    e.first_name,
    e.last_name,
    e.email,
    e.hire_date,
    e.termination_date,
    e.employment_status,
    e.employment_type,
    e.department_code,
    e.department_name,
    e.job_title,
    e.job_grade,
    e.manager_employee_number,
    m.email                     AS manager_emp_key,
    e.work_location,
    e.src_updated_at
FROM latest e
LEFT JOIN latest m ON m.hrms_employee_number = e.manager_employee_number;

COMMIT;
