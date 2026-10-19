# Employee Dimension — Full Flow and Business Logic

**Audience:** an ETL support agent answering questions like *"why does `dim_employee.job_title`
say X for this person when the source says Y?"*

**Scope:** everything needed to trace any target field back through intrm → stage → source,
decide whether the value is correct, and name the exact cause when it is not.

**Golden rule for this agent:** never answer from the target alone. Always read the same
person's row in all four layers, then compare. The layer where the value first changes is the
layer that explains it.

---

## 1. Physical layout

SQLite stores one database per file. All paths are relative to the project root. The
pipeline is exactly ten tables: 3 source, 3 stage, 3 intrm, 1 target. There are no views,
no run-control table and no reject table.

| Logical DB | File | Layer | Tables |
|---|---|---|---|
| DB1 | `db/db1_hrms.db` | Source — HRMS | `hrms_employee` |
| DB2 | `db/db2_beeline.db` | Source — Beeline | `beeline_worker` |
| DB3 | `db/db3_smarttime.db` | Source — SmartTime | `st_employee` |
| DB4 | `db/db4_analytics.db` | Stage + Intrm + Target | `stg_*` (3), `intrm_*` (3), `dim_employee` |

To query across them, attach the sources to DB4:

```sql
ATTACH DATABASE 'db/db1_hrms.db'      AS src_hrms;
ATTACH DATABASE 'db/db2_beeline.db'   AS src_beeline;
ATTACH DATABASE 'db/db3_smarttime.db' AS src_smarttime;
```

### Source systems

| System | DB | Owns | Covers |
|---|---|---|---|
| HRMS | DB1 | Permanent employees — system of record for employment | Employees only |
| Beeline | DB2 | Contingent workers — vendor management | Contractors only |
| SmartTime | DB3 | Time & attendance / badges | Employees **and** contractors |

A person can exist in one, two or all three systems. That is the central fact behind most
"missing column" questions.

---

## 2. Flow and execution order

```
DB1 hrms_employee   → stg_hrms_employee      → intrm_hrms_employee      ┐
DB2 beeline_worker  → stg_beeline_worker     → intrm_beeline_worker     ├→ dim_employee
DB3 st_employee     → stg_smarttime_employee → intrm_smarttime_employee ┘
```

| # | Step | Script | Notes |
|---|---|---|---|
| 1 | Source → stage ×3 | `sql/03_source_queries/*.sql` | Truncate + reload, no transformation |
| 2a | Stage → intrm HRMS | `sql/04_intrm/intrm_hrms_employee.sql` | Must run first |
| 2b | Stage → intrm Beeline | `sql/04_intrm/intrm_beeline_worker.sql` | Must run second |
| 2c | Stage → intrm SmartTime | `sql/04_intrm/intrm_smarttime_employee.sql` | **Must run last** — reads 2a and 2b to resolve identity |
| 3 | Intrm → target | `sql/05_target/dim_employee_load.sql` | SCD2 merge |

**Order dependency matters for debugging.** If 2c ran before 2a/2b, SmartTime badges without
an email could not be resolved and would be dropped instead of reaching the dimension.

### Load patterns per layer

| Layer | Pattern | History kept? |
|---|---|---|
| Stage | `DELETE` then full insert | No — only the latest extract |
| Intrm | `DELETE` then full rebuild from stage | No — only the latest extract |
| Target | SCD2 merge (expire + insert) | **Yes** — every version retained |

So stage and intrm always reflect the **last run only**. The target is the only layer holding
history. This is the single most common source of confusion: if the pipeline has not run since
a source change, stage/intrm/target all still show the *old* value and the source shows the
*new* one — that is correct behaviour, not a defect.

### Run timestamp

There is **no run-control table and no audit column anywhere**. The logical as-of time used
for SCD2 effective dates is passed into the target load by the caller: `setup_all.py` creates
`temp.run_ctx (run_ts, is_first_load)` on its connection, and
`sql/05_target/dim_employee_load.sql` reads `run_ts` from it. The replay supplies the weekly
date it is simulating, which is what lets a year of history be rebuilt from scratch.

**Debug implication:** nothing records when a row was loaded or by which run. The only
timestamp left in the warehouse is the SCD2 window, so "when did the pipeline last change
anything?" is answered with:

```sql
SELECT MAX(effective_from) AS last_change FROM dim_employee;
```

