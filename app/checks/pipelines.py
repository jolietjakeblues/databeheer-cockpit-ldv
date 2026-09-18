import os
from datetime import datetime, timezone

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

_DISABLED_REASON = {
    "disabled_inactivity": "automatisch uitgeschakeld door GitHub wegens 60+ dagen inactiviteit in de repo",
    "disabled_manually": "handmatig uitgeschakeld",
}


def _headers() -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def _get_workflow_state(repo: str, workflow: str) -> str | None:
    """Geeft de workflow-state (active/disabled_inactivity/disabled_manually) of
    None als die niet kon worden opgehaald."""
    api_url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}"
    try:
        response = requests.get(api_url, headers=_headers(), timeout=30)
        if response.status_code != 200:
            return None
        return response.json().get("state")
    except Exception:
        return None


def check_workflow(repo: str, workflow: str, label: str, cadence_days: int | None) -> StatusEntry:
    api_url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/runs?per_page=1"
    html_url = f"https://github.com/{repo}/actions/workflows/{workflow}"

    state = _get_workflow_state(repo, workflow)
    if state and state != "active":
        reason = _DISABLED_REASON.get(state, state)
        return StatusEntry(label=label, level=Level.FAIL, detail=f"workflow staat stil: {reason}", url=html_url)

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
        started_raw = run.get("run_started_at", "")
        run_at = started_raw[:16].replace("T", " ")

        if status != "completed":
            return StatusEntry(label=label, level=Level.WARNING, detail=f"loopt nog ({status}), gestart {run_at}", url=run.get("html_url", html_url))

        level = _CONCLUSION_LEVEL.get(conclusion, Level.UNKNOWN)
        detail = f"laatste run: {conclusion}, {run_at}"

        if cadence_days is not None and started_raw:
            started_at = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
            days_since = (datetime.now(timezone.utc) - started_at).days
            grace_days = max(cadence_days * 2, cadence_days + 2)
            if days_since > grace_days:
                level = Level.FAIL
                detail = f"laatste run {days_since} dagen geleden ({conclusion}), verwacht elke {cadence_days} dag(en) - lijkt gestopt"

        return StatusEntry(label=label, level=level, detail=detail, url=run.get("html_url", html_url))
    except Exception as exc:
        return StatusEntry(label=label, level=Level.FAIL, detail=f"fout bij ophalen: {exc}", url=html_url)


def gather_pipeline_statuses() -> list[StatusEntry]:
    cfg = load_sources()
    return [
        check_workflow(p["repo"], p["workflow"], p["label"], p.get("cadence_days"))
        for p in cfg.get("pipelines", [])
    ]
