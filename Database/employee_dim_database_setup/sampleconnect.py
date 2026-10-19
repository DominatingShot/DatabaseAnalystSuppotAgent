#!/usr/bin/env python3
"""Peek inside DB1: list its tables, then the columns of hrms_employee.

    python sampleconnect.py
"""
import os
import sqlite3

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db", "db1_hrms.db")

con = sqlite3.connect(DB)
print(con.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall())
print([c[1] for c in con.execute("PRAGMA table_info(hrms_employee)")])
con.close()
