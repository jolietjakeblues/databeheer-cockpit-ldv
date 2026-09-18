from datetime import date, timedelta

import requests

from app.config import load_sources
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
        return StatusEntry(label=label, level=Level.FAIL, detail=f"fout bij valideren: {exc}")


def check_triplydb_dataset(account: str, dataset: str, label: str, expected_private: bool = False) -> StatusEntry:
    """Vraagt TriplyDB's eigen dataset-info API op: triple count, laatste
    update en TriplyDB's eigen hasDataQualityIssues-vlag."""
    api_url = f"https://api.linkeddata.cultureelerfgoed.nl/datasets/{account}/{dataset}"
    page_url = f"https://linkeddata.cultureelerfgoed.nl/{account}/{dataset}"
    try:
        response = requests.get(api_url, headers={"accept": "application/json"}, timeout=30)
        data = response.json()

        if response.status_code != 200 or "statements" not in data:
            reason = data.get("message", f"HTTP {response.status_code}")
            if expected_private and response.status_code in (401, 403, 404):
                return StatusEntry(label=label, level=Level.UNKNOWN, detail=f"privé (verwacht), niet publiek uitleesbaar: {reason}", url=page_url)
            return StatusEntry(label=label, level=Level.FAIL, detail=f"dataset niet bereikbaar: {reason}", url=page_url)

        statements = data.get("statements", 0)
        updated_at = (data.get("updatedAt") or "")[:16].replace("T", " ")
        has_issues = bool(data.get("hasDataQualityIssues"))

        level = Level.FAIL if has_issues else Level.OK
        statements_nl = f"{statements:,}".replace(",", ".")
        detail = f"{statements_nl} triples, laatst bijgewerkt {updated_at}"
        if has_issues:
            detail += " - TriplyDB meldt datakwaliteitsissues"

        return StatusEntry(label=label, level=level, detail=detail, url=page_url, value=float(statements))
    except Exception as exc:
        return StatusEntry(label=label, level=Level.FAIL, detail=f"fout bij ophalen: {exc}", url=page_url)


def gather_data_quality_statuses() -> list[StatusEntry]:
    cfg = load_sources()
    entries = [check_datacatalog_nde_sync()]

    for ds in cfg.get("triplydb_datasets", []):
        entries.append(
            check_triplydb_dataset(ds["account"], ds["dataset"], ds["label"], ds.get("expected_private", False))
        )

    return entries
