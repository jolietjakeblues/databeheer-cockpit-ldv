from app import history
from app.cache import Section
from app.charts import sparkline_points
from app.status import SEVERITY_ORDER, Level


def sorted_entries(section: Section) -> list:
    return sorted(section.entries, key=lambda e: SEVERITY_ORDER[e.level])


def summarize(sections: dict[str, Section]) -> dict[Level, int]:
    counts = {level: 0 for level in Level}
    for section in sections.values():
        for entry in section.entries:
            counts[entry.level] += 1
    return counts


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

    return {"problems": problems, "datasets": datasets}
