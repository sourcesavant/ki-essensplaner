"""Database migration: Add servings column to recipes table.

This migration adds the 'servings' column to the recipes table.
Existing recipes will have servings=NULL, which will be treated as default (2).

Issue #30: Portionenanzahl & automatische Rezept-Skalierung
"""

import sqlite3
from pathlib import Path

from src.core.config import DB_PATH


def migrate():
    """Add servings column to recipes table."""
    print("Starting migration: Add servings column...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(recipes)")
        columns = [row[1] for row in cursor.fetchall()]

        if "servings" in columns:
            print("  Column 'servings' already exists. Skipping migration.")
            return

        # Add servings column
        cursor.execute("ALTER TABLE recipes ADD COLUMN servings INTEGER")
        conn.commit()

        print("  [OK] Added 'servings' column to recipes table")

        # Count recipes
        cursor.execute("SELECT COUNT(*) FROM recipes")
        count = cursor.fetchone()[0]
        print(f"  [OK] Migration complete. {count} existing recipes will use default (2 servings)")

    except Exception as e:
        conn.rollback()
        print(f"  [ERROR] Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
