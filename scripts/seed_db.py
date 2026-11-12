"""Load data/seed/*.csv into the database (DATABASE_URL, default SQLite at data/ap.db).

Usage:
    python scripts/seed_db.py            reseed vendors and POs, keep runs
    python scripts/seed_db.py --reset    also wipe all runs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import get_settings  # noqa: E402
from app.db import session_factory  # noqa: E402
from app.seed import seed_master_data, wipe_runs  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="also delete all runs")
    args = parser.parse_args()
    with session_factory()() as session:
        if args.reset:
            print(f"Removed {wipe_runs(session)} run(s)")
        print(f"Seeded {seed_master_data(session, get_settings().seed_dir)} into {get_settings().database_url}")


if __name__ == "__main__":
    main()
