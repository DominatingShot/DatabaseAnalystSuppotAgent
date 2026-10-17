-- =====================================================================
-- DDL  | DB3 (SmartTime)  | st_employee
-- Run against: db/db3_smarttime.db
-- Time & attendance / badge system for employees AND contractors.
-- One row per badge; one person can hold several badges.
-- =====================================================================

DROP TABLE IF EXISTS st_employee;

CREATE TABLE st_employee (
    badge_id          TEXT NOT NULL PRIMARY KEY,   -- SmartTime natural key
    emp_code          TEXT,            -- HRMS employee_number OR Beeline worker_id
    display_name      TEXT,            -- 'FIRST LAST'
    email             TEXT,            -- optional
    shift_code        TEXT,            -- GEN / NIGHT / HALF
    time_zone         TEXT,
    sched_hours_week  TEXT,
    ot_eligible       TEXT,            -- Y/N/1/0/TRUE/FALSE
    pay_group         TEXT,
    last_punch        TEXT,            -- DD-MM-YYYY HH:MM
    is_enabled        INTEGER,         -- 1 = badge active
    modified_on       TEXT             -- DD-MM-YYYY HH:MM
);
