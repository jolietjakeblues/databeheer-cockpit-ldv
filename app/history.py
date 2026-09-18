import os
import sqlite3
import tempfile
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from app.status import Level, StatusEntry

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "history.sqlite"
RETENTION_DAYS = 90

# Read-only modus voor hosts zonder persistente schijf (bv. Render free tier):
# leest een kant-en-klare history.sqlite van een publieke URL (de 'data'-branch
# op GitHub, bijgehouden door .github/workflows/record-history.yml) i.p.v. zelf
# lokaal te schrijven. Schrijven (record_snapshot) is dan een no-op.
REMOTE_URL = os.getenv("HISTORY_REMOTE_URL")
_REMOTE_CACHE_PATH = Path(tempfile.gettempdir()) / "cockpit-history-remote.sqlite"
_REMOTE_CACHE_TTL = 300
_remote_last_fetch = 0.0


def _ensure_remote_copy() -> Path | None:
    global _remote_last_fetch
    if time.time() - _remote_last_fetch < _REMOTE_CACHE_TTL and _REMOTE_CACHE_PATH.exists():
        return _REMOTE_CACHE_PATH
    try:
        response = requests.get(REMOTE_URL, timeout=20)
        response.raise_for_status()
        _REMOTE_CACHE_PATH.write_bytes(response.content)
        _remote_last_fetch = time.time()
    except Exception as exc:
        print(f"[history] kon HISTORY_REMOTE_URL niet ophalen: {exc}")
        # val terug op de laatst gelukte kopie, indien aanwezig
    return _REMOTE_CACHE_PATH if _REMOTE_CACHE_PATH.exists() else None


