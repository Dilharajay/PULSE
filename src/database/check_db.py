"""Inspect statistics for the Letterboxd SQLite database."""

import os
import sys
import sqlite3
from pathlib import Path

# Resolve project root (two levels above src/database/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "raw" / "letterboxd.db"


def print_stats(db_path: str | Path = DEFAULT_DB_PATH):
    target_path = Path(db_path).resolve()
    print(f"Checking database at: {target_path}")

    if not target_path.exists():
        print(f"Error: Database file does not exist at '{target_path}'")
        return

    try:
        conn = sqlite3.connect(str(target_path))
        c = conn.cursor()

        tables = ["films", "cast_members", "crew_members", "film_details", "film_genres", "film_reviews"]
        print("-" * 40)
        for table in tables:
            try:
                count = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"{table.replace('_', ' ').title():<20}: {count:>10,}")
            except sqlite3.OperationalError:
                print(f"{table.replace('_', ' ').title():<20}: [Table not found]")
        print("-" * 40)

        conn.close()
    except Exception as e:
        print(f"Failed to query database: {e}")


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_PATH
    print_stats(db_path)


if __name__ == "__main__":
    main()
