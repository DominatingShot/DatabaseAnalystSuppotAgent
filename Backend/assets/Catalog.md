# Knowledge Base Catalogue

**Base folder:** `Backend/assets/KnowledgeBase/` (all paths are relative to the project root `Project_Data_Analytics`)
**Domain:** The employee dimension (`dim_employee`), built from three source systems (HRMS, Beeline, SmartTime) into the analytics database (DB4).
**Last updated:** 2026-10-17

---

## 1. Files

### KB-01 — `EmployeeDimInsights.md`

| Field | Detail |
|---|---|
| **File** | `EmployeeDimInsights.md` |
| **Path** | `Backend/assets/KnowledgeBase/EmployeeDimInsights.md` |
| **Supports** | Insight |
| **Audience** | An analytics agent answering business questions about the employee dimension |
| **Scope** | The target table only: `dim_employee` and the view `v_dim_employee_current` in `db/db4_analytics.db`. Source, stage and intrm layers are out of scope. |
| **Summary** | Explains how to query the employee dimension correctly: which rows to include, what "active" means, which columns apply to which worker type, and which questions the table cannot answer. Contains a full column dictionary and ready-made SQL for common business questions. |

**Contents by section**

| Section | What it holds |
|---|---|
| §1 | Three rules that prevent wrong answers: filter to current version (`is_current = 1` or `v_dim_employee_current`), "active" means `is_active = 1`, and many columns are populated for one worker type only (with presence flags) |
| §2 | Confirms the dimension has no salary or compensation column. Explains the limits of `bill_rate` (contractors only, mixed currency, mixed units, never sum it) |
| §3 | Column dictionary: identity and keys, person attributes, employee-only (HRMS), contractor-only (Beeline), badge-holder-only (SmartTime), source coverage, data-quality flags, versioning columns |
| §4 | Ready-made SQL: active people, worker-type split, department split, source coverage, status breakdown, contractor rates, roll-offs, tenure, badge coverage, leavers with enabled badge, DQ flags, point-in-time headcount, person change history, last-run changes |
| §5 | Pitfalls checklist (12 common wrong-answer patterns) |
| §6 | Answer conventions (state filters and denominators, surface DQ flags) |

**Can answer**
- Headcount, active and inactive counts, worker-type and department breakdowns
- Counts per source system, multi-source people, badge coverage
- Employment status breakdown, contractor roll-offs, employee tenure
- Data-quality flag counts, security flag (leaver with enabled badge)
- Point-in-time headcount and per-person change history
- Contractor rate ranges by currency

**Cannot answer**
- Salary, payroll cost, compensation or average pay (no such column exists)
- Why a specific field holds a specific value (covered by KB-02)
- Anything about stage, intrm or source tables

**Keywords:** headcount, active, inactive, contractor, employee, worker type, department, ENG, FIN, HR, is_active, is_current, SCD2, v_dim_employee_current, bill_rate, currency, badge, SmartTime, tenure, hire_date, assignment_end_date, roll-off, dq_flags, point-in-time, as-of, job_grade, shift, overtime

**Example queries**
- How many active employees are in each department?
- How many contractors are rolling off in the next 90 days?
- How many leavers still have an enabled badge?
- What was the headcount on 2026-03-31?

**Related files:** KB-02 covers why a value in the dimension holds the value it does.

---

### KB-02 — `EmployeeFlowAndFullBusinessLogic.md`

| Field | Detail |
|---|---|
| **File** | `EmployeeFlowAndFullBusinessLogic.md` |
| **Path** | `Backend/assets/KnowledgeBase/EmployeeFlowAndFullBusinessLogic.md` |
| **Supports** | Debug |
| **Audience** | An ETL support agent answering questions like "why does `dim_employee.job_title` say X when the source says Y?" |
| **Scope** | The full pipeline: source → stage → intrm → target, including identity resolution, deduplication, survivorship, SCD2 handling, and a debug playbook |
| **Summary** | Documents every layer and every transformation rule so any target value can be traced back to its source, judged correct or incorrect, and the exact cause named. Includes decision tree, trace queries, freshness and integrity checks, and worked examples from the mock data. |

**Contents by section**

