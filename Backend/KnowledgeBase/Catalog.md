# Knowledge Base Catalog — Routing Index

**Purpose:** pick which MD files to read for a question. This is the only file read every
time; everything else is read on demand. All files live in `Backend/KnowledgeBase/`.

**How to route:**
1. Match the question in **Routing table**. Take the files listed; read nothing else.
2. No row matches → narrow by **Domain index**, then read the matching file entries' *Answers*
   and *Not for* lines.
3. Still nothing → say the knowledge base does not cover it. Do not guess from a related file.

Read the fewest files that fully answer the question. Two files are warranted only when the
question has two parts (e.g. a number *and* why it is that value).

---

## Domain index

| Domain | Files | Target data |
|---|---|---|
| Employee dimension | `employeeDimInsights.md`, `employeeFlowAndFullBusinessLogic.md` | `dim_employee` + HRMS / Beeline / SmartTime pipeline, `db/db*.db` |

---

## Routing table

| Question / intent | Read |
|---|---|
| A count, list, breakdown or metric from `dim_employee` | `employeeDimInsights.md` |
| What a target column means; which filters a query needs | `employeeDimInsights.md` |
| Whether a metric is answerable at all (e.g. salary) | `employeeDimInsights.md` |
| Why a value is X when the source says Y | `employeeFlowAndFullBusinessLogic.md` |
| A person missing from, or duplicated in, the dimension | `employeeFlowAndFullBusinessLogic.md` |
| How a column is derived; dedup, survivorship, SCD2 mechanics | `employeeFlowAndFullBusinessLogic.md` |
| Source columns, file paths, script order, staleness, lineage | `employeeFlowAndFullBusinessLogic.md` |
| Is the data stale / did the pipeline run | `employeeFlowAndFullBusinessLogic.md` |
| A number **and** the reason behind it | both employee-dimension files |

Default: business/analytics phrasing → insights file; "why" / wrong / missing / defect
phrasing → flow file.

---

## File entries

### `employeeDimInsights.md`
- **Domain:** Employee dimension — target table only
- **Answers:** business questions about `dim_employee` — headcount, contractor mix, department
  splits, badge coverage, tenure, roll-off, data-quality counts, point-in-time ("as of")
- **Not for:** source / stage / intrm layers; how a value got there; debugging a wrong value
- **Contains:** full column dictionary with business meaning and allowed values; the three
  correctness rules (`is_current = 1`, `is_active = 1` includes `ON_LEAVE`, NULL means
  not-applicable — pair with `in_hrms`/`in_beeline`/`in_smarttime`); `employment_status` →
  `is_active` map; which columns exist per worker type and the denominator to state;
  **no salary exists** and why `bill_rate` is not a substitute; `employee_sk` vs
  `employee_bk`; `dq_flags` business impact; ~18 ready-made SQL queries; point-in-time
  pattern; 12-row pitfalls checklist; answer conventions

### `employeeFlowAndFullBusinessLogic.md`
- **Domain:** Employee dimension — full pipeline, source → target
- **Answers:** why a field holds a given value; tracing a field back through intrm → stage →
  source; missing or duplicated people; freshness; whether something is a defect or by design
- **Not for:** curated business metrics; the ready-made analytics query set; what to say when
  a metric cannot be answered
- **Contains:** physical layout (4 SQLite files, exactly 10 tables, `ATTACH` statements, no
  views / run-control / reject table); flow and script order, why intrm SmartTime runs last;
  load pattern per layer (stage and intrm = latest extract only, target = only history);
  `run_ts` via `temp.run_ctx`, `MAX(effective_from)` as the only watermark; identity model
  `emp_key = LOWER(TRIM(email))`, SmartTime resolution priority and `key_resolution`;
  source column dictionaries with their real-world dirt and the duplicate-deciding column;
  stage "land as-is" rule; intrm grain, drop filters and every derived-column expression;
  dedup rules incl. the badge-choice rule; finding dropped rows by comparing stage with intrm;
  survivorship **HRMS > Beeline > SmartTime**; derived `worker_type` / `employment_status` /
  `is_active`; all five `dq_flags` conditions; SCD2 — `scd_signature` list, Type 1 columns,
  expire/insert mechanics, `1900-01-01` sentinel, columns in neither list that keep stale
  values, deletes not handled; debug playbook — per-layer trace, 10-step "target ≠ source"
  decision tree with a verdict per branch, freshness check, 4 integrity checks, 4 worked
  examples

---

## Conventions

**Adding a file:** add one row to **Domain index** (new domain only), one or more rows to
**Routing table**, and one **File entry** using the four fixed lines above — *Domain*,
*Answers*, *Not for*, *Contains*. Keep *Contains* keyword-dense and in the file's own
vocabulary; it is what a question gets matched against. Entries stay in domain order.

**Overlapping files:** when two files document the same object, the routing table decides.
State the division of labour in the *Not for* lines rather than listing the object twice —
e.g. insights holds the business meaning of a `dim_employee` column, flow holds its
derivation.

**Keep in sync:** nothing validates this file. A new or substantially edited MD file that is
not reflected here is unroutable and will not be read.