A run that changed nothing leaves no trace at all.

---

## 3. Identity model — `emp_key`

Everything hinges on this.

```
emp_key = LOWER(TRIM(email))
```

- It is created in the intrm layer for each source.
- It is the join key that merges the three sources into one person.
- It becomes `dim_employee.employee_bk` (the business key) unchanged.

**SmartTime is the exception.** Its email is optional, so the `resolved` CTE inside
`sql/04_intrm/intrm_smarttime_employee.sql` resolves `emp_key` in strict priority order and
records which rule won in `key_resolution`:

| Priority | Rule | `key_resolution` |
|---|---|---|
| 1 | The badge's own email | `SOURCE_EMAIL` |
| 2 | `emp_code` matched `intrm_hrms_employee.hrms_employee_number` | `HRMS_EMP_CODE` |
| 3 | `emp_code` matched `intrm_beeline_worker.beeline_worker_id` | `BEELINE_WORKER_ID` |
| — | None matched → `emp_key` is NULL → row is **dropped** | — |

Consequences the agent must know:

- If someone's email differs between HRMS and Beeline, they become **two different people**
  in the dimension. This is the most likely cause of an unexpected duplicate.
- A change of email in a source creates a **new** `employee_bk` and therefore a new dimension
  row; the old row is not expired, because the merge never sees them as the same person.

---

## 4. Layer 1 — Sources

### 4.1 DB1 `hrms_employee`

Natural key `employee_number`. **The extract carries history, so the key repeats.**

| Column | Type | Business meaning | Known quirks |
|---|---|---|---|
| `employee_number` | TEXT | HRMS employee ID (E1001) | Stray spaces / lower case (`' e1004 '`) |
| `first_name` | TEXT | Given name | Mixed case (`'divya'`) |
| `last_name` | TEXT | Family name | Mixed case (`'KRISHNAN'`) |
| `work_email` | TEXT | Corporate email — **identity key** | Mixed case, trailing spaces |
| `hire_date` | TEXT | Date joined | Usually `YYYY-MM-DD`, sometimes `YYYY/MM/DD` |
| `termination_date` | TEXT | Date left | NULL while employed |
| `employment_status` | TEXT | `A`=Active, `L`=Leave, `T`=Terminated | Single-letter codes |
| `employment_type` | TEXT | `FT`/`PT` | |
| `department_code` | TEXT | ENG / FIN / HR | |
| `department_name` | TEXT | Department label | HRMS is master for this |
| `job_title` | TEXT | Title | |
| `job_grade` | TEXT | L3…L6 | |
| `manager_employee_number` | TEXT | Manager's HRMS ID | NULL at top of hierarchy |
| `work_location` | TEXT | Office city | |
| `updated_at` | TEXT | Row version timestamp | **Decides which duplicate wins** |

### 4.2 DB2 `beeline_worker`

Natural key `worker_id`. **Repeats — one row per rate revision.**

| Column | Type | Business meaning | Known quirks |
|---|---|---|---|
| `worker_id` | TEXT | Beeline ID (BL-5001) | |
| `worker_name` | TEXT | `'Last, First'` | Sometimes ALL CAPS |
| `email_address` | TEXT | Email — **identity key** | Leading spaces, upper case |
| `supplier_name` | TEXT | Staffing vendor | |
| `work_order_id` | TEXT | Work order | |
| `bill_rate` | TEXT | Charge rate | Text: `'$38.50'`, `'4,500.00'` |
| `currency` | TEXT | USD / INR | **Mixed across rows** |
| `assignment_start` | TEXT | Start | `MM/DD/YYYY` |
| `assignment_end` | TEXT | End | `MM/DD/YYYY` |
| `worker_status` | TEXT | Active / Ended / Pending | |
| `cost_center` | TEXT | `ENG-200` | Prefix = department |
| `hiring_manager_email` | TEXT | Manager email | |
| `job_posting_title` | TEXT | Title on the posting | |
| `last_modified` | TEXT | Row version | `MM/DD/YYYY HH:MM` — **decides which duplicate wins** |

> **Trap:** `last_modified` is US-format text. Sorting it as text is wrong
> (`'12/20/2025' > '02/03/2026'` as strings). The intrm query converts to ISO *before*
> ordering. If a rate looks stale, check that conversion first.

### 4.3 DB3 `st_employee`

Natural key `badge_id`. One row per badge; **one person can hold several badges.**

