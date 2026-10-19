#!/usr/bin/env python3
"""
Generate ONE YEAR of realistic mock data for the three source systems.

Output: db/_mock_master.db  -- a "master" dataset holding every *version* of every
source record, each tagged with a clean `version_ts`. The real source databases
(DB1/DB2/DB3) are then rebuilt from it for any point in time, which is how the
replay in setup_all.py simulates the pipeline running month after month.

Why a master instead of writing DB1/DB2/DB3 directly:
  * HRMS and Beeline extracts carry history, so at run date D they contain every
    version with version_ts <= D.
  * SmartTime updates a badge row in place, so at run date D it contains the
    LATEST version per badge with version_ts <= D.
Filtering the master by date reproduces all three behaviours exactly.

The data deliberately contains the same messiness the intrm layer is built to fix
(case, padding, date formats, currency text, duplicates) and every data-quality
case the target layer flags.

Deterministic: the fixed SEED below always produces the same year.
"""
import datetime as dt
import os
import random
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(ROOT, "db", "_mock_master.db")

# fixed, so the same year is rebuilt byte for byte on every run
SEED, N_EMPLOYEES, N_CONTRACTORS = 20260101, 200, 60

# ---------------------------------------------------------------- year window
WINDOW_START = dt.date(2025, 10, 1)   # first day events can happen
WINDOW_END = dt.date(2026, 9, 30)     # last day events can happen

# ---------------------------------------------------------------- reference data
FIRST_NAMES = [
    "Arjun", "Priya", "Rahul", "Divya", "Sanjay", "Meera", "Kiran", "Anjali", "Vikram", "Neha",
    "Joseph", "Lakshmi", "Rohan", "Sneha", "Aditya", "Kavya", "Nikhil", "Pooja", "Varun", "Shreya",
    "Manish", "Ananya", "Suresh", "Ritu", "Aravind", "Deepa", "Harish", "Nandini", "Prakash", "Swathi",
    "Gautam", "Ishita", "Karthik", "Madhuri", "Naveen", "Preethi", "Rajesh", "Sowmya", "Tarun", "Vidya",
    "Abhishek", "Bhavana", "Chetan", "Diya", "Girish", "Haritha", "Jayanth", "Keerthi", "Mohan", "Nithya",
]
LAST_NAMES = [
    "Menon", "Nair", "Varma", "Krishnan", "Iyer", "Pillai", "Das", "Rao", "Gupta", "Fernandes",
    "Thomas", "Sharma", "Reddy", "Kumar", "Shetty", "Bhat", "Joshi", "Mehta", "Chandra", "Verma",
    "Kulkarni", "Desai", "Patel", "Singh", "Mathew", "George", "Prabhu", "Hegde", "Nambiar", "Ravi",
]

LADDER = {
    "ENG": [("Associate Engineer", "L2"), ("Software Engineer I", "L3"), ("Software Engineer II", "L4"),
            ("Senior Software Engineer", "L5"), ("Staff Engineer", "L6"), ("Engineering Manager", "L6"),
            ("Director of Engineering", "L7")],
    "FIN": [("Finance Associate", "L2"), ("Financial Analyst", "L3"), ("Senior Financial Analyst", "L4"),
            ("Finance Lead", "L5"), ("Finance Manager", "L6"), ("Director of Finance", "L7")],
    "HR":  [("HR Associate", "L2"), ("HR Specialist", "L3"), ("Senior HR Specialist", "L4"),
            ("HR Business Partner", "L5"), ("HR Manager", "L6")],
    "SAL": [("Sales Development Rep", "L2"), ("Account Executive", "L3"), ("Senior Account Executive", "L4"),
            ("Sales Lead", "L5"), ("Sales Manager", "L6"), ("Director of Sales", "L7")],
    "OPS": [("Operations Associate", "L2"), ("Operations Analyst", "L3"), ("Senior Operations Analyst", "L4"),
            ("Operations Lead", "L5"), ("Operations Manager", "L6")],
    "MKT": [("Marketing Associate", "L2"), ("Marketing Specialist", "L3"), ("Senior Marketing Specialist", "L4"),
            ("Marketing Lead", "L5"), ("Marketing Manager", "L6")],
}
DEPT_NAME = {"ENG": "Engineering", "FIN": "Finance", "HR": "Human Resources",
             "SAL": "Sales", "OPS": "Operations", "MKT": "Marketing"}
