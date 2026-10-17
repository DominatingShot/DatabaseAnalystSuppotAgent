-- =====================================================================
-- TARGET TRANSFORMATION  | DB4.intrm_* (3 tables)  ->  DB4.dim_employee  (SCD2 merge)
-- Run against: db/db4_analytics.db
-- Requires SQLite >= 3.33 (UPDATE ... FROM).
--
-- CALLER CONTRACT: before running this script the caller must create temp.run_ctx on
-- the same connection, with the logical run timestamp it is loading:
--
--     CREATE TEMP TABLE run_ctx AS
--     SELECT <run_ts> AS run_ts,
--            ((SELECT COUNT(*) FROM dim_employee) = 0) AS is_first_load;
--
-- setup_all.run_target_load() does exactly that. The timestamp is passed in rather
-- than read from the clock so a historical replay dates its versions correctly.
--
-- Steps
--   0. (caller) temp.run_ctx holds run_ts + is_first_load
--   1. build the merged, survivorship-applied snapshot in a TEMP work table
--   2. Type 1 : refresh volatile columns on current rows whose signature is unchanged
--   3. Type 2 : expire current rows whose signature changed
--   4. Type 2 : insert a new current version for new people + changed people
-- =====================================================================

-- ---------- 0. run context ----------
-- temp.run_ctx (run_ts, is_first_load) comes from the caller -- see the contract above.
-- is_first_load is evaluated BEFORE any rows are written in this run, so it is
-- true only on the very first load into an empty dimension (the initial backfill).

-- ---------- 1. merged snapshot ----------
DROP TABLE IF EXISTS temp.wrk_dim_employee;
CREATE TEMP TABLE wrk_dim_employee AS
WITH spine AS (                       -- every person known to any source, once
    SELECT emp_key FROM intrm_hrms_employee
    UNION
    SELECT emp_key FROM intrm_beeline_worker
    UNION
    SELECT emp_key FROM intrm_smarttime_employee
),
dept_lookup AS (                      -- HRMS is the master for department names
    SELECT department_code, MAX(department_name) AS department_name
    FROM intrm_hrms_employee
    GROUP BY department_code
),
merged AS (
    SELECT
        s.emp_key                                                   AS employee_bk,
        h.hrms_employee_number,
        b.beeline_worker_id,
        t.smarttime_badge_id,

        -- shared columns: HRMS > Beeline > SmartTime
        COALESCE(h.first_name, b.first_name, t.first_name)          AS first_name,
        COALESCE(h.last_name,  b.last_name,  t.last_name)           AS last_name,
        s.emp_key                                                   AS email,

        CASE WHEN h.emp_key IS NOT NULL THEN 'EMPLOYEE'
             WHEN b.emp_key IS NOT NULL THEN 'CONTRACTOR'
             ELSE 'UNKNOWN' END                                     AS worker_type,

        CASE WHEN h.emp_key IS NOT NULL THEN h.employment_status
             WHEN b.emp_key IS NOT NULL THEN
                  CASE b.assignment_status WHEN 'ACTIVE'  THEN 'ACTIVE'
                                           WHEN 'PENDING' THEN 'PENDING_START'
                                           WHEN 'ENDED'   THEN 'ENDED'
                                           ELSE 'UNKNOWN' END
             ELSE 'UNVERIFIED' END                                  AS employment_status,

        CASE WHEN h.emp_key IS NOT NULL THEN (h.employment_status IN ('ACTIVE','ON_LEAVE'))
             WHEN b.emp_key IS NOT NULL THEN (b.assignment_status = 'ACTIVE')
             ELSE 0 END                                             AS is_active,

        COALESCE(h.department_code, b.derived_department_code)      AS department_code,
        COALESCE(h.department_name, d.department_name)              AS department_name,
        COALESCE(h.job_title, b.job_posting_title)                  AS job_title,
        COALESCE(h.manager_emp_key, b.hiring_manager_emp_key)       AS manager_employee_bk,

        -- HRMS-only
        h.hire_date, h.termination_date, h.employment_type, h.job_grade, h.work_location,

        -- Beeline-only
        b.supplier_name, b.work_order_id, b.bill_rate, b.bill_currency,
        b.assignment_start_date, b.assignment_end_date, b.cost_center AS beeline_cost_center,

        -- SmartTime-only
        t.shift_code, t.time_zone, t.scheduled_weekly_hours, t.overtime_eligible,
        t.pay_group, t.last_punch_ts,

        (h.emp_key IS NOT NULL)                                     AS in_hrms,
        (b.emp_key IS NOT NULL)                                     AS in_beeline,
        (t.emp_key IS NOT NULL)                                     AS in_smarttime,

        -- carried only to compute DQ flags
        t.key_resolution,
        t.is_badge_enabled
    FROM spine s
    LEFT JOIN intrm_hrms_employee      h ON h.emp_key = s.emp_key
    LEFT JOIN intrm_beeline_worker     b ON b.emp_key = s.emp_key
    LEFT JOIN intrm_smarttime_employee t ON t.emp_key = s.emp_key
    LEFT JOIN dept_lookup                  d ON d.department_code = b.derived_department_code
)
SELECT
    m.*,
    TRIM(COALESCE(m.first_name,'') || ' ' || COALESCE(m.last_name,''))   AS full_name,

    TRIM(CASE WHEN m.in_hrms      THEN 'HRMS|'      ELSE '' END ||
         CASE WHEN m.in_beeline   THEN 'BEELINE|'   ELSE '' END ||
         CASE WHEN m.in_smarttime THEN 'SMARTTIME|' ELSE '' END, '|')     AS source_systems,

    NULLIF(TRIM(
        CASE WHEN m.in_hrms AND m.in_beeline             THEN 'CONVERTED_FROM_CONTRACTOR|' ELSE '' END ||
        CASE WHEN NOT m.in_hrms AND NOT m.in_beeline     THEN 'TIMEKEEPING_ONLY|'          ELSE '' END ||
        CASE WHEN m.key_resolution <> 'SOURCE_EMAIL'     THEN 'SMARTTIME_EMAIL_MISSING|'   ELSE '' END ||
        CASE WHEN m.is_active = 1 AND NOT m.in_smarttime THEN 'ACTIVE_WITHOUT_BADGE|'      ELSE '' END ||
        CASE WHEN m.is_active = 0 AND m.is_badge_enabled = 1 AND (m.in_hrms OR m.in_beeline)
                                                         THEN 'INACTIVE_WITH_ENABLED_BADGE|' ELSE '' END,
    '|'), '')                                                             AS dq_flags,

    -- Type-2 change detector: any change here creates a new version
    IFNULL(m.hrms_employee_number,'~')   || '|' || IFNULL(m.beeline_worker_id,'~')      || '|' ||
    IFNULL(m.smarttime_badge_id,'~')     || '|' || IFNULL(m.first_name,'~')             || '|' ||
    IFNULL(m.last_name,'~')              || '|' || m.worker_type                        || '|' ||
    m.employment_status                  || '|' || m.is_active                          || '|' ||
    IFNULL(m.department_code,'~')        || '|' || IFNULL(m.job_title,'~')              || '|' ||
    IFNULL(m.manager_employee_bk,'~')    || '|' || IFNULL(m.termination_date,'~')       || '|' ||
    IFNULL(m.employment_type,'~')        || '|' || IFNULL(m.job_grade,'~')              || '|' ||
    IFNULL(m.work_location,'~')          || '|' || IFNULL(m.supplier_name,'~')          || '|' ||
    IFNULL(m.bill_rate,'~')              || '|' || IFNULL(m.bill_currency,'~')          || '|' ||
    IFNULL(m.assignment_end_date,'~')    || '|' || IFNULL(m.shift_code,'~')             || '|' ||
    IFNULL(m.scheduled_weekly_hours,'~') || '|' || IFNULL(m.overtime_eligible,'~')      || '|' ||
    IFNULL(m.pay_group,'~')                                                               AS scd_signature
