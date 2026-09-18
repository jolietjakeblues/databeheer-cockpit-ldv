import json
import os
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import requests

from app.config import load_sources
from app.mutes import apply_mutes
from app.status import Level, StatusEntry, now_cet


def check_ldv_service(name: str, url: str) -> StatusEntry:
    """Vraagt de statuspagina van een LDV-dataset-service op (Virtuoso/Jena)."""
    timeformat_src = "%Y-%m-%dT%H:%M:%S.%fZ"
    try:
        response = requests.get(url, headers={"accept": "text/plain"}, timeout=30)
        info = json.loads(response.content)
        status = info.get("status")
        out_of_sync = info.get("outOfSync")
        # De LDV-API geeft een echte JSON-boolean terug; alleen str/bool "true" tellen mee.
        out_of_sync_bool = out_of_sync is True or str(out_of_sync).lower() == "true"
        created = datetime.strptime(info.get("createdAt"), timeformat_src)

        if status != "running":
            level = Level.FAIL
        elif out_of_sync_bool:
            level = Level.WARNING
        elif now_cet() - created <= timedelta(days=1):
            level = Level.WARNING
        else:
            level = Level.OK

        detail = f"{status}, sinds {created:%Y-%m-%d %H:%M}, sync nodig: {out_of_sync}"
        return StatusEntry(label=name, level=level, detail=detail, url=url)
    except Exception as exc:
        return StatusEntry(label=name, level=Level.FAIL, detail=f"fout bij ophalen status: {exc}", url=url)


def check_website(name: str, url: str) -> StatusEntry:
    try:
        response = requests.get(url, allow_redirects=True, timeout=30)
        millis = response.elapsed / timedelta(milliseconds=1)
        level = Level.OK if response.status_code == 200 else Level.FAIL
        detail = f"HTTP {response.status_code} in {millis:.0f}ms"
        return StatusEntry(label=name, level=level, detail=detail, url=url)
    except Exception as exc:
        return StatusEntry(label=name, level=Level.FAIL, detail=f"fout bij ophalen: {exc}", url=url)


def check_poolparty(name: str, url: str) -> StatusEntry:
    token = os.getenv("POOLPARTY_TOKEN")
    if not token:
        return StatusEntry(label=name, level=Level.UNKNOWN, detail="POOLPARTY_TOKEN ontbreekt, check overgeslagen", url=url)
    try:
        response = requests.get(
            url,
            allow_redirects=True,
            headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
            timeout=30,
        )
        millis = response.elapsed / timedelta(milliseconds=1)
        ok = response.status_code == 200 and "uri" in str(response.content)
        level = Level.OK if ok else Level.FAIL
        detail = f"HTTP {response.status_code} in {millis:.0f}ms"
        return StatusEntry(label=f"{name} ({urlsplit(url).netloc})", level=level, detail=detail, url=url)
    except Exception as exc:
        return StatusEntry(label=name, level=Level.FAIL, detail=f"fout bij ophalen: {exc}", url=url)


def gather_service_statuses() -> list[StatusEntry]:
    cfg = load_sources()
    entries: list[StatusEntry] = []

    for svc in cfg.get("ldv_services", []):
        entries.append(check_ldv_service(svc["name"], svc["url"]))

    for site in cfg.get("websites", []):
        entries.append(check_website(site["name"], site["url"]))

    for pp in cfg.get("poolparty_checks", []):
        entries.append(check_poolparty(pp["name"], pp["url"]))

    return apply_mutes(entries, cfg.get("mutes", []))
