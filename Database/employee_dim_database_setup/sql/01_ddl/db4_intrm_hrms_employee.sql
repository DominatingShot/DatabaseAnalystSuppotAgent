-- =====================================================================
-- DDL  | DB4 (Analytics) INTRM  | intrm_hrms_employee
-- Run against: db/db4_analytics.db
-- Loaded by: sql/04_intrm/intrm_hrms_employee.sql
-- Grain: one clean row per HRMS employee. emp_key = lower(trim(email)).
-- =====================================================================

DROP TABLE IF EXISTS intrm_hrms_employee;

CREATE TABLE intrm_hrms_employee (
    emp_key                  TEXT NOT NULL UNIQUE,   -- identity key (email)
    hrms_employee_number     TEXT NOT NULL PRIMARY KEY,
    first_name               TEXT,
    last_name                TEXT,
    email                    TEXT NOT NULL,
    hire_date                TEXT,                   -- ISO date
    termination_date         TEXT,                   -- ISO date
    employment_status        TEXT NOT NULL
        CHECK (employment_status IN ('ACTIVE','ON_LEAVE','TERMINATED','UNKNOWN')),
    employment_type          TEXT
        CHECK (employment_type IN ('FULL_TIME','PART_TIME','UNKNOWN')),
    department_code          TEXT,
    department_name          TEXT,
    job_title                TEXT,
    job_grade                TEXT,
    manager_employee_number  TEXT,
    manager_emp_key          TEXT,                   -- manager's email, resolved via self-join
    work_location            TEXT,
    src_updated_at           TEXT                    -- ISO datetime
);
