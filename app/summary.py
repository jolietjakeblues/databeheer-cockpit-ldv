from app.cache import Section
from app.status import SEVERITY_ORDER, Level


def sorted_entries(section: Section) -> list:
    return sorted(section.entries, key=lambda e: SEVERITY_ORDER[e.level])


def summarize(sections: dict[str, Section]) -> dict[Level, int]:
    counts = {level: 0 for level in Level}
    for section in sections.values():
        for entry in section.entries:
            counts[entry.level] += 1
    return counts
