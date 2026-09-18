"""Draait alle checks eenmalig, schrijft een snapshot naar SQLite en
alerteert (via ntfy.sh) bij nieuwe FAILs.

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
from app.notify import send_ntfy


def main() -> None:
    history.init_db()

    sections = {
        "Diensten": gather_service_statuses,
        "Pipelines": gather_pipeline_statuses,
        "Datakwaliteit": gather_data_quality_statuses,
    }

    new_failures: list[tuple[str, object]] = []
    for key, fetch_fn in sections.items():
        entries = fetch_fn()
        history.record_snapshot(key, entries)
        newly_failed = history.detect_new_failures(entries)
        new_failures.extend((key, e) for e in newly_failed)
        print(f"{key}: {len(entries)} checks opgeslagen, {len(newly_failed)} nieuwe FAIL(s)")

    if new_failures:
        lines = [f"- [{section}] {entry.label}: {entry.detail}" for section, entry in new_failures]
        sent = send_ntfy(
            title=f"Databeheer Cockpit: {len(new_failures)} nieuw(e) probleem/problemen",
            message="\n".join(lines),
            priority="high",
            tags="rotating_light",
        )
        if sent:
            print(f"Alert verstuurd voor {len(new_failures)} nieuwe FAIL(s).")
        else:
            print(f"{len(new_failures)} nieuwe FAIL(s), maar NTFY_TOPIC niet gezet - alert overgeslagen.")


if __name__ == "__main__":
    main()