def _connect() -> sqlite3.Connection:
    if REMOTE_URL:
        path = _ensure_remote_copy()
        if path is None:
            raise RuntimeError("kon HISTORY_REMOTE_URL niet ophalen en geen lokale cache beschikbaar")
        return sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True, timeout=10)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    if REMOTE_URL:
        return  # read-only: schema wordt elders (Action) beheerd
    with closing(_connect()) as conn, conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                section TEXT NOT NULL,
                label TEXT NOT NULL,
                level TEXT NOT NULL,
                detail TEXT,
                value REAL,
                checked_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_checked_at ON snapshots (checked_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_label ON snapshots (label, checked_at)")


def record_snapshot(section: str, entries: list[StatusEntry]) -> None:
    """Slaat één rij per check op en ruimt meteen alles ouder dan de
    bewaartermijn op - geen aparte cleanup-job nodig."""
    if REMOTE_URL:
        return  # read-only modus: dit proces schrijft niet, alleen de Action doet dat
    now = datetime.now(timezone.utc).isoformat()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
    with closing(_connect()) as conn:
        with conn:
            conn.executemany(
                "INSERT INTO snapshots (section, label, level, detail, value, checked_at) VALUES (?, ?, ?, ?, ?, ?)",
                [(section, e.label, e.level.value, e.detail, e.value, now) for e in entries],
            )
            conn.execute("DELETE FROM snapshots WHERE checked_at < ?", (cutoff,))
        # WAL-mode schrijft naar een los -wal-bestand tot een checkpoint dat
        # terugmerget in het hoofdbestand. Iets dat het hoofdbestand los van
        # SQLite kopieert/publiceert (zoals record_history.py, dat het
        # bestand daarna naar de data-branch commit) ziet zonder expliciete
        # checkpoint dus soms een leeg of onvolledig bestand - vandaar hier
        # altijd afdwingen. Moet na de `with conn:` (die commit) draaien: een
        # checkpoint kan niet binnen een nog open schrijftransactie.
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def detect_new_failures(entries: list[StatusEntry]) -> list[StatusEntry]:
    """Vergelijkt elke entry met de vorige snapshot van datzelfde label en
    geeft de entries terug die NET FAIL zijn geworden (was iets anders, is nu
    FAIL) - bedoeld om alleen bij een echte statusovergang te alerten, niet
    bij elke run zolang iets al bekend kapot is (voorkomt alert-moeheid).
    Moet aangeroepen worden na record_snapshot() van diezelfde entries."""
    if REMOTE_URL:
        return []  # alerting gebeurt vanuit de Action, niet vanuit een read-only host
    newly_failed = []
    with closing(_connect()) as conn:
        for entry in entries:
            if entry.level != Level.FAIL:
                continue
            row = conn.execute(
                "SELECT level FROM snapshots WHERE label = ? ORDER BY checked_at DESC LIMIT 1 OFFSET 1",
                (entry.label,),
            ).fetchone()
            previous_level = row[0] if row else None
            if previous_level != Level.FAIL.value:
                newly_failed.append(entry)
    return newly_failed


def daily_problem_counts(days: int = 30) -> list[tuple[str, int]]:
    """(dag, aantal niet-OK checks) voor elke dag met data, laatste `days` dagen.

    Trends zijn een bijzaak t.o.v. de live status hierboven: als de historie
    (lokaal of remote) om wat voor reden dan ook niet te lezen is, geeft dit
    gewoon een lege lijst terug i.p.v. de hele dashboardpagina mee te slepen
    in een crash."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        with closing(_connect()) as conn:
            rows = conn.execute(
                """
                SELECT substr(checked_at, 1, 10) AS day, COUNT(*) AS problems
                FROM snapshots
                WHERE checked_at >= ? AND level != 'ok'
                GROUP BY day
                ORDER BY day
                """,
                (cutoff,),
            ).fetchall()
        return list(rows)
    except Exception as exc:
        print(f"[history] daily_problem_counts mislukt: {exc}")
        return []


def days_since_last_incident(section: str | None = None) -> dict | None:
    """Dagen sinds de laatste FAIL - het getal voor een 'X dagen zonder
    storing'-bord. Is er nog nooit een FAIL gezien (in de bewaarde 90 dagen),
    dan telt het vanaf het eerste record ('sinds start van de meting') i.p.v.
    een onwaarschijnlijk hoog getal te verzinnen. Geeft None als er
    helemaal geen historie is om iets over te zeggen."""
    try:
        with closing(_connect()) as conn:
            if section:
                last_fail = conn.execute(
                    "SELECT MAX(checked_at) FROM snapshots WHERE level = 'fail' AND section = ?",
                    (section,),
                ).fetchone()[0]
            else:
                last_fail = conn.execute(
                    "SELECT MAX(checked_at) FROM snapshots WHERE level = 'fail'"
                ).fetchone()[0]

            had_fail = last_fail is not None
            if had_fail:
                since = last_fail
            elif section:
                since = conn.execute(
                    "SELECT MIN(checked_at) FROM snapshots WHERE section = ?", (section,)
                ).fetchone()[0]
            else:
                since = conn.execute("SELECT MIN(checked_at) FROM snapshots").fetchone()[0]

        if since is None:
            return None
        since_dt = datetime.fromisoformat(since)
        if since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=timezone.utc)
        days = max(0, (datetime.now(timezone.utc) - since_dt).days)
        return {"days": days, "had_fail": had_fail}
    except Exception as exc:
        print(f"[history] days_since_last_incident({section!r}) mislukt: {exc}")
        return None


def worst_offenders(days: int = 30, limit: int = 5) -> list[tuple[str, str, int]]:
    """(sectie, label, aantal niet-OK checks) top-N over de laatste `days`
    dagen - de checks die het vaakst voor problemen zorgen ('wall of shame').
    Zelfde falen-is-geen-optie-redenering als daily_problem_counts."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        with closing(_connect()) as conn:
            rows = conn.execute(
                """
                SELECT section, label, COUNT(*) AS problems
                FROM snapshots
                WHERE checked_at >= ? AND level != 'ok'
                GROUP BY section, label
                ORDER BY problems DESC, label
                LIMIT ?
                """,
                (cutoff, limit),
            ).fetchall()
        return list(rows)
    except Exception as exc:
        print(f"[history] worst_offenders mislukt: {exc}")
        return []


def dataset_trend(label: str, days: int = 30) -> list[tuple[str, float]]:
    """(dag, laatste waarde die dag) voor een gegeven check-label, laatste `days` dagen.
    Zelfde falen-is-geen-optie-redenering als daily_problem_counts."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        with closing(_connect()) as conn:
            rows = conn.execute(
                """
                SELECT substr(s1.checked_at, 1, 10) AS day, s1.value
                FROM snapshots s1
                WHERE s1.checked_at >= ? AND s1.label = ? AND s1.value IS NOT NULL
                  AND s1.checked_at = (
                      SELECT MAX(s2.checked_at) FROM snapshots s2
                      WHERE s2.label = s1.label
                        AND substr(s2.checked_at, 1, 10) = substr(s1.checked_at, 1, 10)
                  )
                ORDER BY day
                """,
                (cutoff, label),
            ).fetchall()
        return list(rows)
    except Exception as exc:
        print(f"[history] dataset_trend({label!r}) mislukt: {exc}")
        return []