| Column | Type | Business meaning | Known quirks |
|---|---|---|---|
| `badge_id` | TEXT | Badge (ST-0001) | PK |
| `emp_code` | TEXT | HRMS number **or** Beeline worker id | Mixed namespace |
| `display_name` | TEXT | `'FIRST LAST'` | ALL CAPS |
| `email` | TEXT | Email | **Optional — may be NULL** |
| `shift_code` | TEXT | GEN / NIGHT / HALF | |
| `time_zone` | TEXT | IANA zone | |
| `sched_hours_week` | TEXT | Scheduled hours | Numeric held as text |
| `ot_eligible` | TEXT | Overtime eligible | Any of `Y/N/1/0/TRUE/FALSE` |
| `pay_group` | TEXT | Payroll group | |
| `last_punch` | TEXT | Last clock event | `DD-MM-YYYY HH:MM` |
| `is_enabled` | INTEGER | 1 = badge active | Old badges disabled, not deleted |
| `modified_on` | TEXT | Row version | `DD-MM-YYYY HH:MM` |

---

## 5. Layer 2 — Stage (`stg_*`)

**Rule: land the source as-is.** Every column TEXT, no trimming, no casting, no dedup, no
filtering. Garbage is preserved deliberately so it can be traced.

Column mapping is **1:1 and same-named** for all three sources, except SmartTime's
`is_enabled`, which is cast to TEXT on the way in. **No audit columns are added** — a stage
table has exactly the columns the extract returns.

**Debug implication:** if stage differs from source, either the pipeline has not run since the
source changed, or the extract filter excluded the row. Nothing else can change a value here.

---

## 6. Layer 3 — Intrm

Purpose: clean, type, and reduce to **one row per person per source**.

### 6.1 `intrm_hrms_employee` — grain: one row per `hrms_employee_number`

**Filter (rows failing it are dropped silently — nothing records them):**
```sql
WHERE NULLIF(TRIM(employee_number),'') IS NOT NULL
  AND NULLIF(TRIM(work_email),'')      IS NOT NULL
```
A row with no employee number or no work email cannot be tied to a person, so it never
reaches intrm. Compare stage against intrm to find such rows.

**Dedup:** `ROW_NUMBER() OVER (PARTITION BY hrms_employee_number ORDER BY src_updated_at DESC)`, keep `rn = 1`.
→ **the row with the latest `updated_at` wins; older versions are discarded.**

| Target column | Expression | Business rule |
|---|---|---|
| `emp_key` | `LOWER(TRIM(work_email))` | Identity key |
| `hrms_employee_number` | `UPPER(TRIM(employee_number))` | Normalised ID |
| `first_name` | `UPPER(SUBSTR(TRIM(first_name),1,1)) \|\| LOWER(SUBSTR(TRIM(first_name),2))` | Proper case |
| `last_name` | same pattern on `last_name` | Proper case |
| `email` | `LOWER(TRIM(work_email))` | |
| `hire_date` | `date(REPLACE(TRIM(hire_date),'/','-'))` | `/` → `-`, then ISO |
| `termination_date` | `date(REPLACE(NULLIF(TRIM(termination_date),''),'/','-'))` | Empty → NULL |
| `employment_status` | `A`→`ACTIVE`, `L`→`ON_LEAVE`, `T`→`TERMINATED`, else `UNKNOWN` | Decode |
| `employment_type` | `FT`→`FULL_TIME`, `PT`→`PART_TIME`, else `UNKNOWN` | Decode |
| `department_code` | `UPPER(TRIM(...))` | |
| `department_name` | `TRIM(...)` | |
| `job_title` | `TRIM(...)` | |
| `job_grade` | `UPPER(TRIM(...))` | |
| `manager_employee_number` | `UPPER(NULLIF(TRIM(...),''))` | |
| `manager_emp_key` | self-join: `m.email` where `m.hrms_employee_number = e.manager_employee_number` | Manager's email; NULL if manager not in this extract |
| `work_location` | `TRIM(...)` | |
| `src_updated_at` | `datetime(TRIM(updated_at))` | ISO datetime |

### 6.2 `intrm_beeline_worker` — grain: one row per `emp_key`

**Filter:** `WHERE NULLIF(TRIM(email_address),'') IS NOT NULL` → rows with no email are
dropped (email is the identity key here).