FROM merged m;

BEGIN;

-- ---------- 2. Type 1: overwrite volatile columns on unchanged current rows ----------
UPDATE dim_employee
SET    last_punch_ts  = w.last_punch_ts,
       dq_flags       = w.dq_flags,
       source_systems = w.source_systems
FROM   temp.wrk_dim_employee w
WHERE  dim_employee.employee_bk   = w.employee_bk
  AND  dim_employee.is_current    = 1
  AND  dim_employee.scd_signature = w.scd_signature
  AND (dim_employee.last_punch_ts  IS NOT w.last_punch_ts
    OR dim_employee.dq_flags       IS NOT w.dq_flags
    OR dim_employee.source_systems IS NOT w.source_systems);

-- ---------- 3. Type 2: expire current rows whose tracked attributes changed ----------
UPDATE dim_employee
SET    effective_to = (SELECT run_ts FROM temp.run_ctx),
       is_current   = 0
WHERE  is_current = 1
  AND  EXISTS (SELECT 1
               FROM temp.wrk_dim_employee w
               WHERE w.employee_bk   = dim_employee.employee_bk
                 AND w.scd_signature <> dim_employee.scd_signature);

-- ---------- 4. Type 2: insert new current version (brand-new people + just-expired people) ----------
INSERT INTO dim_employee (
    employee_bk, hrms_employee_number, beeline_worker_id, smarttime_badge_id,
    first_name, last_name, full_name, email, worker_type, employment_status, is_active,
    department_code, department_name, job_title, manager_employee_bk,
    hire_date, termination_date, employment_type, job_grade, work_location,
    supplier_name, work_order_id, bill_rate, bill_currency,
    assignment_start_date, assignment_end_date, beeline_cost_center,
    shift_code, time_zone, scheduled_weekly_hours, overtime_eligible, pay_group, last_punch_ts,
    in_hrms, in_beeline, in_smarttime, source_systems, dq_flags,
    scd_signature, effective_from, effective_to, is_current
)
SELECT
    w.employee_bk, w.hrms_employee_number, w.beeline_worker_id, w.smarttime_badge_id,
    w.first_name, w.last_name, w.full_name, w.email, w.worker_type, w.employment_status, w.is_active,
    w.department_code, w.department_name, w.job_title, w.manager_employee_bk,
    w.hire_date, w.termination_date, w.employment_type, w.job_grade, w.work_location,
    w.supplier_name, w.work_order_id, w.bill_rate, w.bill_currency,
    w.assignment_start_date, w.assignment_end_date, w.beeline_cost_center,
    w.shift_code, w.time_zone, w.scheduled_weekly_hours, w.overtime_eligible, w.pay_group, w.last_punch_ts,
    w.in_hrms, w.in_beeline, w.in_smarttime, w.source_systems, w.dq_flags,
    w.scd_signature,
    -- Initial backfill only: everyone already existed before the warehouse did, so their
    -- first version opens at the sentinel. On every later run a person who appears for the
    -- first time is genuinely new, so their version opens at run_ts -- otherwise a joiner
    -- would look like they had existed since 1900 and point-in-time headcount would be flat.
    CASE WHEN r.is_first_load = 1 THEN '1900-01-01 00:00:00' ELSE r.run_ts END,
    '9999-12-31 23:59:59',
    1
FROM temp.wrk_dim_employee w
CROSS JOIN temp.run_ctx r
WHERE NOT EXISTS (SELECT 1 FROM dim_employee d
                  WHERE d.employee_bk = w.employee_bk AND d.is_current = 1);

COMMIT;

