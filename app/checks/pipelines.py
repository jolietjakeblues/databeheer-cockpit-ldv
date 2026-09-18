import os

import requests

from app.config import load_sources
from app.status import Level, StatusEntry

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

_CONCLUSION_LEVEL = {
    "success": Level.OK,
    "failure": Level.FAIL,
    "cancelled": Level.WARNING,
    "timed_out": Level.FAIL,
    "action_required": Level.WARNING,
    "skipped": Level.WARNING,
    "stale": Level.WARNING,
}


def _headers() -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def check_workflow(repo: str, workflow: str, label: str) -> StatusEntry:
    api_url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/runs?per_page=1"
    html_url = f"https://github.com/{repo}/actions/workflows/{workflow}"
    try:
        response = requests.get(api_url, headers=_headers(), timeout=30)
        if response.status_code == 404:
            return StatusEntry(label=label, level=Level.UNKNOWN, detail="workflow niet gevonden", url=html_url)
        response.raise_for_status()
        runs = response.json().get("workflow_runs", [])
        if not runs:
            return StatusEntry(label=label, level=Level.UNKNOWN, detail="nog geen runs", url=html_url)

        run = runs[0]
        status = run.get("status")  # queued/in_progress/completed
        conclusion = run.get("conclusion")  # success/failure/...
        run_at = run.get("run_started_at", "")[:16].replace("T", " ")

        if status != "completed":
            level = Level.WARNING
            detail = f"loopt nog ({status}), gestart {run_at}"
        else:
            level = _CONCLUSION_LEVEL.get(conclusion, Level.UNKNOWN)
            detail = f"laatste run: {conclusion}, {run_at}"

        return StatusEntry(label=label, level=level, detail=detail, url=run.get("html_url", html_url))
    except Exception as exc:
        return StatusEntry(label=label, level=Level.FAIL, detail=f"fout bij ophalen: {exc}", url=html_url)


def gather_pipeline_statuses() -> list[StatusEntry]:
    cfg = load_sources()
    return [check_workflow(p["repo"], p["workflow"], p["label"]) for p in cfg.get("pipelines", [])]
