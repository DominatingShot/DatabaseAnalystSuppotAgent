# Employee Dimension — Insights Reference

**Audience:** an analytics agent answering business questions about the employee dimension
(headcount, contractor mix, department splits, badge coverage, data quality).

**Scope:** the target table only — `dim_employee` in `db/db4_analytics.db`. Source, stage and
intrm layers are out of scope here; for "why does this field say X?", use
*EmployeeFlowAndFullBusinessLogic.md* instead.

---

## 1. The three rules that prevent wrong answers

### Rule 1 — always filter to the current version

`dim_employee` keeps history (SCD Type 2). Every change creates a new row, so the table holds
more rows than people. **Counting it unfiltered overstates headcount.**

```sql
-- correct
SELECT COUNT(*) FROM dim_employee WHERE is_current = 1;
```

`WHERE is_current = 1` belongs in every query by default. Query history only when the
question is explicitly about change over time.

### Rule 2 — "active" means `is_active = 1`, not `employment_status = 'ACTIVE'`

`is_active` is the single boolean for "currently working here". It includes people on leave.

| `employment_status` | `is_active` | Meaning |
|---|---|---|
| `ACTIVE` | 1 | Working |
| `ON_LEAVE` | 1 | Employee on leave — **still counts as active** |
| `TERMINATED` | 0 | Employee who left |
| `ENDED` | 0 | Contractor whose assignment finished |
| `PENDING_START` | 0 | Contractor not started yet — **not yet active** |
| `UNVERIFIED` | 0 | Badge-only person, no HR or vendor record |
| `UNKNOWN` | 0 | Status could not be mapped |

### Rule 3 — many columns are populated for only one worker type

A NULL is usually "not applicable", not "missing data". Always pair such a column with its
presence flag, and state the denominator in the answer.

| Column group | Populated for | Presence flag |
|---|---|---|
| `hire_date`, `termination_date`, `employment_type`, `job_grade`, `work_location` | Employees (HRMS) | `in_hrms = 1` |
| `supplier_name`, `work_order_id`, `bill_rate`, `bill_currency`, `assignment_start_date`, `assignment_end_date`, `beeline_cost_center` | Contractors (Beeline) | `in_beeline = 1` |
| `shift_code`, `time_zone`, `scheduled_weekly_hours`, `overtime_eligible`, `pay_group`, `last_punch_ts` | Anyone with a badge (SmartTime) | `in_smarttime = 1` |

> *"Average job grade across the workforce"* is really "average across employees only".
> Say so in the answer.

---

## 2. There is no salary in this dimension

**`dim_employee` holds no salary, compensation or payroll-amount column.** Questions about
total salary, payroll cost or average pay **cannot be answered from this table.** Say so
plainly rather than substituting a different measure.

The only monetary column is `bill_rate`, and it is narrow:

- It applies to **contractors only** (`in_beeline = 1`); it is NULL for every employee.
- It is the **vendor charge rate**, not pay to the person.
- `bill_currency` is **mixed** (USD and INR in the same column).
- The unit is **not uniform** — some rows are hourly, some monthly.

Therefore: **never `SUM(bill_rate)`**, and never compare rates across currencies. The most
you can report is a breakdown, clearly labelled:

```sql
SELECT bill_currency,
       COUNT(*)      AS contractors,
       MIN(bill_rate) AS min_rate,
       MAX(bill_rate) AS max_rate
FROM dim_employee
WHERE is_current = 1 AND in_beeline = 1 AND bill_rate IS NOT NULL
GROUP BY bill_currency;
```

`pay_group` (from SmartTime) is a payroll **grouping label** such as `IN-MONTHLY` or
`CONTRACT` — it carries no amount.

---

## 3. Column dictionary

### Identity and keys

| Column | Type | Business meaning | Notes for analysis |
|---|---|---|---|
| `employee_sk` | INTEGER | Surrogate key, unique per **version** | Never count distinct people with this |
| `employee_bk` | TEXT | Business key = normalised email | **Count distinct people with this** |
| `email` | TEXT | Same as `employee_bk` | |
| `hrms_employee_number` | TEXT | HRMS ID | NULL for pure contractors |
| `beeline_worker_id` | TEXT | Beeline ID | NULL for pure employees |
| `smarttime_badge_id` | TEXT | Winning badge | NULL if no badge |

### Person attributes (populated for everyone)

