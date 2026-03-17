"""
Run this script to set passwords for existing employees who have NULL password_hash.
Each employee gets a default password of:  Welcome@<employee_id>

Example: employee_id=5  →  password = Welcome@5

After running, employees can log in and change their password from their profile.

Usage:
    python set_existing_passwords.py

Optional — set a single uniform password for all:
    python set_existing_passwords.py --password "MyPass@123"
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from utils.db import run_query, run_write
from utils.auth import hash_password

def main():
    uniform_password = None
    if "--password" in sys.argv:
        idx = sys.argv.index("--password")
        if idx + 1 < len(sys.argv):
            uniform_password = sys.argv[idx + 1]

    # Fetch employees with NULL or empty password_hash
    df = run_query("""
        SELECT employee_id, full_name, email
        FROM employees
        WHERE password_hash IS NULL OR password_hash = ''
        ORDER BY employee_id
    """)

    if df.empty:
        print("No employees with missing passwords found. All good!")
        return

    print(f"Found {len(df)} employees with no password set.\n")
    print(f"{'ID':<6} {'Name':<30} {'Email':<35} {'Password'}")
    print("-" * 90)

    for _, row in df.iterrows():
        emp_id = int(row["employee_id"])
        password = uniform_password if uniform_password else f"Welcome@{emp_id}"
        pw_hash = hash_password(password)
        run_write(
            "UPDATE employees SET password_hash = %s WHERE employee_id = %s",
            (pw_hash, emp_id)
        )
        print(f"{emp_id:<6} {str(row['full_name']):<30} {str(row['email']):<35} {password}")

    print(f"\nDone. {len(df)} employees updated.")
    print("\nEmployees can log in with the password shown above.")
    if not uniform_password:
        print("Default pattern: Welcome@<employee_id>  (e.g. employee_id=3 → Welcome@3)")

if __name__ == "__main__":
    main()
