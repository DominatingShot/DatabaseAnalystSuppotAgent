-- =====================================================================
-- SOURCE QUERY  | DB1 (HRMS) -> DB4.stg_hrms_employee
-- Runs on:  db/db1_hrms.db
-- Lands in: db/db4_analytics.db  stg_hrms_employee  (truncate + insert)
--
-- Extract rule: select the source columns exactly as they are -- no TRIM,
-- no casting, no dedup. Output column names match the stage table, and the
-- The runner loads the result straight into the stage table, column for column.
--
-- Full extract. For an incremental extract, add:
--     WHERE updated_at > :last_successful_extract_ts
-- =====================================================================

SELECT
    employee_number,
    first_name,
    last_name,
    work_email,
    hire_date,
    termination_date,
    employment_status,
    employment_type,
    department_code,
    department_name,
    job_title,
    job_grade,
    manager_employee_number,
    work_location,
    updated_at
FROM hrms_employee
ORDER BY employee_number, updated_at;
