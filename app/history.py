import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.status import StatusEntry

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "history.sqlite"
RETENTION_DAYS = 90


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
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
    now = datetime.now(timezone.utc).isoformat()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
    with closing(_connect()) as conn, conn:
        conn.executemany(
            "INSERT INTO snapshots (section, label, level, detail, value, checked_at) VALUES (?, ?, ?, ?, ?, ?)",
            [(section, e.label, e.level.value, e.detail, e.value, now) for e in entries],
        )
        conn.execute("DELETE FROM snapshots WHERE checked_at < ?", (cutoff,))


def daily_problem_counts(days: int = 30) -> list[tuple[str, int]]:
    """(dag, aantal niet-OK checks) voor elke dag met data, laatste `days` dagen."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
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


def dataset_trend(label: str, days: int = 30) -> list[tuple[str, float]]:
    """(dag, laatste waarde die dag) voor een gegeven check-label, laatste `days` dagen."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
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
