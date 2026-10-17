-- =====================================================================
-- SOURCE QUERY  | DB2 (Beeline) -> DB4.stg_beeline_worker
-- Runs on:  db/db2_beeline.db
-- Lands in: db/db4_analytics.db  stg_beeline_worker  (truncate + insert)
--
-- Extract rule: source columns as-is, names match the stage table.
--
-- Full extract. Note for an incremental version: last_modified is
-- MM/DD/YYYY text, so it must be converted before comparing, e.g.
--     WHERE substr(last_modified,7,4)||'-'||substr(last_modified,1,2)||'-'||
--           substr(last_modified,4,2)||' '||substr(last_modified,12,5)
--           > :last_successful_extract_ts
-- =====================================================================

SELECT
    worker_id,
    worker_name,
    email_address,
    supplier_name,
    work_order_id,
    bill_rate,
    currency,
    assignment_start,
    assignment_end,
    worker_status,
    cost_center,
    hiring_manager_email,
    job_posting_title,
    last_modified
FROM beeline_worker
ORDER BY worker_id;
