-- =====================================================================
-- DDL  | DB2 (Beeline)  | beeline_worker
-- Run against: db/db2_beeline.db
-- Vendor management system for contingent workers.
-- One worker can have several rows (rate revisions), so worker_id is NOT unique.
-- =====================================================================

DROP TABLE IF EXISTS beeline_worker;

CREATE TABLE beeline_worker (
    worker_id             TEXT NOT NULL,   -- Beeline natural key, e.g. BL-5001
    worker_name           TEXT,            -- 'Last, First'
    email_address         TEXT,
    supplier_name         TEXT,
    work_order_id         TEXT,
    bill_rate             TEXT,            -- '$45.00' / '4,500.00'
    currency              TEXT,
    assignment_start      TEXT,            -- MM/DD/YYYY
    assignment_end        TEXT,            -- MM/DD/YYYY
    worker_status         TEXT,            -- Active / Ended / Pending
    cost_center           TEXT,            -- e.g. ENG-200 (prefix = department)
    hiring_manager_email  TEXT,
    job_posting_title     TEXT,
    last_modified         TEXT             -- MM/DD/YYYY HH:MM
);

CREATE INDEX ix_beeline_worker_id ON beeline_worker (worker_id);