**Dedup:** `ROW_NUMBER() OVER (PARTITION BY email ORDER BY src_last_modified DESC)`, keep `rn = 1`.
Note the partition is on **email**, not `worker_id` — if one person had two worker ids, only
the latest-modified assignment survives.

| Target column | Expression | Business rule |
|---|---|---|
| `emp_key` | `LOWER(TRIM(email_address))` | Identity key |
| `beeline_worker_id` | `UPPER(TRIM(worker_id))` | |
| `first_name` | text after `','` in `worker_name`, proper-cased | `'Das, Kiran'` → `Kiran` |
| `last_name` | text before `','`, proper-cased | `'Das, Kiran'` → `Das` |
| `supplier_name` | `TRIM(...)` | |
| `work_order_id` | `UPPER(TRIM(...))` | |
| `bill_rate` | `CAST(REPLACE(REPLACE(TRIM(bill_rate),'$',''),',','') AS REAL)` | Strips `$` and `,` |
| `bill_currency` | `UPPER(TRIM(currency))` | |
| `assignment_start_date` | `MM/DD/YYYY` → `YYYY-MM-DD` via SUBSTR | |
| `assignment_end_date` | same | |
| `assignment_status` | `ACTIVE`/`ENDED`/`PENDING`, else `UNKNOWN` | |
| `cost_center` | `UPPER(TRIM(...))` | |
| `derived_department_code` | text before `'-'` in cost_center | `ENG-200` → `ENG` |
| `hiring_manager_emp_key` | `LOWER(NULLIF(TRIM(hiring_manager_email),''))` | |
| `job_posting_title` | `TRIM(...)` | |
| `src_last_modified` | `MM/DD/YYYY HH:MM` → ISO datetime | **Converted before ordering** |

### 6.3 `intrm_smarttime_employee` — grain: one row per `emp_key`

Built in one script with three CTEs: `cleaned` types the stage columns, `resolved` ties each
badge to a person (§3), and `ranked` dedups.

**Cleaning (in the `cleaned` CTE):**

| Target column | Expression |
|---|---|
| `smarttime_badge_id` | `UPPER(TRIM(badge_id))` |
| `smarttime_emp_code` | `UPPER(TRIM(emp_code))` |
| `src_email` | `NULLIF(LOWER(TRIM(email)),'')` |
| `shift_code` | `UPPER(TRIM(...))` |
| `time_zone` | `TRIM(...)` |
| `scheduled_weekly_hours` | `CAST(NULLIF(TRIM(sched_hours_week),'') AS REAL)` |
| `overtime_eligible` | `Y/YES/1/TRUE` → 1; `N/NO/0/FALSE` → 0; anything else → NULL |
| `pay_group` | `NULLIF(UPPER(TRIM(...)),'')` |
| `last_punch_ts` | `DD-MM-YYYY HH:MM` → ISO datetime |
| `is_badge_enabled` | `CAST(is_enabled AS INTEGER)` |
| `src_modified_on` | `DD-MM-YYYY HH:MM` → ISO datetime |
| `emp_key` | `COALESCE(src_email, h.emp_key, b.emp_key)` — in `resolved`, see §3 |
| `key_resolution` | which rule won |

**Names (in the intrm script):** `display_name` is split on the **first space** —
`'LAKSHMI S'` → first `Lakshmi`, last `S`. A one-word display name yields a NULL last name.

**Dropped:** a badge with no email whose `emp_code` matches neither HRMS nor Beeline has
`emp_key = NULL` and is filtered out by `WHERE emp_key IS NOT NULL`. Nothing records it.

**Dedup — the badge-choice rule:**
```sql
ROW_NUMBER() OVER (PARTITION BY emp_key
                   ORDER BY is_badge_enabled DESC, src_modified_on DESC)
```
→ **an enabled badge always beats a disabled one; ties break on latest `modified_on`.**
This is why a converted contractor shows the new employee badge, not the old contractor one.

### 6.4 Rows that never make it

There is no reject table. A row that fails a filter above is simply absent from intrm, so
**a person missing from the dimension is found by comparing stage with intrm**:

```sql
-- HRMS rows in stage that no intrm row corresponds to
SELECT employee_number, work_email FROM stg_hrms_employee
WHERE NULLIF(TRIM(employee_number),'') IS NULL
   OR NULLIF(TRIM(work_email),'')      IS NULL;

-- SmartTime badges that could not be resolved to a person
SELECT badge_id, emp_code, email FROM stg_smarttime_employee
WHERE NULLIF(TRIM(email),'') IS NULL
  AND UPPER(TRIM(emp_code)) NOT IN (SELECT hrms_employee_number FROM intrm_hrms_employee)
  AND UPPER(TRIM(emp_code)) NOT IN (SELECT beeline_worker_id    FROM intrm_beeline_worker);
```

---

## 7. Layer 4 — Target `dim_employee`

**Grain:** one row per person (`employee_bk`) per version. Exactly one row per person has
`is_current = 1`, enforced by a partial unique index.

**Spine:** every `emp_key` found in any of the three intrm tables, `UNION`ed (so once each),
then LEFT JOINed to all three. That is why a person present in only one source still appears.

### 7.1 Survivorship for shared columns — **HRMS > Beeline > SmartTime**

| Target column | Derivation |
|---|---|
| `employee_bk` / `email` | `emp_key` from the spine |
| `first_name` | `COALESCE(hrms, beeline, smarttime)` |
| `last_name` | `COALESCE(hrms, beeline, smarttime)` |
| `full_name` | `TRIM(first_name \|\| ' ' \|\| last_name)` |
| `department_code` | `COALESCE(hrms.department_code, beeline.derived_department_code)` |
| `department_name` | `COALESCE(hrms.department_name, dept_lookup.department_name)` — lookup maps the Beeline-derived code to the HRMS name |
| `job_title` | `COALESCE(hrms.job_title, beeline.job_posting_title)` |
| `manager_employee_bk` | `COALESCE(hrms.manager_emp_key, beeline.hiring_manager_emp_key)` |

### 7.2 Derived classification

| Column | Rule |
|---|---|
| `worker_type` | in HRMS → `EMPLOYEE`; else in Beeline → `CONTRACTOR`; else `UNKNOWN` |
| `employment_status` | in HRMS → the HRMS status (`ACTIVE`/`ON_LEAVE`/`TERMINATED`); else in Beeline → `ACTIVE`/`PENDING_START`/`ENDED`/`UNKNOWN`; else `UNVERIFIED` |
| `is_active` | HRMS person: status in (`ACTIVE`,`ON_LEAVE`) → 1; Beeline person: assignment `ACTIVE` → 1; SmartTime-only: always 0 |

> **Note:** someone on leave counts as active (`is_active = 1`, `employment_status = 'ON_LEAVE'`).

### 7.3 Single-source columns — NULL when the person is not in that source

| Source | Columns |
|---|---|
| HRMS only | `hire_date`, `termination_date`, `employment_type`, `job_grade`, `work_location` |
| Beeline only | `supplier_name`, `work_order_id`, `bill_rate`, `bill_currency`, `assignment_start_date`, `assignment_end_date`, `beeline_cost_center` |
| SmartTime only | `shift_code`, `time_zone`, `scheduled_weekly_hours`, `overtime_eligible`, `pay_group`, `last_punch_ts` |

**This is by design, not a defect.** A NULL `bill_rate` on an employee is correct —
employees have no Beeline record. Confirm with `in_hrms` / `in_beeline` / `in_smarttime`.

### 7.4 Cross-reference and lineage columns

| Column | Meaning |
|---|---|
| `hrms_employee_number` | HRMS natural key, NULL if not in HRMS |
| `beeline_worker_id` | Beeline natural key, NULL if not in Beeline |
| `smarttime_badge_id` | The **winning** badge only (see §6.3) |
| `in_hrms` / `in_beeline` / `in_smarttime` | 1/0 presence flags |
| `source_systems` | Pipe-joined, e.g. `HRMS\|SMARTTIME` |

### 7.5 Data-quality flags (`dq_flags`, pipe-delimited, NULL when clean)

| Flag | Condition | What it means |
|---|---|---|
| `CONVERTED_FROM_CONTRACTOR` | in HRMS **and** in Beeline | Contractor became an employee |
| `TIMEKEEPING_ONLY` | not in HRMS and not in Beeline | Badge exists but no HR/vendor record |
| `SMARTTIME_EMAIL_MISSING` | `key_resolution <> 'SOURCE_EMAIL'` | Identity resolved via `emp_code` |
| `ACTIVE_WITHOUT_BADGE` | `is_active = 1` and not in SmartTime | Active person with no badge |
| `INACTIVE_WITH_ENABLED_BADGE` | `is_active = 0`, badge enabled, and in HRMS or Beeline | **Security issue** — leaver still has an active badge |

