import random

from app import history
from app.cache import Section
from app.charts import sparkline_points
from app.status import SEVERITY_ORDER, Level

# Gewicht per niveau voor de gezondheidsscore: fail kost alle punten, warning
# de helft, onbekend maar een klein beetje (het is immers geen bevestigd
# probleem - zie de FAIL/UNKNOWN-uitleg in het README).
SCORE_WEIGHTS = {Level.OK: 1.0, Level.UNKNOWN: 0.8, Level.WARNING: 0.5, Level.FAIL: 0.0}

CALM_MESSAGES = [
    "Niets te melden vandaag.",
    "All quiet on the western front.",
    "Rustig vaarwater.",
    "Alle seinen op groen.",
    "Geen nieuws is goed nieuws.",
    "De archivaris kan gerust slapen.",
    "Stilte in de tent.",
]


def sorted_entries(section: Section) -> list:
    return sorted(section.entries, key=lambda e: SEVERITY_ORDER[e.level])


def summarize(sections: dict[str, Section]) -> dict[Level, int]:
    counts = {level: 0 for level in Level}
    for section in sections.values():
        for entry in section.entries:
            counts[entry.level] += 1
    return counts


def health_score(counts: dict[Level, int]) -> int:
    """Gewogen gezondheidsscore (0-100): telt zwaarder mee naarmate een
    niveau ernstiger is, in plaats van simpelweg het percentage OK."""
    total = sum(counts.values()) or 1
    weighted = sum(SCORE_WEIGHTS[level] * count for level, count in counts.items())
    return round(weighted / total * 100)


def score_band(score: int) -> str:
    if score >= 90:
        return "ok"
    if score >= 70:
        return "warning"
    return "fail"


def calm_message(counts: dict[Level, int]) -> str | None:
    """Een rustige, wisselende regel i.p.v. een kaal vinkje zodra er geen
    fail of warning open staat - zodat de pagina niet leeg aanvoelt op een
    goede dag."""
    if counts[Level.FAIL] == 0 and counts[Level.WARNING] == 0:
        return random.choice(CALM_MESSAGES)
    return None


def build_safety_signs(section_keys: list[str]) -> list[dict]:
    """'Dagen zonder storing'-bordjes: totaal plus per sectie."""
    signs = []
    total = history.days_since_last_incident()
    if total:
        signs.append({"label": "Totaal", **total})
    for key in section_keys:
        result = history.days_since_last_incident(section=key)
        if result:
            signs.append({"label": key, **result})
    return signs


def build_trends(triplydb_datasets: list[dict], days: int = 30) -> dict:
    """Stelt de trenddata samen: problemen-over-tijd + per-dataset sparklines.
    Werkt ook met weinig/geen historie - dan tonen we gewoon 'wordt opgebouwd'."""
    problem_rows = history.daily_problem_counts(days=days)
    max_problems = max((count for _, count in problem_rows), default=0) or 1
    problems = [
        {"day": day, "count": count, "height_pct": round(count / max_problems * 100, 1)}
        for day, count in problem_rows
    ]

    datasets = []
    for ds in triplydb_datasets:
        rows = history.dataset_trend(ds["label"], days=days)
        values = [v for _, v in rows]
        datasets.append(
            {
                "label": ds["label"],
                "points": sparkline_points(values),
                "current": values[-1] if values else None,
                "has_trend": len(values) >= 2,
            }
        )

    offenders = [
        {"section": section, "label": label, "count": count}
        for section, label, count in history.worst_offenders(days=days)
    ]

    return {"problems": problems, "datasets": datasets, "offenders": offenders}
