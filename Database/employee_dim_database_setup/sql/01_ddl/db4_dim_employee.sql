-- =====================================================================
-- DDL  | DB4 (Analytics) TARGET  | dim_employee  (SCD Type 2, with a few Type 1 columns)
-- Run against: db/db4_analytics.db  (same DB as stage and intrm)
-- Loaded by: sql/05_target/dim_employee_load.sql
--
-- Grain: one row per person (employee_bk) per version.
--        Exactly one row per employee_bk has is_current = 1.
--
-- Column ownership (survivorship):
--   shared     : name, email, department, job_title, manager -> HRMS > Beeline > SmartTime
--   HRMS only  : hire/termination date, employment_type, grade, location, department_name
--   Beeline    : supplier, work order, bill rate, assignment dates, cost center
--   SmartTime  : badge, shift, time zone, weekly hours, OT eligibility, pay group, last punch
-- A column owned by one system is NULL for people who are not in that system.
--
-- SCD handling:
--   Type 2 (new version on change): everything in scd_signature
--   Type 1 (overwrite current row) : last_punch_ts, dq_flags, source_systems
--
-- Current rows are read with WHERE is_current = 1.
-- =====================================================================

DROP TABLE IF EXISTS dim_employee;

CREATE TABLE dim_employee (
    employee_sk              INTEGER PRIMARY KEY AUTOINCREMENT,  -- surrogate key
    employee_bk              TEXT    NOT NULL,                   -- business key = normalised email

    -- cross-reference to every source's natural key
    hrms_employee_number     TEXT,
    beeline_worker_id        TEXT,
    smarttime_badge_id       TEXT,

    -- shared attributes (survivorship applied)
    first_name               TEXT,
    last_name                TEXT,
    full_name                TEXT,
    email                    TEXT    NOT NULL,
    worker_type              TEXT    NOT NULL
        CHECK (worker_type IN ('EMPLOYEE','CONTRACTOR','UNKNOWN')),
    employment_status        TEXT    NOT NULL
        CHECK (employment_status IN ('ACTIVE','ON_LEAVE','TERMINATED','PENDING_START','ENDED','UNVERIFIED','UNKNOWN')),
    is_active                INTEGER NOT NULL CHECK (is_active IN (0,1)),
    department_code          TEXT,
    department_name          TEXT,
    job_title                TEXT,
    manager_employee_bk      TEXT,

    -- HRMS-only
    hire_date                TEXT,
    termination_date         TEXT,
    employment_type          TEXT,
    job_grade                TEXT,
    work_location            TEXT,

    -- Beeline-only
    supplier_name            TEXT,
    work_order_id            TEXT,
    bill_rate                REAL,
    bill_currency            TEXT,
    assignment_start_date    TEXT,
    assignment_end_date      TEXT,
    beeline_cost_center      TEXT,

    -- SmartTime-only
    shift_code               TEXT,
    time_zone                TEXT,
    scheduled_weekly_hours   REAL,
    overtime_eligible        INTEGER,
    pay_group                TEXT,
    last_punch_ts            TEXT,          -- Type 1

    -- lineage / data quality
    in_hrms                  INTEGER NOT NULL CHECK (in_hrms      IN (0,1)),
    in_beeline               INTEGER NOT NULL CHECK (in_beeline   IN (0,1)),
    in_smarttime             INTEGER NOT NULL CHECK (in_smarttime IN (0,1)),
    source_systems           TEXT    NOT NULL,   -- e.g. 'HRMS|SMARTTIME'   (Type 1)
    dq_flags                 TEXT,               -- pipe-delimited          (Type 1)

    -- SCD2 housekeeping
    scd_signature            TEXT    NOT NULL,   -- concatenation of Type-2 columns
    effective_from           TEXT    NOT NULL,
    effective_to             TEXT    NOT NULL DEFAULT '9999-12-31 23:59:59',
    is_current               INTEGER NOT NULL CHECK (is_current IN (0,1))
);

-- At most one current version per person: the database itself enforces SCD2 integrity
CREATE UNIQUE INDEX ux_dim_employee_current ON dim_employee (employee_bk) WHERE is_current = 1;
CREATE INDEX ix_dim_employee_bk_eff ON dim_employee (employee_bk, effective_from);
CREATE INDEX ix_dim_employee_hrms   ON dim_employee (hrms_employee_number);
CREATE INDEX ix_dim_employee_bl     ON dim_employee (beeline_worker_id);
