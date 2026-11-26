from collections import Counter

from app.status import Level, StatusEntry

# UNKNOWN-redenen die geen "blindheid" zijn: een bewuste configuratiekeuze of
# een geaccepteerd probleem. Alleen echte onbeoordeelbaarheid (verlopen token,
# netwerk, foute credentials) telt voor het blind-alarm.
NOT_BLINDNESS_MARKERS = ("ontbreekt, check overgeslagen", "gemute:")


def blind_entries(entries: list[tuple[str, StatusEntry]]) -> list[tuple[str, StatusEntry]]:
    return [
        (section, entry)
        for section, entry in entries
        if entry.level == Level.UNKNOWN and not any(marker in entry.detail for marker in NOT_BLINDNESS_MARKERS)
    ]


def describe_blindness(blind: list[tuple[str, StatusEntry]]) -> str:
    """Per sectie: aantal + de meest voorkomende reden, zodat de melding de oorzaak noemt."""
    by_section: dict[str, list[str]] = {}
    for section, entry in blind:
        by_section.setdefault(section, []).append(entry.detail)
    lines = []
    for section, details in by_section.items():
        reason, _ = Counter(details).most_common(1)[0]
        lines.append(f"- {section}: {len(details)} checks - {reason[:140]}")
    return "\n".join(lines)