DEPTS = list(LADDER)
DEPT_WEIGHTS = [0.40, 0.12, 0.08, 0.18, 0.12, 0.10]   # ENG is the biggest org
LOCATIONS = ["Kochi", "Bengaluru", "Chennai", "Hyderabad", "Pune"]
SUPPLIERS = ["TechStaff Pvt Ltd", "InfoBridge Solutions", "CloudNine Consulting",
             "Vertex Talent", "BlueOrbit Services"]
CONTRACT_TITLES = {
    "ENG": ["Backend Developer", "Java Developer", "DevOps Engineer", "Data Engineer", "QA Automation Engineer"],
    "FIN": ["Finance Associate", "Accounts Analyst"],
    "HR": ["Recruitment Coordinator"],
    "SAL": ["Inside Sales Associate"],
    "OPS": ["Operations Support Analyst", "Logistics Coordinator"],
    "MKT": ["Content Specialist", "Campaign Analyst"],
}

# ---------------------------------------------------------------- helpers
def iso_d(d):
    return d.strftime("%Y-%m-%d")

def iso_ts(d, h=9, m=0):
    return dt.datetime(d.year, d.month, d.day, h, m, 0).strftime("%Y-%m-%d %H:%M:%S")

def us_d(d):
    return d.strftime("%m/%d/%Y")

def us_ts(d, h=10, m=0):
    return dt.datetime(d.year, d.month, d.day, h, m).strftime("%m/%d/%Y %H:%M")

def dmy_ts(d, h=18, m=0):
    return dt.datetime(d.year, d.month, d.day, h, m).strftime("%d-%m-%Y %H:%M")

def month_starts(start, end):
    """First day of every month in the window."""
    out, cur = [], dt.date(start.year, start.month, 1)
    while cur <= end:
        out.append(cur)
        cur = dt.date(cur.year + (cur.month == 12), (cur.month % 12) + 1, 1)
    return out

def day_in_month(rnd, m):
    """A random day inside month m, clamped to the window."""
    nxt = dt.date(m.year + (m.month == 12), (m.month % 12) + 1, 1)
    last = (nxt - dt.timedelta(days=1)).day
    d = dt.date(m.year, m.month, rnd.randint(1, last))
    return max(WINDOW_START, min(d, WINDOW_END))


