import sqlite3

conn = sqlite3.connect(r"C:\Users\aksha\Desktop\DataSupportAgent\Database\employee_dim_database_setup\db\db1_hrms.db")   # path to your .db file
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print(cur.fetchall())

# cur.execute("SELECT * from hrms_employee")
# print(cur.fetchall())


cur.execute("PRAGMA table_info(hrms_employee)")
l = cur.fetchall()
print([column[1] for column in l])  # Print column names
#cur.execute("SELECT * from hrms_employee")
#print(cur.fetchall())
def execute_sql(query, DB_Name):