"""
Run this once to seed the HR admin user into the database.
Usage: python seed_hr.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from utils.db import run_write, get_employee_by_email
from utils.auth import hash_password

HR_EMAIL = "hr@company.com"
HR_PASSWORD = "HRAdmin@123"  # Change this if you want

def seed():
    # 1. Ensure password_hash column exists (run this SQL manually if it fails)
    try:
        run_write("ALTER TABLE employees ADD COLUMN password_hash VARCHAR(255) NULL")
        print("Added password_hash column.")
    except Exception as e:
        if "Duplicate column" in str(e) or "1060" in str(e):
            print("password_hash column already exists, skipping.")
        else:
            print(f"Column alter note: {e}")

    # 2. Check if HR user already exists
    existing = get_employee_by_email(HR_EMAIL)
    pw_hash = hash_password(HR_PASSWORD)

    if not existing.empty:
        emp_id = int(existing.iloc[0]["employee_id"])
        run_write("UPDATE employees SET password_hash = %s WHERE employee_id = %s", (pw_hash, emp_id))
        print(f"Updated password for existing HR user: {HR_EMAIL}")
    else:
        from utils.db import create_employee
        from datetime import date
        emp_id = create_employee({
            "email": HR_EMAIL,
            "full_name": "HR Admin",
            "current_department": "HR",
            "current_role": "HR Manager",
            "hire_date": date.today().strftime("%Y-%m-%d"),
            "location": "Remote",
            "employee_level": "Director",
            "manager_id": None,
        })
        run_write("UPDATE employees SET password_hash = %s WHERE employee_id = %s", (pw_hash, emp_id))
        print(f"Created HR user: {HR_EMAIL}")

    print(f"\nLogin credentials:")
    print(f"  Email:    {HR_EMAIL}")
    print(f"  Password: {HR_PASSWORD}")

if __name__ == "__main__":
    seed()