| Column | Type | Business meaning | Allowed values |
|---|---|---|---|
| `first_name`, `last_name` | TEXT | Name parts | |
| `full_name` | TEXT | Display name | Use for listings |
| `worker_type` | TEXT | Workforce category | `EMPLOYEE`, `CONTRACTOR`, `UNKNOWN` |
| `employment_status` | TEXT | Lifecycle state | See Rule 2 |
| `is_active` | INTEGER | Currently working | 1 / 0 |
| `department_code` | TEXT | Department | `ENG`, `FIN`, `HR`; NULL for badge-only |
| `department_name` | TEXT | Department label | |
| `job_title` | TEXT | Title (HRMS, else Beeline posting title) | Free text — group with care |
| `manager_employee_bk` | TEXT | Manager's email | Self-reference for hierarchy |

`worker_type` rules: in HRMS → `EMPLOYEE` (wins even if also in Beeline, i.e. a converted
contractor); else in Beeline → `CONTRACTOR`; else `UNKNOWN` (badge only).

### Employee-only (HRMS)

| Column | Type | Meaning |
|---|---|---|
| `hire_date` | TEXT (ISO date) | Date joined — use for tenure |
| `termination_date` | TEXT (ISO date) | Date left; NULL while employed |
| `employment_type` | TEXT | `FULL_TIME`, `PART_TIME`, `UNKNOWN` |
| `job_grade` | TEXT | `L3`…`L6`, higher = more senior |
| `work_location` | TEXT | Office city |

### Contractor-only (Beeline)

| Column | Type | Meaning |
|---|---|---|
| `supplier_name` | TEXT | Staffing vendor |
| `work_order_id` | TEXT | Work order |
| `bill_rate` | REAL | Vendor charge rate — see §2 |
| `bill_currency` | TEXT | `USD` / `INR` |
| `assignment_start_date` / `assignment_end_date` | TEXT (ISO date) | Assignment window — use for roll-off reporting |
| `beeline_cost_center` | TEXT | e.g. `ENG-200` |

### Badge-holder only (SmartTime)

| Column | Type | Meaning |
|---|---|---|
| `shift_code` | TEXT | `GEN`, `NIGHT`, `HALF` |
| `time_zone` | TEXT | IANA zone |
| `scheduled_weekly_hours` | REAL | Scheduled hours per week |
| `overtime_eligible` | INTEGER | 1 / 0, NULL if unmappable |
| `pay_group` | TEXT | Payroll group label, no amount |
| `last_punch_ts` | TEXT (ISO datetime) | Last clock event — **refreshed in place each run** |

### Source coverage

| Column | Type | Meaning |
|---|---|---|
| `in_hrms`, `in_beeline`, `in_smarttime` | INTEGER | 1/0 presence per source |
| `source_systems` | TEXT | Pipe-joined, e.g. `HRMS\|SMARTTIME` |

For "how many people come from source X", use the **flags**, not string matching on
`source_systems` — the flags are indexed-friendly and unambiguous.

### Data quality

`dq_flags` is pipe-delimited and NULL when clean. Match with
`dq_flags LIKE '%FLAG%'`.

| Flag | Meaning | Why a business user cares |
|---|---|---|
| `CONVERTED_FROM_CONTRACTOR` | In HRMS and Beeline | Contractor-to-employee conversions |
| `TIMEKEEPING_ONLY` | Badge but no HR/vendor record | Unknown worker — needs investigation |
| `SMARTTIME_EMAIL_MISSING` | Identity resolved via employee code | Lower-confidence match |
| `ACTIVE_WITHOUT_BADGE` | Active but no badge | Onboarding gap |
| `INACTIVE_WITH_ENABLED_BADGE` | Leaver with a live badge | **Security risk — flag prominently** |

### Versioning

| Column | Meaning |
|---|---|
| `effective_from` / `effective_to` | Validity window; current rows end `9999-12-31 23:59:59` |
| `is_current` | 1 for the live version |
| `scd_signature` | Internal change detector — never expose to users |

First-ever versions start at `1900-01-01 00:00:00` so history has no gap. That is a sentinel,
not a real date — **never report it as a start date**.

---

## 4. Ready-made queries

