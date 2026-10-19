# How to run the employee_dimension pipeline (SQLite, Windows)

One command builds everything: four databases, a year of mock source data, and 52 weekly ETL
runs replayed over that year so `dim_employee` accumulates real SCD2 history.

```powershell
python --version
python -c "import sqlite3; print(sqlite3.sqlite_version)"   # needs 3.33 or newer
python setup_all.py
```

Run it **in PowerShell, from this folder** (the one with `setup_all.py`) — every path in the
scripts is relative to it. There are no options: each run drops the databases, regenerates the
same year of data (fixed seed, identical every time) and replays all 52 weeks. It prints one
line per weekly load, then the validation checks and the headcount at each run, and exits 1 if
an assertion fails.

## What it builds

SQLite keeps each database in one file, so DB1-DB4 are four files in `db/` (created on the
first run):

| Diagram | File | Holds |
|---|---|---|
| DB1 | `db/db1_hrms.db` | `hrms_employee` |
| DB2 | `db/db2_beeline.db` | `beeline_worker` |
| DB3 | `db/db3_smarttime.db` | `st_employee` |
| DB4 | `db/db4_analytics.db` | `stg_*` (3), `intrm_*` (3), `dim_employee` |
| — | `db/_mock_master.db` | every *version* of every source row, with `version_ts` |

Ten tables in all — 3 source, 3 stage, 3 intrm, 1 target. No views, no run-control table, no
reject table, no audit columns: current rows are read with `WHERE is_current = 1`.

## The five steps it prints

1. delete the old `.db` files
2. run every DDL in `sql/01_ddl`
3. generate one year of mock source versions into `db/_mock_master.db`
4. for each of the 52 weekly run dates: rebuild DB1/DB2/DB3 to their state on that date, then
   source -> stage -> intrm x3 -> target (SCD2 merge)
5. run `sql/06_validation/validation_checks.sql` and print the headcount at each run

Two things make the replay work. Inside step 4 the SmartTime intrm runs last of the three,
because it resolves badges against the HRMS and Beeline intrm tables. And each run date is
passed into the target load by `setup_all.py` rather than read from the clock — that is what
lets a year of history be rebuilt from scratch, each version dated by the week that made it.

## Check the result

```powershell
python sampleconnect.py    # tables and columns of DB1
python -c "import sqlite3;print(sqlite3.connect('db/db4_analytics.db').execute('SELECT full_name, worker_type, source_systems, dq_flags FROM dim_employee WHERE is_current = 1 LIMIT 20').fetchall())"
```

Or open `db\db4_analytics.db` in DB Browser for SQLite (https://sqlitebrowser.org) or the
VS Code *SQLite Viewer* extension and browse `dim_employee` (add `WHERE is_current = 1` for
the live version of each person). Close the file in that tool before re-running a load, or
the next run fails with `database is locked`.

Point-in-time query — the dimension as it stood on any date:

```sql
SELECT * FROM dim_employee
WHERE '2026-06-30 02:00:00' >= effective_from
  AND '2026-06-30 02:00:00' <  effective_to;
```

## Folder contents

```
setup_all.py                 the one command: build, generate, replay the year, validate
sampleconnect.py             quick look inside DB1
tools/generate_mock_year.py  generates the year of source versions into db/_mock_master.db
sql/01_ddl/                  one file per table, 10 in all (DB1, DB2, DB3, DB4)
sql/03_source_queries/       the extract query for each source system
sql/04_intrm/                stage -> intrm cleansing, conforming and identity resolution
sql/05_target/               intrm -> dim_employee SCD2 merge (setup_all.py supplies the run date)
sql/06_validation/           4 assertions + row-count / snapshot reports
```

## Common errors

| Error | Fix |
|---|---|
| `unable to open database "db/db1_hrms.db"` | You are not in this folder |
| `no such table: ...` | A previous run was interrupted; re-run `python setup_all.py` |
| `near "FROM": syntax error` in the target load | SQLite is older than 3.33; install a newer Python |
| `database is locked` | Close the `.db` file in DB Browser / VS Code, then retry |
