import os
from datetime import datetime, timezone

import requests

from app.config import load_sources
from app.mutes import apply_mutes
from app.status import Level, StatusEntry

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
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
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
        if response.status_code == 403 and "rate limit" in response.text.lower():
            limit = response.headers.get("X-RateLimit-Limit", "?")
            token_hint = "GITHUB_TOKEN lijkt niet actief" if limit == "60" else "GITHUB_TOKEN lijkt wel actief, maar toch opgebruikt"
            # Onze check kon GitHub niet bevragen - zegt niets over of de
            # workflow zelf goed draait. Geen FAIL: dat zou een storing in
            # ons eigen pollen laten lijken op een kapotte pipeline.
            return StatusEntry(
                label=label,
                level=Level.UNKNOWN,
                detail=f"kon status niet checken: rate limit bereikt ({limit}/uur) - {token_hint}",
                url=html_url,
            )
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
        # Netwerkfout/timeout/onverwacht antwoord bij het checken zelf - ook
        # dit zegt niets over de daadwerkelijke status van de workflow.
        return StatusEntry(label=label, level=Level.UNKNOWN, detail=f"kon status niet checken: {exc}", url=html_url)


def gather_pipeline_statuses() -> list[StatusEntry]:
    cfg = load_sources()
    entries = [
        check_workflow(p["repo"], p["workflow"], p["label"], p.get("cadence_days"))
        for p in cfg.get("pipelines", [])
    ]
    return apply_mutes(entries, cfg.get("mutes", []))
