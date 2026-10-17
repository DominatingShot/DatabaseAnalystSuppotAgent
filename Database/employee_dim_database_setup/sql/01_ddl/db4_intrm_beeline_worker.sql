-- =====================================================================
-- DDL  | DB4 (Analytics) INTRM  | intrm_beeline_worker
-- Run against: db/db4_analytics.db
-- Loaded by: sql/04_intrm/intrm_beeline_worker.sql
-- Grain: one clean row per contractor (latest Beeline record per email).
-- =====================================================================

DROP TABLE IF EXISTS intrm_beeline_worker;

CREATE TABLE intrm_beeline_worker (
    emp_key                  TEXT NOT NULL PRIMARY KEY,
    beeline_worker_id        TEXT NOT NULL,
    first_name               TEXT,
    last_name                TEXT,
    email                    TEXT NOT NULL,
    supplier_name            TEXT,
    work_order_id            TEXT,
    bill_rate                REAL,
    bill_currency            TEXT,
    assignment_start_date    TEXT,                   -- ISO date (from MM/DD/YYYY)
    assignment_end_date      TEXT,
    assignment_status        TEXT
        CHECK (assignment_status IN ('ACTIVE','ENDED','PENDING','UNKNOWN')),
    cost_center              TEXT,
    derived_department_code  TEXT,                   -- 'ENG-200' -> 'ENG'
    hiring_manager_emp_key   TEXT,
    job_posting_title        TEXT,
    src_last_modified        TEXT                    -- ISO datetime
);

CREATE INDEX ix_intrm_beeline_worker_id ON intrm_beeline_worker (beeline_worker_id);
