from datetime import date, datetime, timedelta, timezone

import requests

from app import history
from app.config import load_sources
from app.mutes import apply_mutes
from app.status import Level, StatusEntry


def _sparql_count(endpoint: str, query: str) -> int:
    response = requests.get(
        endpoint,
        params={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=60,
    )
    response.raise_for_status()
    result = response.json()
    return int(result["results"]["bindings"][0]["count"]["value"])


def check_datacatalog_nde_sync() -> StatusEntry:
    """Vergelijkt het aantal RCE-datasets in de eigen catalogus met wat het
    NDE Datasetregister recent heeft binnengehaald."""
    cfg = load_sources()
    endpoints = cfg.get("sparql_endpoints", {})
    nde_endpoint = endpoints.get("nde_datasetregister")
    rce_endpoint = endpoints.get("datacatalog_rce")
    label = "Datacatalog RCE <-> NDE Datasetregister"

    if not nde_endpoint or not rce_endpoint:
        return StatusEntry(label=label, level=Level.UNKNOWN, detail="endpoints niet geconfigureerd")

    try:
        nde_count = _sparql_count(
            nde_endpoint,
            "PREFIX dct: <http://purl.org/dc/terms/> "
            "PREFIX schema: <https://schema.org/> "
            "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> "
            "SELECT (count(distinct ?dataset) as ?count) WHERE { "
            "?dataset dct:publisher <https://www.cultureelerfgoed.nl> . "
            "?dataset schema:dateRead ?date . "
            f'FILTER (?date > "{date.today() - timedelta(days=2)}T00:00:00+00:00"^^xsd:dateTime) . '
            "}",
        )
        rce_count = _sparql_count(
            rce_endpoint,
            "PREFIX schema: <https://schema.org/> "
            "SELECT (count(distinct ?dataset) as ?count) WHERE { "
            "?dataset schema:publisher <https://www.cultureelerfgoed.nl> . "
            "}",
        )
        level = Level.OK if nde_count == rce_count else Level.WARNING
        detail = f"{nde_count}/{rce_count} datasets uit de RCE-catalogus recent gezien op het NDE Datasetregister"
        return StatusEntry(label=label, level=level, detail=detail)
    except Exception as exc:
        # Netwerk-/queryfout bij het checken zelf - zegt niets over of de
        # datacatalog en het NDE-register daadwerkelijk uit sync zijn.
        return StatusEntry(label=label, level=Level.UNKNOWN, detail=f"kon niet valideren: {exc}")


# Een daling van de triple count van minstens dit percentage t.o.v. de laatste
# meting van gisteren (of eerder) geldt als mogelijk dataverlies. Onder
# MIN_TRIPLES_FOR_DROP_CHECK schommelt een dataset in percentages te veel.
DEFAULT_MAX_DROP_PCT = 5
MIN_TRIPLES_FOR_DROP_CHECK = 1000


def _previous_day_value(label: str) -> float | None:
    """Laatste opgeslagen waarde van een eerdere (UTC-)dag, of None zonder historie."""
    today = datetime.now(timezone.utc).date().isoformat()
    rows = [(day, value) for day, value in history.dataset_trend(label, days=14) if day < today]
    return rows[-1][1] if rows else None


def check_triplydb_dataset(
    account: str,
    dataset: str,
    label: str,
    max_age_days: float | None = None,
    max_drop_pct: float | None = DEFAULT_MAX_DROP_PCT,
) -> StatusEntry:
    """Vraagt TriplyDB's eigen dataset-info API op: triple count, laatste
    update en TriplyDB's eigen hasDataQualityIssues-vlag."""
    api_url = f"https://api.linkeddata.cultureelerfgoed.nl/datasets/{account}/{dataset}"
    page_url = f"https://linkeddata.cultureelerfgoed.nl/{account}/{dataset}"
    try:
        response = requests.get(api_url, headers={"accept": "application/json"}, timeout=30)
        data = response.json()

        if response.status_code != 200 or "statements" not in data:
            # De dataset zelf reageert niet zoals verwacht (404/401/403/...) -
            # dat is een echt signaal over de dataset, geen check-mislukking
            # van onze kant, dus dit blijft FAIL (evt. te temperen via mutes).
            reason = data.get("message", f"HTTP {response.status_code}")
            return StatusEntry(label=label, level=Level.FAIL, detail=f"dataset niet bereikbaar: {reason}", url=page_url)

        statements = data.get("statements", 0)
        updated_raw = data.get("updatedAt") or ""
        updated_at = updated_raw[:16].replace("T", " ")
        has_issues = bool(data.get("hasDataQualityIssues"))

        statements_nl = f"{statements:,}".replace(",", ".")
        detail = f"{statements_nl} triples, laatst bijgewerkt {updated_at}"
        problems: list[str] = []

        if has_issues:
            problems.append("TriplyDB meldt datakwaliteitsissues")

        if max_age_days is not None and updated_raw:
            age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))).total_seconds() / 86400
            if age_days > max_age_days:
                problems.append(f"al {age_days:.1f} dagen niet bijgewerkt (max {max_age_days:g}) - ververst de pipeline nog?")

        if max_drop_pct is not None:
            previous = _previous_day_value(label)
            if previous and previous >= MIN_TRIPLES_FOR_DROP_CHECK:
                drop_pct = 100 * (previous - statements) / previous
                if drop_pct >= max_drop_pct:
                    problems.append(
                        f"{drop_pct:.1f}% minder triples dan vorige meting ({f'{int(previous):,}'.replace(',', '.')}) - dataverlies?"
                    )

        level = Level.FAIL if problems else Level.OK
        if problems:
            detail += " - " + "; ".join(problems)

        return StatusEntry(label=label, level=level, detail=detail, url=page_url, value=float(statements))
    except Exception as exc:
        # Netwerk-/timeoutfout bij het checken zelf (DNS, connectie, timeout)
        # - we weten hierdoor niets over de dataset, dus geen FAIL.
        return StatusEntry(label=label, level=Level.UNKNOWN, detail=f"kon status niet checken: {exc}", url=page_url)


def gather_data_quality_statuses() -> list[StatusEntry]:
    cfg = load_sources()
    entries = [check_datacatalog_nde_sync()]

    for ds in cfg.get("triplydb_datasets", []):
        entries.append(
            check_triplydb_dataset(
                ds["account"],
                ds["dataset"],
                ds["label"],
                max_age_days=ds.get("max_age_days"),
                max_drop_pct=ds.get("max_drop_pct", DEFAULT_MAX_DROP_PCT),
            )
        )

    return apply_mutes(entries, cfg.get("mutes", []))
