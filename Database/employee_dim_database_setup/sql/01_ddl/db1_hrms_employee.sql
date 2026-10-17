-- =====================================================================
-- DDL  | DB1 (HRMS)  | hrms_employee
-- Run against: db/db1_hrms.db
-- System of record for permanent employees.
-- The extract keeps history, so employee_number is NOT unique here.
-- =====================================================================

DROP TABLE IF EXISTS hrms_employee;

CREATE TABLE hrms_employee (
    employee_number          TEXT NOT NULL,   -- HRMS natural key, e.g. E1001
    first_name               TEXT,
    last_name                TEXT,
    work_email               TEXT,            -- cross-system identity key
    hire_date                TEXT,            -- YYYY-MM-DD (sometimes YYYY/MM/DD)
    termination_date         TEXT,
    employment_status        TEXT,            -- A = Active, L = Leave, T = Terminated
    employment_type          TEXT,            -- FT / PT
    department_code          TEXT,
    department_name          TEXT,
    job_title                TEXT,
    job_grade                TEXT,
    manager_employee_number  TEXT,
    work_location            TEXT,
    updated_at               TEXT             -- YYYY-MM-DD HH:MM:SS
);

CREATE INDEX ix_hrms_employee_updated_at ON hrms_employee (updated_at);
