#!/usr/bin/env python3
import sys
import os
import subprocess

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """Initialize database - try migrations first, fallback to direct table creation."""
    script_dir = os.path.dirname(os.path.abspath(__file__))

    print("🗄️  Initializing database...")

    try:
        # Try migrations first
        result = subprocess.run([
            sys.executable, '-m', 'alembic', 'upgrade', 'head'
        ], capture_output=True, text=True, cwd=script_dir)

        if result.returncode == 0:
            print("✅ Database initialized with migrations")
            return
        else:
            print("⚠️  Migrations failed, creating tables directly...")
            # If migrations fail, create tables directly from models
            from core.db import Base, engine
            from core import models  # Import to register all models

            Base.metadata.create_all(bind=engine)
            print("✅ Database tables created")

            # Stamp database with latest migration
            result = subprocess.run([
                sys.executable, '-m', 'alembic', 'stamp', 'head'
            ], capture_output=True, text=True, cwd=script_dir)

            if result.returncode == 0:
                print("✅ Database stamped with latest migration")
            else:
                print("⚠️  Warning: Could not stamp database (non-critical)")

    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
