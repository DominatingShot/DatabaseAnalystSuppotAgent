#!/usr/bin/env python3
"""Build the four databases and replay one year of weekly ETL runs.

    python setup_all.py

The five steps it prints, and the point-in-time replay, are described in
HOW_TO_RUN.md next to this file.
"""
import datetime as dt
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import generate_mock_year as gen                 # noqa: E402

DB1, DB2, DB3 = "db/db1_hrms.db", "db/db2_beeline.db", "db/db3_smarttime.db"
DB4 = "db/db4_analytics.db"
MASTER = "db/_mock_master.db"

# DDL files in dependency order, and the DB each one belongs to
DDL = [
    (DB1, "db1_hrms_employee.sql"),
    (DB2, "db2_beeline_worker.sql"),
    (DB3, "db3_st_employee.sql"),
    (DB4, "db4_stg_hrms_employee.sql"),
    (DB4, "db4_stg_beeline_worker.sql"),
    (DB4, "db4_stg_smarttime_employee.sql"),
    (DB4, "db4_intrm_hrms_employee.sql"),
    (DB4, "db4_intrm_beeline_worker.sql"),
    (DB4, "db4_intrm_smarttime_employee.sql"),
    (DB4, "db4_dim_employee.sql"),
]

# (source DB, source query, stage table)
EXTRACTS = [
    (DB1, "src_hrms_employee.sql",      "stg_hrms_employee"),
    (DB2, "src_beeline_worker.sql",     "stg_beeline_worker"),
    (DB3, "src_smarttime_employee.sql", "stg_smarttime_employee"),
]

INTRM = ["intrm_hrms_employee.sql", "intrm_beeline_worker.sql", "intrm_smarttime_employee.sql"]


def read_sql(folder, name):
    with open(os.path.join("sql", folder, name), encoding="utf-8") as f:
        return f.read()


def run_script(db_path, folder, name):
    con = sqlite3.connect(db_path)
    con.executescript(read_sql(folder, name))
    con.commit()
    con.close()


def query(db_path, sql, params=()):
    con = sqlite3.connect(db_path)
    rows = con.execute(sql, params).fetchall()
    con.close()
    return rows


# ---------------------------------------------------------------- the ETL run
def run_dates():
    """52 weekly runs across the generated year. Each run sees the sources as of that date."""
    out = []
    day = gen.WINDOW_START + dt.timedelta(days=7)
    while day <= gen.WINDOW_END + dt.timedelta(days=1):
        out.append(f"{day.isoformat()} 02:00:00")
        day += dt.timedelta(days=7)
    return out


def build_sources_asof(as_of):
    """Rebuild DB1/DB2/DB3 from the master dataset to their state at as_of."""
    con = sqlite3.connect(DB1)
    con.execute("ATTACH DATABASE ? AS m", (MASTER,))
    con.execute("ATTACH DATABASE ? AS b", (DB2,))
    con.execute("ATTACH DATABASE ? AS s", (DB3,))

    # HRMS: the extract carries history -> every version up to now
    hrms = ", ".join(gen.HRMS_COLS)
    con.execute("DELETE FROM hrms_employee")
    con.execute(f"""INSERT INTO hrms_employee ({hrms})
                    SELECT {hrms} FROM m.mst_hrms_employee WHERE version_ts <= ?""", (as_of,))

    # Beeline: one row per revision -> every version up to now
    beeline = ", ".join(gen.BEELINE_COLS)
    con.execute("DELETE FROM b.beeline_worker")
    con.execute(f"""INSERT INTO b.beeline_worker ({beeline})
                    SELECT {beeline} FROM m.mst_beeline_worker WHERE version_ts <= ?""", (as_of,))

    # SmartTime: the badge row is updated in place -> latest version per badge
    smarttime = ", ".join(gen.SMARTTIME_COLS)
    con.execute("DELETE FROM s.st_employee")
    con.execute(f"""INSERT INTO s.st_employee ({smarttime})
                    SELECT {smarttime} FROM (
                        SELECT *, ROW_NUMBER() OVER (PARTITION BY badge_id
                                                     ORDER BY version_ts DESC) AS rn
                        FROM m.mst_smarttime_employee WHERE version_ts <= ?)
                    WHERE rn = 1""", (as_of,))
    con.commit()
    con.close()


def extract_to_stage(src_db, query_file, stg_table):
    """Run the source query on the source DB, truncate + load the stage table in DB4."""
    src = sqlite3.connect(src_db)
    cur = src.execute(read_sql("03_source_queries", query_file))
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    src.close()

    tgt = sqlite3.connect(DB4)
    tgt.execute(f"DELETE FROM {stg_table}")
    tgt.executemany(f"INSERT INTO {stg_table} ({', '.join(cols)}) "
                    f"VALUES ({', '.join('?' * len(cols))})", rows)
    tgt.commit()
    tgt.close()


