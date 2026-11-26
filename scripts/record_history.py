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
from app.alerts import blind_entries, describe_blindness
from app.checks.data_quality import gather_data_quality_statuses
from app.checks.pipelines import gather_pipeline_statuses
from app.checks.poolparty import gather_poolparty_statuses
from app.checks.services import gather_service_statuses
from app.config import load_sources
from app.notify import send_ntfy

DEFAULT_UNKNOWN_THRESHOLD = 5


def check_blindness(all_entries) -> None:
    """Alert zodra de cockpit zelf blind is (veel checks tegelijk onbeoordeelbaar),
    en een herstelbericht zodra het weer werkt. Alleen bij een overgang, niet elke run."""
    threshold = load_sources().get("alerts", {}).get("unknown_threshold", DEFAULT_UNKNOWN_THRESHOLD)
    blind = blind_entries(all_entries)
    is_blind = len(blind) >= threshold
    was_blind = history.get_state("blind", "0") == "1"
    print(f"Onbeoordeelbaar: {len(blind)} checks (drempel {threshold}) - blind: {is_blind}")

    if is_blind and not was_blind:
        sent = send_ntfy(
            title=f"Databeheer Cockpit is blind: {len(blind)} checks onbeoordeelbaar",
            message=describe_blindness(blind) + "\n\nDe cockpit kan niet zien of het goed gaat: controleer tokens/credentials.",
            priority="high",
            tags="see_no_evil",
        )
        print("Blind-alert verstuurd." if sent else "Blind-alert overgeslagen (NTFY_TOPIC niet gezet).")
    elif was_blind and not is_blind:
        sent = send_ntfy(
            title="Databeheer Cockpit ziet weer alles",
            message=f"Nog {len(blind)} onbeoordeelbare check(s), onder de drempel van {threshold}.",
            priority="default",
            tags="white_check_mark",
        )
        print("Herstelbericht verstuurd." if sent else "Herstelbericht overgeslagen (NTFY_TOPIC niet gezet).")
    history.set_state("blind", "1" if is_blind else "0")


def main() -> None:
    history.init_db()

    sections = {
        "Diensten": gather_service_statuses,
        "PoolParty": gather_poolparty_statuses,
        "Pipelines": gather_pipeline_statuses,
        "Datakwaliteit": gather_data_quality_statuses,
    }

    new_failures: list[tuple[str, object]] = []
    all_entries: list[tuple[str, object]] = []
    for key, fetch_fn in sections.items():
        entries = fetch_fn()
        history.record_snapshot(key, entries)
        newly_failed = history.detect_new_failures(entries)
        new_failures.extend((key, e) for e in newly_failed)
        all_entries.extend((key, e) for e in entries)
        print(f"{key}: {len(entries)} checks opgeslagen, {len(newly_failed)} nieuwe FAIL(s)")

    check_blindness(all_entries)

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