### 7.6 SCD handling

**Type 2 (new version on change).** `scd_signature` concatenates these columns; any change
creates a new version:

`hrms_employee_number`, `beeline_worker_id`, `smarttime_badge_id`, `first_name`, `last_name`,
`worker_type`, `employment_status`, `is_active`, `department_code`, `job_title`,
`manager_employee_bk`, `termination_date`, `employment_type`, `job_grade`, `work_location`,
`supplier_name`, `bill_rate`, `bill_currency`, `assignment_end_date`, `shift_code`,
`scheduled_weekly_hours`, `overtime_eligible`, `pay_group`

**Type 1 (overwrite in place, no new version):** `last_punch_ts`, `dq_flags`, `source_systems`.

**Type 2 mechanics:**
1. Unchanged signature → Type 1 columns refreshed on the current row.
2. Changed signature → current row gets `effective_to = run_ts`, `is_current = 0`.
3. A new row is inserted with `is_current = 1`, `effective_to = '9999-12-31 23:59:59'`.
   - First-ever version: `effective_from = '1900-01-01 00:00:00'` (so history has no gap).
   - Later versions: `effective_from = run_ts`.

> **Columns NOT in the signature** — notably `department_name`, `full_name`, `email`,
> `hire_date`, `assignment_start_date`, `work_order_id`, `time_zone`, `beeline_cost_center` —
> **do not trigger a new version**, and because they are not Type 1 either, a change to them
> alone leaves the current row showing the **old** value until some other tracked column
> changes. This is a known limitation and a real answer to "why didn't the target update?".

**Deletes are not handled.** If a person disappears from all sources, their current row stays
as-is. An "employee who already left but still shows active" may be this.

---

## 8. Debug playbook

### 8.1 Trace one person through every layer

Set `:email` to the person's email in lower case.

```sql
-- 0. target: current + full history
SELECT * FROM dim_employee WHERE employee_bk = :email ORDER BY effective_from;

-- 1. intrm (one row each at most)
SELECT * FROM intrm_hrms_employee      WHERE emp_key = :email;
SELECT * FROM intrm_beeline_worker     WHERE emp_key = :email;
SELECT * FROM intrm_smarttime_employee WHERE emp_key = :email;

-- 2. stage (may be several rows — this is where duplicates are visible)
SELECT * FROM stg_hrms_employee      WHERE LOWER(TRIM(work_email))    = :email;
SELECT * FROM stg_beeline_worker     WHERE LOWER(TRIM(email_address)) = :email;
SELECT * FROM stg_smarttime_employee WHERE LOWER(TRIM(email))         = :email;

-- 3. source (requires ATTACH from §1)
SELECT * FROM src_hrms.hrms_employee      WHERE LOWER(TRIM(work_email))    = :email;
SELECT * FROM src_beeline.beeline_worker  WHERE LOWER(TRIM(email_address)) = :email;
SELECT * FROM src_smarttime.st_employee   WHERE LOWER(TRIM(email))         = :email;

-- 4. in stage but not in intrm? then a filter dropped them (§6.4)
SELECT 'HRMS' AS src, employee_number AS id, work_email AS email FROM stg_hrms_employee
 WHERE LOWER(TRIM(work_email)) = :email
   AND (NULLIF(TRIM(employee_number),'') IS NULL OR NULLIF(TRIM(work_email),'') IS NULL)
UNION ALL
SELECT 'BEELINE', worker_id, email_address FROM stg_beeline_worker
 WHERE NULLIF(TRIM(email_address),'') IS NULL;

-- 5. when did the dimension last change? (no run-control table exists)
SELECT MAX(effective_from) AS last_change FROM dim_employee;
```

### 8.2 Decision tree — "target value ≠ source value"

Work down in order; stop at the first match.