```sql
-- Total active people
SELECT COUNT(*) AS active_people
FROM dim_employee WHERE is_current = 1 AND is_active = 1;

-- Headcount split by worker type
SELECT worker_type,
       COUNT(*)                                   AS total,
       SUM(is_active)                             AS active,
       COUNT(*) - SUM(is_active)                  AS inactive
FROM dim_employee WHERE is_current = 1
GROUP BY worker_type ORDER BY total DESC;

-- Active employees by department
SELECT department_code, department_name, COUNT(*) AS active_employees
FROM dim_employee
WHERE is_current = 1 AND is_active = 1 AND worker_type = 'EMPLOYEE'
GROUP BY department_code, department_name ORDER BY active_employees DESC;

-- People per source system
SELECT SUM(in_hrms) AS from_hrms, SUM(in_beeline) AS from_beeline,
       SUM(in_smarttime) AS from_smarttime, COUNT(*) AS total_people
FROM dim_employee WHERE is_current = 1;

-- People in more than one source
SELECT source_systems, COUNT(*) AS people
FROM dim_employee WHERE is_current = 1
GROUP BY source_systems ORDER BY people DESC;

-- Employment status breakdown
SELECT employment_status, COUNT(*) AS people
FROM dim_employee WHERE is_current = 1
GROUP BY employment_status ORDER BY people DESC;

-- Contractor rates by currency (never summed — see §2)
SELECT bill_currency, COUNT(*) AS contractors,
       MIN(bill_rate) AS min_rate, MAX(bill_rate) AS max_rate
FROM dim_employee
WHERE is_current = 1 AND in_beeline = 1 AND bill_rate IS NOT NULL
GROUP BY bill_currency;

-- Contractors rolling off in the next 90 days
SELECT full_name, supplier_name, assignment_end_date
FROM dim_employee
WHERE is_current = 1 AND is_active = 1 AND assignment_end_date IS NOT NULL
  AND assignment_end_date <= date('now','+90 day')
ORDER BY assignment_end_date;

-- Tenure of active employees (years)
SELECT full_name, hire_date,
       ROUND((julianday('now') - julianday(hire_date)) / 365.25, 1) AS years
FROM dim_employee
WHERE is_current = 1 AND is_active = 1 AND in_hrms = 1
ORDER BY hire_date;

-- Badge coverage
SELECT SUM(in_smarttime) AS with_badge,
       COUNT(*) - SUM(in_smarttime) AS without_badge
FROM dim_employee WHERE is_current = 1 AND is_active = 1;

-- Security: leavers with an enabled badge
SELECT full_name, employment_status, smarttime_badge_id, last_punch_ts
FROM dim_employee
WHERE is_current = 1 AND dq_flags LIKE '%INACTIVE_WITH_ENABLED_BADGE%';

-- Any data-quality flag
SELECT dq_flags, COUNT(*) AS people
FROM dim_employee
WHERE is_current = 1 AND dq_flags IS NOT NULL GROUP BY dq_flags ORDER BY people DESC;

-- Headcount as it stood on a past date (point-in-time)
SELECT COUNT(*) AS active_people
FROM dim_employee
WHERE is_active = 1
  AND :as_of_date >= effective_from AND :as_of_date < effective_to;

-- Change history for one person
SELECT full_name, job_title, job_grade, employment_status,
       effective_from, effective_to, is_current
FROM dim_employee WHERE employee_bk = :email ORDER BY effective_from;

-- Who changed in the most recent load
SELECT full_name, job_title, employment_status, effective_from
FROM dim_employee
WHERE is_current = 1
  AND effective_from = (SELECT MAX(effective_from) FROM dim_employee);
```

**Point-in-time pattern:** for "as of" questions, replace `is_current = 1` with
`:as_of >= effective_from AND :as_of < effective_to`. `effective_to` is exclusive, so this
never double-counts.

---

## 5. Pitfalls checklist

| # | Pitfall | Correct approach |
|---|---|---|
| 1 | Counting `dim_employee` without `is_current` | Add `WHERE is_current = 1` |
| 2 | `COUNT(DISTINCT employee_sk)` as headcount | Use `COUNT(DISTINCT employee_bk)` |
| 3 | Treating `employment_status = 'ACTIVE'` as all active | Use `is_active = 1` (includes `ON_LEAVE`) |
| 4 | Summing `bill_rate` | Never — mixed currency and mixed unit; no salary exists (§2) |
| 5 | Averaging `job_grade` or `scheduled_weekly_hours` across everyone | Restrict to the owning source and say so |
| 6 | Reading NULL as missing data | Check `in_hrms` / `in_beeline` / `in_smarttime` |
| 7 | Counting `PENDING_START` as active | They have not started; `is_active = 0` |
| 8 | Reporting `1900-01-01` as a real start date | Sentinel for the first version |
| 9 | Grouping free-text `job_title` for clean buckets | Use `job_grade` or `department_code` instead |
| 10 | Counting `UNKNOWN` worker type as staff | They are badge-only; report separately |
| 11 | Ignoring a converted contractor's double presence | They are one person, `worker_type = EMPLOYEE` |
| 12 | Trending `last_punch_ts` historically | It is overwritten in place; current value only |

---

## 6. Answer conventions

1. State the filter used — current version, active only, which worker types.
2. Give the denominator for any metric limited to one source.
3. Surface relevant `dq_flags` when they affect the number.
4. If the question needs salary, say the dimension has none (§2) rather than substituting
   `bill_rate`.
5. For "as of" questions, use the point-in-time pattern, not `is_current`.
