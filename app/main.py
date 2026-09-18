import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app import history
from app.cache import DashboardCache
from app.checks.data_quality import gather_data_quality_statuses
from app.checks.pipelines import gather_pipeline_statuses
from app.checks.services import gather_service_statuses
from app.config import load_sources
from app.summary import build_trends, sorted_entries, summarize

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Databeheer Cockpit LDV")
app.mount("/static", StaticFiles(directory=BASE_DIR.parent / "static"), name="static")
jinja_env = Environment(
    loader=FileSystemLoader(BASE_DIR / "templates"),
    autoescape=select_autoescape(),
)

history.init_db()

cfg = load_sources()
cache = DashboardCache(
    sections={
        "Diensten": gather_service_statuses,
        "Pipelines": gather_pipeline_statuses,
        "Datakwaliteit": gather_data_quality_statuses,
    },
    ttl_seconds=cfg.get("refresh_interval_seconds", 300),
)


@app.get("/")
def dashboard(request: Request):
    sections = cache.all_sections()
    counts = summarize(sections)
    total = sum(counts.values()) or 1
    try:
        trends = build_trends(cfg.get("triplydb_datasets", []))
    except Exception as exc:
        # Trends is een bijzaak t.o.v. de live status hierboven: nooit de
        # hele pagina laten crashen op een probleem met de trendhistorie.
        print(f"[dashboard] build_trends mislukt: {exc}")
        trends = {"problems": [], "datasets": []}
    template = jinja_env.get_template("dashboard.html")
    return HTMLResponse(
        template.render(
            sections=sections,
            sorted_entries=sorted_entries,
            counts=counts,
            total=total,
            trends=trends,
        )
    )


@app.post("/refresh")
def refresh():
    cache.refresh_all_async()
    return RedirectResponse(url="/", status_code=303)


@app.get("/health")
def health():
    def _env_hint(name: str) -> str:
        value = os.getenv(name)
        if not value:
            return "niet gezet"
        return f"gezet ({len(value)} tekens, begint met '{value[:8]}...')"

    return {
        "status": "ok",
        "env": {
            "GITHUB_TOKEN": _env_hint("GITHUB_TOKEN"),
            "POOLPARTY_TOKEN": _env_hint("POOLPARTY_TOKEN"),
            "HISTORY_REMOTE_URL": _env_hint("HISTORY_REMOTE_URL"),
        },
    }