def run_target_load(as_of):
    """Load dim_employee for the run date as_of.

    There is no run-control table, so the timestamp is handed to the SQL script in
    temp.run_ctx on this connection. It must come from the caller, not the clock,
    or a replayed run would date its versions today.
    """
    con = sqlite3.connect(DB4)
    con.execute("""CREATE TEMP TABLE run_ctx AS
                   SELECT ? AS run_ts,
                          ((SELECT COUNT(*) FROM dim_employee) = 0) AS is_first_load""", (as_of,))
    con.executescript(read_sql("05_target", "dim_employee_load.sql"))
    con.commit()
    con.close()


def run_etl(as_of):
    for src_db, query_file, stg_table in EXTRACTS:
        extract_to_stage(src_db, query_file, stg_table)
    for script in INTRM:
        run_script(DB4, "04_intrm", script)
    run_target_load(as_of)


# ---------------------------------------------------------------- validation
def print_table(rows, cols):
    if not rows:
        print("    (no rows)")
        return
    rows = [["" if v is None else str(v) for v in r] for r in rows]
    widths = [max(len(c), *(len(r[i]) for r in rows)) for i, c in enumerate(cols)]
    print("    " + " | ".join(c.ljust(w) for c, w in zip(cols, widths)))
    print("    " + "-+-".join("-" * w for w in widths))
    for r in rows:
        print("    " + " | ".join(v.ljust(w) for v, w in zip(r, widths)))


def run_checks():
    """Run each '-- @check:' block in validation_checks.sql. ASSERT blocks must return no rows."""
    con = sqlite3.connect(DB4)
    failed = 0
    for chunk in read_sql("06_validation", "validation_checks.sql").split("-- @check:")[1:]:
        name, sql = chunk.split("\n", 1)
        name = name.strip()
        cur = con.execute(sql)
        rows = cur.fetchall()
        print(f"\n  [{name}]")
        print_table(rows, [d[0] for d in cur.description])
        if name.startswith("ASSERT") and rows:
            failed += 1
    con.close()
    print(f"\n  assertions failed: {failed}")
    return failed


def headcount_by_run(dates):
    """Point-in-time headcount: the dimension as it stood at each run."""
    print("\nHeadcount as it stood at each run")
    print(f"  {'as of':<22}{'people':>8}{'active':>8}{'emp':>6}{'ctr':>6}{'unknown':>9}")
    for as_of in dates:
        row = query(DB4, """SELECT COUNT(*), SUM(is_active),
                                   SUM(worker_type = 'EMPLOYEE'), SUM(worker_type = 'CONTRACTOR'),
                                   SUM(worker_type = 'UNKNOWN')
                            FROM dim_employee
                            WHERE ? >= effective_from AND ? < effective_to""", (as_of, as_of))[0]
        print(f"  {as_of:<22}{row[0]:>8}{row[1] or 0:>8}{row[2] or 0:>6}{row[3] or 0:>6}{row[4] or 0:>9}")


# ---------------------------------------------------------------- main
def main():
    print("STEP 1  remove old databases")
    os.makedirs("db", exist_ok=True)
    for path in (DB1, DB2, DB3, DB4):
        if os.path.exists(path):
            os.remove(path)
            print(f"  removed {path}")

    print("\nSTEP 2  create the 10 tables from sql/01_ddl")
    for db, script in DDL:
        run_script(db, "01_ddl", script)
        print(f"  ok  {script}")

    print("\nSTEP 3  generate one year of source data")
    gen.main()

    dates = run_dates()
    print(f"\nSTEP 4  replay {len(dates)} weekly runs "
          f"({dates[0][:10]} to {dates[-1][:10]})")
    for i, as_of in enumerate(dates, 1):
        build_sources_asof(as_of)
        run_etl(as_of)
        current, total = query(DB4, """SELECT (SELECT COUNT(*) FROM dim_employee WHERE is_current = 1),
                                              (SELECT COUNT(*) FROM dim_employee)""")[0]
        print(f"  run {i:>2}/{len(dates)}  as of {as_of[:10]}  "
              f"dim: {current} current / {total} total rows")

    print("\nSTEP 5  validation")
    failed = run_checks()
    headcount_by_run(dates)
    print("\nDone. Open db/db4_analytics.db and browse dim_employee "
          "(current rows: WHERE is_current = 1).")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
