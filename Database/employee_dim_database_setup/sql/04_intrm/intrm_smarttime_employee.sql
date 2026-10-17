-- =====================================================================
-- INTRM TRANSFORMATION  | DB4.stg_smarttime_employee  ->  DB4.intrm_smarttime_employee
-- Run against: db/db4_analytics.db
-- Run order: 3 of 3. Resolves badge -> person against the HRMS and Beeline intrm
--            tables, so both must be loaded before this runs.
-- Pattern: rebuild from the current stage extract. Badges that cannot be tied to a
--          person are dropped.
-- Requires SQLite >= 3.25 (window functions).
--
-- SmartTime email is optional, so emp_key is resolved in priority order:
--   1. its own email   2. emp_code -> HRMS employee_number   3. emp_code -> Beeline worker_id
-- key_resolution records which one won. A badge that matches none of the three has
-- no emp_key and is dropped by the WHERE filter in `ranked`.
-- =====================================================================

BEGIN;

-- dedup: one badge per person -> enabled badge first, then latest modified
DELETE FROM intrm_smarttime_employee;
INSERT INTO intrm_smarttime_employee (
    emp_key, smarttime_badge_id, smarttime_emp_code, key_resolution, first_name, last_name,
    shift_code, time_zone, scheduled_weekly_hours, overtime_eligible, pay_group,
    last_punch_ts, is_badge_enabled, src_modified_on
)
WITH cleaned AS (                     -- clean and type the raw stage columns
    SELECT
        UPPER(TRIM(s.badge_id))                          AS smarttime_badge_id,
        UPPER(TRIM(s.emp_code))                          AS smarttime_emp_code,
        UPPER(TRIM(s.display_name))                      AS display_name,
        NULLIF(LOWER(TRIM(s.email)), '')                 AS src_email,
        UPPER(TRIM(s.shift_code))                        AS shift_code,
        TRIM(s.time_zone)                                AS time_zone,
        CAST(NULLIF(TRIM(s.sched_hours_week), '') AS REAL) AS scheduled_weekly_hours,
        CASE
            WHEN UPPER(TRIM(s.ot_eligible)) IN ('Y','YES','1','TRUE')  THEN 1
            WHEN UPPER(TRIM(s.ot_eligible)) IN ('N','NO','0','FALSE') THEN 0
        END                                              AS overtime_eligible,
        NULLIF(UPPER(TRIM(s.pay_group)), '')             AS pay_group,
        -- DD-MM-YYYY HH:MM  ->  YYYY-MM-DD HH:MM:SS
        datetime(SUBSTR(TRIM(s.last_punch),7,4) || '-' || SUBSTR(TRIM(s.last_punch),4,2) || '-' ||
                 SUBSTR(TRIM(s.last_punch),1,2) || ' ' || SUBSTR(TRIM(s.last_punch),12,5) || ':00')
                                                         AS last_punch_ts,
        CAST(s.is_enabled AS INTEGER)                    AS is_badge_enabled,
        datetime(SUBSTR(TRIM(s.modified_on),7,4) || '-' || SUBSTR(TRIM(s.modified_on),4,2) || '-' ||
                 SUBSTR(TRIM(s.modified_on),1,2) || ' ' || SUBSTR(TRIM(s.modified_on),12,5) || ':00')
                                                         AS src_modified_on
    FROM stg_smarttime_employee s
),
resolved AS (                         -- tie each badge to a person
    SELECT
        c.*,
        COALESCE(c.src_email, h.emp_key, b.emp_key)      AS emp_key,
        CASE
            WHEN c.src_email IS NOT NULL THEN 'SOURCE_EMAIL'
            WHEN h.emp_key   IS NOT NULL THEN 'HRMS_EMP_CODE'
            WHEN b.emp_key   IS NOT NULL THEN 'BEELINE_WORKER_ID'
        END                                              AS key_resolution
    FROM cleaned c
    LEFT JOIN intrm_hrms_employee  h ON h.hrms_employee_number = c.smarttime_emp_code
    LEFT JOIN intrm_beeline_worker b ON b.beeline_worker_id    = c.smarttime_emp_code
),
ranked AS (
    SELECT r.*,
           -- 'LAKSHMI S' -> first 'LAKSHMI', last 'S'
           CASE WHEN INSTR(display_name, ' ') > 0
                THEN SUBSTR(display_name, 1, INSTR(display_name, ' ') - 1)
                ELSE display_name END                         AS raw_first,
           CASE WHEN INSTR(display_name, ' ') > 0
                THEN SUBSTR(display_name, INSTR(display_name, ' ') + 1) END AS raw_last,
           ROW_NUMBER() OVER (PARTITION BY emp_key
                              ORDER BY is_badge_enabled DESC, src_modified_on DESC) AS rn
    FROM resolved r
    WHERE emp_key IS NOT NULL
)
SELECT
    emp_key,
    smarttime_badge_id,
    smarttime_emp_code,
    key_resolution,
    UPPER(SUBSTR(raw_first,1,1)) || LOWER(SUBSTR(raw_first,2)),
    UPPER(SUBSTR(raw_last,1,1))  || LOWER(SUBSTR(raw_last,2)),
    shift_code,
    time_zone,
    scheduled_weekly_hours,
    overtime_eligible,
    pay_group,
    last_punch_ts,
    is_badge_enabled,
    src_modified_on
FROM ranked
WHERE rn = 1;

COMMIT;
