-- =====================================================================
-- DDL  | DB4 (Analytics) STAGE  | stg_beeline_worker
-- Run against: db/db4_analytics.db
-- Loaded by: sql/03_source_queries/src_beeline_worker.sql
-- Stage rule: land the source as-is. All TEXT, no cleaning, no dedup.
-- =====================================================================

DROP TABLE IF EXISTS stg_beeline_worker;

CREATE TABLE stg_beeline_worker (
    worker_id             TEXT,
    worker_name           TEXT,
    email_address         TEXT,
    supplier_name         TEXT,
    work_order_id         TEXT,
    bill_rate             TEXT,
    currency              TEXT,
    assignment_start      TEXT,
    assignment_end        TEXT,
    worker_status         TEXT,
    cost_center           TEXT,
    hiring_manager_email  TEXT,
    job_posting_title     TEXT,
    last_modified         TEXT
);
