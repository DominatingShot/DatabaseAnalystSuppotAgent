-- =====================================================================
-- DDL  | DB4 (Analytics) STAGE  | stg_hrms_employee
-- Run against: db/db4_analytics.db
-- Loaded by: sql/03_source_queries/src_hrms_employee.sql
-- Stage rule: land the source as-is. All TEXT, no cleaning, no dedup.
-- =====================================================================

DROP TABLE IF EXISTS stg_hrms_employee;

CREATE TABLE stg_hrms_employee (
    employee_number          TEXT,
    first_name               TEXT,
    last_name                TEXT,
    work_email               TEXT,
    hire_date                TEXT,
    termination_date         TEXT,
    employment_status        TEXT,
    employment_type          TEXT,
    department_code          TEXT,
    department_name          TEXT,
    job_title                TEXT,
    job_grade                TEXT,
    manager_employee_number  TEXT,
    work_location            TEXT,
    updated_at               TEXT
);
