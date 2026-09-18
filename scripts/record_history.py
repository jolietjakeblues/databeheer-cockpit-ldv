"""Draait alle checks eenmalig en schrijft een snapshot naar SQLite.

Bedoeld om periodiek via een GitHub Action te draaien (zie
.github/workflows/record-history.yml), zodat er ook trendhistorie bestaat
voor omgevingen zonder persistente schijf (bv. Render free tier), die de
resulterende data/history.sqlite read-only uitlezen via HISTORY_REMOTE_URL.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import history
from app.checks.data_quality import gather_data_quality_statuses
from app.checks.pipelines import gather_pipeline_statuses
from app.checks.services import gather_service_statuses


def main() -> None:
    history.init_db()

    sections = {
        "Diensten": gather_service_statuses,
        "Pipelines": gather_pipeline_statuses,
        "Datakwaliteit": gather_data_quality_statuses,
    }

    for key, fetch_fn in sections.items():
        entries = fetch_fn()
        history.record_snapshot(key, entries)
        print(f"{key}: {len(entries)} checks opgeslagen")


if __name__ == "__main__":
    main()