| Section | What it holds |
|---|---|
| §1 | Physical layout: databases DB1 to DB4, file paths, tables per layer, how to `ATTACH` sources |
| §2 | Flow and execution order, load pattern per layer (stage and intrm keep last run only, target keeps history), `etl_run` control table |
| §3 | Identity model: `emp_key = LOWER(TRIM(email))`, SmartTime identity resolution priority, consequences (email mismatch creates two people) |
| §4 | Source tables with column meanings and known quirks: `hrms_employee`, `beeline_worker`, `st_employee` |
| §5 | Stage layer rules (land as-is, audit columns) |
| §6 | Intrm layer: per-source filters, dedup rules, column-by-column transformation expressions, `intrm_reject` |
| §7 | Target `dim_employee`: grain, survivorship (HRMS > Beeline > SmartTime), derived `worker_type`, `employment_status`, `is_active`, single-source columns, lineage columns, DQ flag conditions, SCD1/SCD2 behaviour and known limitations |
| §8 | Debug playbook: trace-one-person queries, 10-step decision tree for "target ≠ source", freshness check, four integrity checks, 8 worked examples, answer template |

**Can answer**
- Why a target value differs from the source value
- Whether a value is correct by design, stale, a source data-quality issue, or an ETL defect
- Why a person is missing, duplicated, or has an unexpected NULL
- Which dedup or survivorship rule picked a value
- Why a source change did not appear in the target
- Which transformation (decode, proper case, date format, `$` and `,` strip) changed a value

**Cannot answer**
- Aggregated business insights on headcount or workforce mix (covered by KB-01)
- Anything outside the three sources and DB4 tables listed in Section 2

**Keywords:** why, mismatch, wrong, incorrect, stale, missing, duplicate, not updated, trace, lineage, source, stage, intrm, reject, dedup, survivorship, SCD2, scd_signature, emp_key, email, key_resolution, HRMS, Beeline, SmartTime, etl_run, pipeline, transformation, NULL, job_title, bill_rate, hire_date, badge, converted contractor, CONVERTED_FROM_CONTRACTOR

**Example queries**
- Why does Anjali Rao show "Senior Software Engineer" while one source row shows a different title?
- Is `bill_rate = 38.50` correct for Neha Fernandes?
- Why is Kiran Das shown as EMPLOYEE and not CONTRACTOR?
- Why is a visitor badge missing from `dim_employee`?
- Why did the target not update after the HRMS record changed?

**Related files:** KB-01 holds the business meaning and allowed values of the `dim_employee` columns.

---

## 2. Data objects

| Object | Layer | Database | Covered in |
|---|---|---|---|
| `hrms_employee` | Source (HRMS) | DB1 | KB-02 §4.1 |
| `beeline_worker` | Source (Beeline) | DB2 | KB-02 §4.2 |
| `st_employee` | Source (SmartTime) | DB3 | KB-02 §4.3 |
| `stg_hrms_employee`, `stg_beeline_worker`, `stg_smarttime_employee` | Stage | DB4 | KB-02 §5 (columns mirror the sources 1:1) |
| `intrm_hrms_employee` | Intrm | DB4 | KB-02 §6.1 |
| `intrm_beeline_worker` | Intrm | DB4 | KB-02 §6.2 |
| `intrm_smarttime_employee`, `vw_smarttime_resolved` | Intrm | DB4 | KB-02 §6.3 |
| `intrm_reject` | Intrm | DB4 | KB-02 §6.4 |
| `dim_employee` | Target | DB4 | KB-01 §3 (business meaning), KB-02 §7 (derivation) |
| `v_dim_employee_current` | Target view | DB4 | KB-01 §1, KB-02 §1 |
| `etl_run` | Run control | DB4 | KB-02 §2 |

---

## 3. Not covered by any file

- Salary, compensation and payroll amounts. KB-01 §2 states the dimension has no such column. `bill_rate` is a vendor charge rate, not pay.
- Tables or systems other than HRMS, Beeline, SmartTime and the DB4 tables listed in Section 2.
- Actual row data. The files describe schema, rules and logic, not data values.
- Full ETL script source code. KB-02 documents the rules and expressions, not the scripts line by line.
- Workforce topics beyond the employee dimension (attendance history, payroll runs, recruitment).