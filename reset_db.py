import os
import sqlite3
import sys

# Add current directory to path so we can import database
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import DB_PATH

def reset():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    tables = [
        "applications",
        "interview_answers",
        "interview_sessions",
        "job_questions",
        "jobs",
        "certificates",
        "profiles",
        "company_profiles",
        "users"
    ]

    for table in tables:
        try:
            cur.execute(f"DELETE FROM {table}")
            print(f"Cleared {table}")
        except Exception as e:
            print(f"Skipped {table}: {e}")

    conn.commit()
    conn.close()
    print("Database reset completed successfully.")

if __name__ == "__main__":
    reset()