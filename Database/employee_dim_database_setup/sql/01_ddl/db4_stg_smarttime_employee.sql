-- =====================================================================
-- DDL  | DB4 (Analytics) STAGE  | stg_smarttime_employee
-- Run against: db/db4_analytics.db
-- Loaded by: sql/03_source_queries/src_smarttime_employee.sql
-- Stage rule: land the source as-is. All TEXT, no cleaning, no dedup.
-- =====================================================================

DROP TABLE IF EXISTS stg_smarttime_employee;

CREATE TABLE stg_smarttime_employee (
    badge_id          TEXT,
    emp_code          TEXT,
    display_name      TEXT,
    email             TEXT,
    shift_code        TEXT,
    time_zone         TEXT,
    sched_hours_week  TEXT,
    ot_eligible       TEXT,
    pay_group         TEXT,
    last_punch        TEXT,
    is_enabled        TEXT,
    modified_on       TEXT
);
