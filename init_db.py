#!/usr/bin/env python3
import sys
import os
import subprocess

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    print("Initializing database with Alembic migrations...")
    try:
        # Run alembic upgrade to ensure database is up to date
        result = subprocess.run([
            sys.executable, '-m', 'alembic', 'upgrade', 'head'
        ], capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__)))
        
        if result.returncode == 0:
            print("✅ Database initialized successfully!")
            print("📝 All migrations applied.")
        else:
            print(f"❌ Error running migrations: {result.stderr}")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
