-- =====================================================================
-- DDL  | DB4 (Analytics) INTRM  | intrm_smarttime_employee
-- Run against: db/db4_analytics.db
-- Loaded by: sql/04_intrm/intrm_smarttime_employee.sql
-- That script also resolves badge -> person, so it reads the HRMS and Beeline
-- intrm tables and must run after them.
-- Grain: one clean row per person (the enabled / latest badge wins).
-- =====================================================================

DROP TABLE IF EXISTS intrm_smarttime_employee;

CREATE TABLE intrm_smarttime_employee (
    emp_key                  TEXT NOT NULL PRIMARY KEY,
    smarttime_badge_id       TEXT NOT NULL,
    smarttime_emp_code       TEXT,
    key_resolution           TEXT NOT NULL           -- how emp_key was found
        CHECK (key_resolution IN ('SOURCE_EMAIL','HRMS_EMP_CODE','BEELINE_WORKER_ID')),
    first_name               TEXT,
    last_name                TEXT,
    shift_code               TEXT,
    time_zone                TEXT,
    scheduled_weekly_hours   REAL,
    overtime_eligible        INTEGER CHECK (overtime_eligible IN (0,1)),
    pay_group                TEXT,
    last_punch_ts            TEXT,                   -- ISO datetime (from DD-MM-YYYY)
    is_badge_enabled         INTEGER CHECK (is_badge_enabled IN (0,1)),
    src_modified_on          TEXT
);