class Generator:
    def __init__(self, seed, n_employees, n_contractors):
        self.rnd = random.Random(seed)
        self.n_employees = n_employees
        self.n_contractors = n_contractors
        self.used_emails = set()
        self.emp_seq = 1000
        self.wrk_seq = 5000
        self.badge_seq = 0
        self.employees = []       # live employee records
        self.contractors = []
        self.badges = []
        self.hrms_rows = []       # (version_ts, tuple-of-source-columns)
        self.beeline_rows = []
        self.smarttime_rows = []
        self.notes = []           # seeded scenarios, for the dataset summary

    # ---------------- identity
    def new_person(self):
        r = self.rnd
        f, l = r.choice(FIRST_NAMES), r.choice(LAST_NAMES)
        base = f"{f.lower()}.{l.lower()}"
        email, n = f"{base}@acme.com", 2
        while email in self.used_emails:
            email, n = f"{base}{n}@acme.com", n + 1
        self.used_emails.add(email)
        return f, l, email

    # ---------------- source formatting quirks (what intrm has to clean up)
    def q_empno(self, no):
        return f" {no.lower()} " if self.rnd.random() < 0.03 else no

    def q_email_hrms(self, e):
        r = self.rnd.random()
        if r < 0.05:
            return ".".join(p.capitalize() for p in e.split("@")[0].split(".")) + "@acme.com "
        if r < 0.08:
            return e.upper()
        return e

    def q_date_hrms(self, d):
        s = iso_d(d)
        return s.replace("-", "/") if self.rnd.random() < 0.06 else s

    def q_name_beeline(self, first, last):
        s = f"{last}, {first}"
        return s.upper() if self.rnd.random() < 0.15 else s

    def q_email_beeline(self, e):
        r = self.rnd.random()
        if r < 0.07:
            return " " + e.upper()
        if r < 0.12:
            return ".".join(p.capitalize() for p in e.split("@")[0].split(".")) + "@ACME.com"
        return e

    def q_rate(self, rate, currency):
        return f"{rate:,.2f}" if currency == "INR" else f"${rate:,.2f}"

    def q_ot(self, eligible):
        return self.rnd.choice(["Y", "1", "TRUE", "YES"]) if eligible else self.rnd.choice(["N", "0", "FALSE"])

    # ---------------- emit one version row per source
    def emit_hrms(self, e, when, hour=9):
        self.hrms_rows.append((iso_ts(when, hour), (
            "" if e.get("break_empno") else self.q_empno(e["no"]),
            e["first"], e["last"],
            "" if e.get("break_email") else self.q_email_hrms(e["email"]),
            self.q_date_hrms(e["hire"]),
            iso_d(e["term"]) if e["term"] else None,
            e["status"], e["etype"], e["dept"], DEPT_NAME[e["dept"]],
            e["title"], e["grade"], e["mgr"], e["loc"],
            iso_ts(when, hour),
        )))

    def emit_beeline(self, c, when, hour=10):
        self.beeline_rows.append((iso_ts(when, hour), (
            c["id"], self.q_name_beeline(c["first"], c["last"]),
            "" if c.get("break_email") else self.q_email_beeline(c["email"]),
            c["supplier"], c["wo"], self.q_rate(c["rate"], c["ccy"]), c["ccy"],
            us_d(c["start"]), us_d(c["end"]), c["status"], c["cc"],
            c["mgr_email"], c["title"], us_ts(when, hour),
        )))

    def emit_badge(self, b, when, hour=18):
        self.smarttime_rows.append((iso_ts(when, hour), (
            b["id"], b["emp_code"], b["display"], b["email"], b["shift"], b["tz"],
            str(b["hours"]), self.q_ot(b["ot"]), b["pay_group"],
            dmy_ts(b["last_punch"], self.rnd.randint(17, 21), self.rnd.choice([0, 15, 30, 45])),
            1 if b["enabled"] else 0, dmy_ts(when, hour),
        )))

    # ---------------- record factories
    def make_employee(self, hire, dept=None, step=None, email=None, first=None, last=None):
        r = self.rnd
        self.emp_seq += 1
        if email is None:
            first, last, email = self.new_person()
        dept = dept or r.choices(DEPTS, weights=DEPT_WEIGHTS)[0]
        ladder = LADDER[dept]
        step = step if step is not None else r.randrange(0, min(4, len(ladder)))
        title, grade = ladder[step]
        return {
            "no": f"E{self.emp_seq}", "first": first, "last": last, "email": email,
            "hire": hire, "dept": dept, "step": step, "title": title, "grade": grade,
            "loc": r.choice(LOCATIONS), "etype": "PT" if r.random() < 0.08 else "FT",
            "mgr": None, "status": "A", "term": None,
        }

    def make_contractor(self, start, dept=None):
        r = self.rnd
        self.wrk_seq += 1
        first, last, email = self.new_person()
        dept = dept or r.choices(DEPTS, weights=DEPT_WEIGHTS)[0]
        ccy = "INR" if r.random() < 0.35 else "USD"
        rate = round(r.uniform(2500, 7500), 2) if ccy == "INR" else round(r.uniform(28, 85), 2)
        months = r.choice([6, 9, 12, 12, 18, 24])
        return {
            "id": f"BL-{self.wrk_seq}", "first": first, "last": last, "email": email,
            "supplier": r.choice(SUPPLIERS), "wo": f"WO-{88000 + self.wrk_seq}",
            "rate": rate, "ccy": ccy, "start": start,
            "end": start + dt.timedelta(days=30 * months), "status": "Active",
            "cc": f"{dept}-{r.choice([100, 200, 300, 400])}", "dept": dept,
            "mgr_email": None, "title": r.choice(CONTRACT_TITLES[dept]),
        }

    def make_badge(self, emp_code, first, last, email, when, contractor=False, no_email=False):
        r = self.rnd
        self.badge_seq += 1
        shift = r.choices(["GEN", "NIGHT", "HALF"], weights=[0.72, 0.18, 0.10])[0]
        return {
            "id": f"ST-{self.badge_seq:05d}", "emp_code": emp_code,
            "display": f"{first} {last}".upper(), "email": None if no_email else email,
            "shift": shift, "tz": "Asia/Kolkata",
            "hours": {"GEN": 40, "NIGHT": 45, "HALF": 20}[shift],
            "ot": (r.random() < 0.75) if contractor else (r.random() < 0.35),
            "pay_group": "CONTRACT" if contractor else "IN-MONTHLY",
            "last_punch": when, "enabled": True,
        }

    # ---------------- the year
    def build(self):
        r = self.rnd
        # ---- opening workforce, hired over the previous 9 years
        for _ in range(self.n_employees):
            hire = WINDOW_START - dt.timedelta(days=r.randint(30, 3300))
            self.employees.append(self.make_employee(hire))

        # managers: per department, the most senior person leads, next few manage
        for dept in DEPTS:
            team = [e for e in self.employees if e["dept"] == dept]
            if not team:
                continue
            team.sort(key=lambda e: (-e["step"], e["hire"]))
            ladder = LADDER[dept]
            director = team[0]
            director["step"] = len(ladder) - 1
            director["title"], director["grade"] = ladder[-1]
            managers = team[1:1 + max(1, len(team) // 25)]
            for m in managers:
                m["step"] = max(m["step"], len(ladder) - 2)
                m["title"], m["grade"] = ladder[m["step"]]
                m["mgr"] = director["no"]
            for e in team[1 + len(managers):]:
                e["mgr"] = r.choice(managers)["no"] if managers else director["no"]

        # ---- seeded data-quality cases (each one exercises a documented rule)
        broken = r.sample(self.employees, 3)
        broken[0]["break_email"] = True       # dropped at intrm: no email
        broken[1]["break_email"] = True
        broken[2]["break_empno"] = True       # dropped at intrm: no employee_number
        self.notes.append(f"HRMS rejects: {broken[0]['no']}, {broken[1]['no']} (no email); "
                          f"{broken[2]['no']} (no employee number)")

        # opening HRMS versions: the record was last touched when the person was hired
        for e in self.employees:
            self.emit_hrms(e, max(e["hire"], WINDOW_START - dt.timedelta(days=400)))

        # ---- opening contractor population
        for _ in range(self.n_contractors):
            start = WINDOW_START - dt.timedelta(days=r.randint(20, 500))
            self.contractors.append(self.make_contractor(start))
        for c in self.contractors:
            mgrs = [e for e in self.employees if e["dept"] == c["dept"] and e["step"] >= len(LADDER[c["dept"]]) - 2]
            c["mgr_email"] = (r.choice(mgrs)["email"] if mgrs else self.employees[0]["email"])
        bad_bl = r.sample(self.contractors, 2)
        for c in bad_bl:
            c["break_email"] = True           # dropped at intrm: no email
        self.notes.append(f"Beeline rejects: {bad_bl[0]['id']}, {bad_bl[1]['id']} (no email)")
        for c in self.contractors:
            self.emit_beeline(c, max(c["start"], WINDOW_START - dt.timedelta(days=400)))

        # ---- opening badges (not everyone has one -> ACTIVE_WITHOUT_BADGE)
        base_day = WINDOW_START - dt.timedelta(days=5)
        no_email_badges = 0
        for e in self.employees:
            if r.random() < 0.86:
                no_email = r.random() < 0.08
                no_email_badges += no_email
                b = self.make_badge(e["no"], e["first"], e["last"], e["email"], base_day, no_email=no_email)
                b["person"] = e["email"]
                self.badges.append(b)
                self.emit_badge(b, base_day)
        for c in self.contractors:
            if r.random() < 0.90:
                b = self.make_badge(c["id"], c["first"], c["last"], c["email"], base_day, contractor=True)
                b["person"] = c["email"]
                self.badges.append(b)
                self.emit_badge(b, base_day)
        self.notes.append(f"Badges with no email (resolved via emp_code): {no_email_badges}")

        # badge-only people: in no HR or vendor system -> TIMEKEEPING_ONLY
        for i in range(8):
            f, l, email = self.new_person()
            b = self.make_badge(f"CON-{70 + i}", f, l, email, base_day, contractor=True)
            b["person"] = email
            self.badges.append(b)
            self.emit_badge(b, base_day)
        self.notes.append("Timekeeping-only badges (CON-70..CON-77): 8")

        # unidentifiable badges: no email and emp_code matches nothing -> rejected
        for i in range(5):
            b = self.make_badge(f"TMP-{90 + i}", "Visitor", f"Pass{i}", None, base_day, no_email=True)
            b["person"] = None
            self.badges.append(b)
            self.emit_badge(b, base_day)
        self.notes.append("Unresolvable badges (TMP-90..TMP-94): 5 -> dropped at intrm")

        # same human, different email in HRMS vs Beeline -> lands as TWO people
        for i in range(2):
            src = r.choice([e for e in self.employees if not e.get("break_email")])
            self.wrk_seq += 1
            alias = src["email"].replace(".", "", 1)
            self.used_emails.add(alias)
            c = {
                "id": f"BL-{self.wrk_seq}", "first": src["first"], "last": src["last"], "email": alias,
                "supplier": r.choice(SUPPLIERS), "wo": f"WO-{88000 + self.wrk_seq}",
                "rate": round(r.uniform(30, 70), 2), "ccy": "USD",
                "start": WINDOW_START - dt.timedelta(days=60),
                "end": WINDOW_START + dt.timedelta(days=200), "status": "Active",
                "cc": f"{src['dept']}-200", "dept": src["dept"],
                "mgr_email": src["email"], "title": r.choice(CONTRACT_TITLES[src["dept"]]),
            }
            self.contractors.append(c)
            self.emit_beeline(c, WINDOW_START - dt.timedelta(days=60))
            self.notes.append(f"Email mismatch: {src['no']} is {src['email']} in HRMS "
                              f"but {alias} in Beeline ({c['id']}) -> two dimension rows")

        # ---- month-by-month events
        for month in month_starts(WINDOW_START, WINDOW_END):
            self.run_month(month)

        return self

    def run_month(self, month):
        r = self.rnd
        actives = [e for e in self.employees if e["status"] in ("A", "L") and not e.get("break_email")]

        # new hires (3-7 a month)
        for _ in range(r.randint(3, 7)):
            day = day_in_month(r, month)
            e = self.make_employee(day, step=r.randrange(0, 3))
            peers = [x for x in self.employees if x["dept"] == e["dept"] and x["step"] >= len(LADDER[e["dept"]]) - 2]
            e["mgr"] = r.choice(peers)["no"] if peers else None
            self.employees.append(e)
            self.emit_hrms(e, day)
            if r.random() < 0.88:                      # badge issued on or just after day one
                bd = day + dt.timedelta(days=r.randint(0, 3))
                b = self.make_badge(e["no"], e["first"], e["last"], e["email"], bd)
                b["person"] = e["email"]
                self.badges.append(b)
                self.emit_badge(b, bd)

        # terminations (1-3 a month)
        for e in r.sample(actives, min(len(actives), r.randint(1, 3))):
            day = day_in_month(r, month)
            e["status"], e["term"] = "T", day
            self.emit_hrms(e, day)
            for b in self.badges:
                if b.get("person") == e["email"] and b["enabled"]:
                    if r.random() < 0.80:              # 20% of leavers keep a live badge
                        b["enabled"] = False
                        self.emit_badge(b, day + dt.timedelta(days=r.randint(0, 2)))

        # promotions (2-5 a month): title + grade move up one rung
        promo_pool = [e for e in actives if e["step"] < len(LADDER[e["dept"]]) - 2]
        for e in r.sample(promo_pool, min(len(promo_pool), r.randint(2, 5))):
            day = day_in_month(r, month)
            e["step"] += 1
            e["title"], e["grade"] = LADDER[e["dept"]][e["step"]]
            self.emit_hrms(e, day)

        # department transfers (0-2 a month)
        for e in r.sample(actives, min(len(actives), r.randint(0, 2))):
            day = day_in_month(r, month)
            new_dept = r.choice([d for d in DEPTS if d != e["dept"]])
            e["dept"] = new_dept
            e["step"] = min(e["step"], len(LADDER[new_dept]) - 1)
            e["title"], e["grade"] = LADDER[new_dept][e["step"]]
            peers = [x for x in self.employees if x["dept"] == new_dept and x["step"] >= len(LADDER[new_dept]) - 2]
            e["mgr"] = r.choice(peers)["no"] if peers else None
            self.emit_hrms(e, day)

        # relocations (0-2 a month)
        for e in r.sample(actives, min(len(actives), r.randint(0, 2))):
            day = day_in_month(r, month)
            e["loc"] = r.choice([l for l in LOCATIONS if l != e["loc"]])
            self.emit_hrms(e, day)

        # leave starts and returns
        for e in r.sample(actives, min(len(actives), r.randint(0, 2))):
            if e["status"] == "A":
                day = day_in_month(r, month)
                e["status"] = "L"
                self.emit_hrms(e, day)
        for e in [x for x in self.employees if x["status"] == "L"]:
            if r.random() < 0.35:
                day = day_in_month(r, month)
                e["status"] = "A"
                self.emit_hrms(e, day)

        # ---- contractors
        live = [c for c in self.contractors if c["status"] == "Active" and not c.get("break_email")]

        for _ in range(r.randint(1, 3)):               # new assignments
            day = day_in_month(r, month)
            c = self.make_contractor(day)
            mgrs = [e for e in self.employees if e["dept"] == c["dept"] and e["step"] >= len(LADDER[c["dept"]]) - 2]
            c["mgr_email"] = r.choice(mgrs)["email"] if mgrs else self.employees[0]["email"]
            if r.random() < 0.25:                      # some are raised before they start
                c["status"] = "Pending"
                c["start"] = day + dt.timedelta(days=r.randint(10, 45))
            self.contractors.append(c)
            self.emit_beeline(c, day)
            if c["status"] == "Active" and r.random() < 0.9:
                b = self.make_badge(c["id"], c["first"], c["last"], c["email"], day, contractor=True)
                b["person"] = c["email"]
                self.badges.append(b)
                self.emit_badge(b, day)

        for c in [x for x in self.contractors if x["status"] == "Pending"]:
            if c["start"] <= day_in_month(r, month):   # pending -> active once started
                c["status"] = "Active"
                self.emit_beeline(c, c["start"])

        for c in r.sample(live, min(len(live), r.randint(2, 5))):   # rate revisions
            day = day_in_month(r, month)
            c["rate"] = round(c["rate"] * r.uniform(1.03, 1.12), 2)
            self.emit_beeline(c, day)

        for c in r.sample(live, min(len(live), r.randint(0, 2))):   # extensions
            day = day_in_month(r, month)
            c["end"] = c["end"] + dt.timedelta(days=r.choice([90, 180, 365]))
            self.emit_beeline(c, day)

        for c in r.sample(live, min(len(live), r.randint(1, 3))):   # assignment ends
            day = day_in_month(r, month)
            c["status"], c["end"] = "Ended", day
            self.emit_beeline(c, day)
            for b in self.badges:
                if b.get("person") == c["email"] and b["enabled"] and r.random() < 0.85:
                    b["enabled"] = False
                    self.emit_badge(b, day)

        # contractor -> employee conversions (0-1 a month), same email in both systems
        if live and r.random() < 0.55:
            c = r.choice(live)
            day = day_in_month(r, month)
            c["status"], c["end"] = "Ended", day
            self.emit_beeline(c, day)
            e = self.make_employee(day, dept=c["dept"], step=1,
                                   email=c["email"], first=c["first"], last=c["last"])
            peers = [x for x in self.employees if x["dept"] == e["dept"] and x["step"] >= len(LADDER[e["dept"]]) - 2]
            e["mgr"] = r.choice(peers)["no"] if peers else None
            self.employees.append(e)
            self.emit_hrms(e, day)
            for b in self.badges:                      # old contractor badge is disabled
                if b.get("person") == c["email"] and b["enabled"]:
                    b["enabled"] = False
                    self.emit_badge(b, day)
            nb = self.make_badge(e["no"], e["first"], e["last"], e["email"], day)
            nb["person"] = e["email"]
            self.badges.append(nb)
            self.emit_badge(nb, day)                   # new employee badge, enabled

        # ---- routine badge traffic: a sample of live badges clock in this month
        for b in self.badges:
            if b["enabled"] and r.random() < 0.5:
                day = day_in_month(r, month)
                b["last_punch"] = day
                self.emit_badge(b, day)


# ---------------------------------------------------------------- persistence
HRMS_COLS = ("employee_number first_name last_name work_email hire_date termination_date "
             "employment_status employment_type department_code department_name job_title "
             "job_grade manager_employee_number work_location updated_at").split()
BEELINE_COLS = ("worker_id worker_name email_address supplier_name work_order_id bill_rate currency "
                "assignment_start assignment_end worker_status cost_center hiring_manager_email "
                "job_posting_title last_modified").split()
SMARTTIME_COLS = ("badge_id emp_code display_name email shift_code time_zone sched_hours_week "
                  "ot_eligible pay_group last_punch is_enabled modified_on").split()

MASTER_TABLES = {
    "mst_hrms_employee": HRMS_COLS,
    "mst_beeline_worker": BEELINE_COLS,
    "mst_smarttime_employee": SMARTTIME_COLS,
}


def write_master(gen):
    os.makedirs(os.path.dirname(MASTER), exist_ok=True)
    if os.path.exists(MASTER):
        os.remove(MASTER)
    con = sqlite3.connect(MASTER)
    with con:
        for table, cols in MASTER_TABLES.items():
            con.execute(f"DROP TABLE IF EXISTS {table}")
            con.execute(f"CREATE TABLE {table} (version_ts TEXT NOT NULL, "
                        + ", ".join(f"{c} TEXT" for c in cols) + ")")
            con.execute(f"CREATE INDEX ix_{table}_v ON {table}(version_ts)")
        for table, rows in (("mst_hrms_employee", gen.hrms_rows),
                            ("mst_beeline_worker", gen.beeline_rows),
                            ("mst_smarttime_employee", gen.smarttime_rows)):
            cols = MASTER_TABLES[table]
            ph = ",".join("?" * (len(cols) + 1))
            con.executemany(f"INSERT INTO {table} VALUES ({ph})",
                            [(v,) + tuple(row) for v, row in rows])
    con.close()


def main():
    gen = Generator(SEED, N_EMPLOYEES, N_CONTRACTORS).build()
    write_master(gen)
    print(f"  master -> {os.path.relpath(MASTER, ROOT)}")
    print(f"  HRMS versions      : {len(gen.hrms_rows):>6}")
    print(f"  Beeline versions   : {len(gen.beeline_rows):>6}")
    print(f"  SmartTime versions : {len(gen.smarttime_rows):>6}")
    print(f"  people created     : {len(gen.employees)} employees, "
          f"{len(gen.contractors)} contractors, {len(gen.badges)} badges")
    for n in gen.notes:
        print(f"    - {n}")
    return gen


if __name__ == "__main__":
    main()
