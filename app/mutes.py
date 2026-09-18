from datetime import date

from app.status import Level, StatusEntry


def apply_mutes(entries: list[StatusEntry], mutes_cfg: list[dict]) -> list[StatusEntry]:
    """Demp bekende, geaccepteerde problemen.

    Een check die FAIL of WARNING oplevert maar voorkomt in `mutes_cfg` (op
    exacte label-match) wordt teruggebracht naar UNKNOWN met de reden erbij
    - zichtbaar dat er iets afwijkt, maar telt niet mee als storing. Geen
    codewijziging nodig voor een nieuw eenmalig geaccepteerd issue: gewoon
    een item toevoegen aan `mutes:` in config/sources.yaml. Een `until`-datum
    (YYYY-MM-DD) laat de mute vanzelf verlopen, zodat een "tijdelijk"
    geaccepteerd probleem niet stilzwijgend voor altijd genegeerd blijft.
    """
    today = date.today().isoformat()
    active_mutes = {}
    for mute in mutes_cfg:
        until = mute.get("until")
        if until and str(until) < today:
            continue  # verlopen, telt niet meer mee
        active_mutes[mute["label"]] = mute

    for entry in entries:
        mute = active_mutes.get(entry.label)
        if mute and entry.level in (Level.FAIL, Level.WARNING):
            entry.level = Level.UNKNOWN
            entry.detail = f"{entry.detail} — gemute: {mute['reason']}"

    return entries