| # | Check | If true → verdict |
|---|---|---|
| 1 | Does stage equal the source? | **No** → the pipeline has not run since the source changed (compare the source row's own timestamp with `MAX(effective_from)` in `dim_employee`), **or** the row was filtered out. **Not an ETL defect** — report as "source changed after last run". |
| 2 | Does intrm equal stage for the *winning* row? | **No** → a transformation changed it. Find the column in §6 and quote the rule (decode, proper case, date format, `$`/`,` strip). **Correct by design.** |
| 3 | Are there several stage rows for this person? | **Yes** → dedup picked one. HRMS: latest `updated_at`. Beeline: latest `last_modified` (ISO-converted). SmartTime: enabled badge, then latest `modified_on`. Confirm the winner is genuinely the latest. **Correct by design** unless the version timestamp itself is wrong in the source. |
| 4 | Is the person missing from intrm but present in stage? | **Yes** → a filter dropped the row: missing email / missing employee number / unresolved badge. Confirm with the queries in §6.4. **Data-quality issue in the source.** |
| 5 | Does the target's *current* row differ from intrm? | **Yes** → go to 6 and 7. |
| 6 | Is the differing column in the `scd_signature` list (§7.6)? | **No** → the column does not trigger a version and is not Type 1, so it is stuck at the old value. **Known limitation.** |
| 7 | Did another source win survivorship? | **Yes** → HRMS beats Beeline beats SmartTime (§7.1). E.g. job title comes from HRMS even though Beeline shows a different posting title. **Correct by design.** |
| 8 | Is the column single-source and NULL? | **Yes** → the person is not in that source. Check `in_hrms`/`in_beeline`/`in_smarttime`. **Correct by design.** |
| 9 | Are there two dimension rows for what should be one person? | **Yes** → their email differs between sources, so `emp_key` differs (§3). **Data-quality issue in the source.** |
| 10 | Is the analyst looking at an expired row? | **Yes** → they queried without `is_current = 1`. **User error.** |

### 8.3 Freshness check — is the target simply stale?

With no run-control table, the newest `effective_from` is the best available watermark. It
is the last run that **changed something**, so it is a lower bound on the last run.

```sql
-- last load that changed anything
SELECT MAX(effective_from) AS last_change FROM dim_employee;

-- HRMS rows changed after it (needs ATTACH)
SELECT employee_number, work_email, updated_at
FROM src_hrms.hrms_employee
WHERE datetime(updated_at) > (SELECT MAX(effective_from) FROM dim_employee);
```
Any rows returned → the source moved after the last load that changed anything. The target is
*correct as of its run*, and the fix is to run the pipeline, not to change code.

### 8.4 Integrity checks (all four must return zero rows)

In `sql/06_validation/validation_checks.sql`:
1. More than one current row per person.
2. Overlapping SCD2 effective ranges.
3. A person in intrm with no current dimension row.
4. Source-owned columns populated for someone not in that source.

If any returns rows, it **is** an ETL defect — escalate.

### 8.5 Worked examples (from the mock data)

| Person | Situation | Expected target | Why |
|---|---|---|---|
| **Anjali Rao** (E1008) | Two HRMS rows, promoted | `Senior Software Engineer`, grade L5 | Dedup kept the later `updated_at` |
| **Neha Fernandes** (BL-5003) | Two Beeline rows, rate revised | `bill_rate = 38.50` | ISO conversion before ordering; naive text sort would wrongly pick 35.00 |
| **Kiran Das** (E1007 / BL-5002) | Contractor → employee | `worker_type = EMPLOYEE`, badge `ST-0007`, flag `CONVERTED_FROM_CONTRACTOR` | HRMS wins survivorship; enabled badge beats the disabled contractor badge |
| **Meera Pillai** (E1006) | SmartTime badge has no email | Present, flag `SMARTTIME_EMAIL_MISSING` | `emp_code` matched the HRMS number |
| **Rahul Varma** (E1003) | Terminated, badge still enabled | `is_active = 0`, flag `INACTIVE_WITH_ENABLED_BADGE` | Leaver with live badge |
| **Lakshmi S** (ST-0011) | Badge only | `worker_type = UNKNOWN`, `UNVERIFIED`, flag `TIMEKEEPING_ONLY` | In no HR or vendor system |
| **Visitor badge** (ST-0012) | No email, `emp_code` matches nothing | **Absent** — dropped at intrm | Unresolved identity |
| **Priya Nair** (E1002) | Promoted on a later run | Two rows; old expired, new current | Title + grade are in the signature |

### 8.6 Answer template for the agent

1. **Verdict** — correct by design / stale source / source data-quality issue / ETL defect.
2. **Evidence** — the value at each layer, side by side.
3. **Rule applied** — quote the section and the exact expression.
4. **Action** — none / re-run the pipeline / fix the source record / escalate to ETL.
