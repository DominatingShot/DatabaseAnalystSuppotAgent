-- =====================================================================
-- SOURCE QUERY  | DB3 (SmartTime) -> DB4.stg_smarttime_employee
-- Runs on:  db/db3_smarttime.db
-- Lands in: db/db4_analytics.db  stg_smarttime_employee  (truncate + insert)
--
-- Extract rule: source columns as-is, names match the stage table.
-- Disabled badges are extracted too: intrm needs them to pick the right
-- badge per person and to detect terminated people with enabled badges.
-- =====================================================================

SELECT
    badge_id,
    emp_code,
    display_name,
    email,
    shift_code,
    time_zone,
    sched_hours_week,
    ot_eligible,
    pay_group,
    last_punch,
    is_enabled,
    modified_on
FROM st_employee
ORDER BY badge_id;
