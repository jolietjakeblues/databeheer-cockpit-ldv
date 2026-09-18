"""Rendert een statische snapshot van de cockpit voor GitHub Pages.

Draait als eenmalige batch (geen live server, geen caching) - bedoeld om
periodiek via een GitHub Action te draaien. Schrijft dezelfde soort
snapshot naar SQLite als de live app, zodat de Trends-sparklines ook op de
statische pagina historie opbouwen.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app import history
from app.cache import Section
from app.checks.data_quality import gather_data_quality_statuses
from app.checks.pipelines import gather_pipeline_statuses
from app.checks.services import gather_service_statuses
from app.config import load_sources
from app.status import now_cet
from app.summary import build_trends, sorted_entries, summarize

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / "docs"


def _build_section(title: str, fetch_fn) -> Section:
    entries = fetch_fn()
    return Section(title=title, fetch=fetch_fn, entries=entries, last_refreshed=1)


def main() -> None:
    history.init_db()
    cfg = load_sources()

    sections = {
        "Diensten": _build_section("Diensten", gather_service_statuses),
        "Pipelines": _build_section("Pipelines", gather_pipeline_statuses),
        "Datakwaliteit": _build_section("Datakwaliteit", gather_data_quality_statuses),
    }

    for key, section in sections.items():
        history.record_snapshot(key, section.entries)

    counts = summarize(sections)
    total = sum(counts.values()) or 1
    trends = build_trends(cfg.get("triplydb_datasets", []))

    env = Environment(
        loader=FileSystemLoader(BASE_DIR / "app" / "templates"),
        autoescape=select_autoescape(),
    )
    template = env.get_template("dashboard.html")
    html = template.render(
        sections=sections,
        sorted_entries=sorted_entries,
        counts=counts,
        total=total,
        trends=trends,
        static=True,
        generated_at=now_cet(),
    )

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")
    (OUT_DIR / "style.css").write_text(
        (BASE_DIR / "static" / "style.css").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (OUT_DIR / ".nojekyll").write_text("")

    print(f"Statische snapshot geschreven naar {OUT_DIR}")


if __name__ == "__main__":
    main()
