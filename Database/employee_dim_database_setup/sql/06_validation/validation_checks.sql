-- =====================================================================
-- Validation checks  (run against db/db4_analytics.db)
-- Every "assert" check must return zero rows / zero count.
-- Each check below is preceded by an "@check" comment marker (used by setup_all.py).
-- =====================================================================


-- @check: ASSERT more than one current row per person (expect none)
SELECT employee_bk, COUNT(*) AS current_rows
FROM dim_employee WHERE is_current = 1
GROUP BY employee_bk HAVING COUNT(*) > 1;

-- @check: ASSERT overlapping SCD2 intervals (expect none)
SELECT a.employee_bk, a.employee_sk, b.employee_sk
FROM dim_employee a
JOIN dim_employee b
  ON a.employee_bk = b.employee_bk AND a.employee_sk < b.employee_sk
 AND a.effective_from < b.effective_to AND b.effective_from < a.effective_to;

-- @check: ASSERT every intrm person has exactly one current dim row (expect none)
SELECT k.emp_key
FROM (SELECT emp_key FROM intrm_hrms_employee
      UNION SELECT emp_key FROM intrm_beeline_worker
      UNION SELECT emp_key FROM intrm_smarttime_employee) k
LEFT JOIN dim_employee d ON d.employee_bk = k.emp_key AND d.is_current = 1
WHERE d.employee_sk IS NULL;

-- @check: ASSERT source-owned columns leaked onto people not in that source (expect none)
SELECT employee_bk, 'BEELINE column without Beeline record' AS issue FROM dim_employee
 WHERE is_current = 1
   AND in_beeline = 0 AND (supplier_name IS NOT NULL OR bill_rate IS NOT NULL OR work_order_id IS NOT NULL)
UNION ALL
SELECT employee_bk, 'HRMS column without HRMS record' FROM dim_employee
 WHERE is_current = 1
   AND in_hrms = 0 AND (hire_date IS NOT NULL OR job_grade IS NOT NULL OR employment_type IS NOT NULL)
UNION ALL
SELECT employee_bk, 'SMARTTIME column without SmartTime record' FROM dim_employee
 WHERE is_current = 1
   AND in_smarttime = 0 AND (shift_code IS NOT NULL OR smarttime_badge_id IS NOT NULL);

-- @check: INFO row counts by layer
SELECT 'stg_hrms_employee'        AS tbl, COUNT(*) AS n FROM stg_hrms_employee
UNION ALL SELECT 'stg_beeline_worker',       COUNT(*) FROM stg_beeline_worker
UNION ALL SELECT 'stg_smarttime_employee',   COUNT(*) FROM stg_smarttime_employee
UNION ALL SELECT 'intrm_hrms_employee',      COUNT(*) FROM intrm_hrms_employee
UNION ALL SELECT 'intrm_beeline_worker',     COUNT(*) FROM intrm_beeline_worker
UNION ALL SELECT 'intrm_smarttime_employee', COUNT(*) FROM intrm_smarttime_employee
UNION ALL SELECT 'dim_employee (all versions)', COUNT(*) FROM dim_employee
UNION ALL SELECT 'dim_employee (current)',      COUNT(*) FROM dim_employee WHERE is_current = 1;

-- @check: INFO current dimension snapshot (first 15)
SELECT employee_sk AS sk, full_name, worker_type AS type, employment_status AS status, is_active AS act,
       department_code AS dept, job_title, hrms_employee_number AS hrms, beeline_worker_id AS beeline,
       smarttime_badge_id AS badge, bill_rate, shift_code AS shift, source_systems, dq_flags
FROM dim_employee WHERE is_current = 1 ORDER BY employee_sk LIMIT 15;

-- @check: INFO SCD2 history for the 3 most-versioned people
SELECT employee_sk AS sk, full_name, job_title, job_grade, effective_from, effective_to, is_current
FROM dim_employee
WHERE employee_bk IN (SELECT employee_bk FROM dim_employee
                      GROUP BY employee_bk HAVING COUNT(*) > 1
                      ORDER BY COUNT(*) DESC LIMIT 3)
ORDER BY employee_bk, effective_from;
