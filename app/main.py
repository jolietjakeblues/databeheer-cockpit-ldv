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
from app.checks.poolparty import gather_poolparty_statuses
from app.checks.services import gather_service_statuses
from app.config import load_sources
from app.summary import build_safety_signs, build_trends, calm_message, health_score, score_band, sorted_entries, summarize

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
        "PoolParty": gather_poolparty_statuses,
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
        trends = {"problems": [], "datasets": [], "offenders": []}
    try:
        safety_signs = build_safety_signs(list(sections.keys()))
    except Exception as exc:
        print(f"[dashboard] build_safety_signs mislukt: {exc}")
        safety_signs = []
    score = health_score(counts)
    template = jinja_env.get_template("dashboard.html")
    return HTMLResponse(
        template.render(
            sections=sections,
            sorted_entries=sorted_entries,
            counts=counts,
            total=total,
            trends=trends,
            score=score,
            score_band=score_band(score),
            calm=calm_message(counts),
            safety_signs=safety_signs,
        )
    )


@app.post("/refresh")
def refresh():
    cache.refresh_all_async()
    return RedirectResponse(url="/", status_code=303)


@app.get("/health")
def health():
    # Dit eindpunt is openbaar: nooit tekens van een geheim tonen, behalve het
    # vaste, publiek bekende voorvoegsel van een tokentype (geen waarde-inhoud).
    public_prefixes = ("github_pat_", "ghp_", "gho_", "https://")

    def _env_hint(name: str) -> str:
        value = os.getenv(name)
        if not value:
            return "niet gezet"
        prefix = next((p for p in public_prefixes if value.startswith(p)), None)
        return f"gezet ({len(value)} tekens" + (f", begint met '{prefix}'" if prefix else "") + ")"

    names = (
        "GITHUB_TOKEN",
        "POOLPARTY_USER",
        "POOLPARTY_TOKEN",
        "POOLPARTY_USER_TEST",
        "POOLPARTY_TOKEN_TEST",
        "HISTORY_REMOTE_URL",
    )
    return {"status": "ok", "env": {name: _env_hint(name) for name in names}}
