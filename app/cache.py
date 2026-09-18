import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from app.status import StatusEntry


@dataclass
class Section:
    title: str
    fetch: Callable[[], list[StatusEntry]]
    entries: list[StatusEntry] = field(default_factory=list)
    last_refreshed: float = 0.0


class DashboardCache:
    """Houdt de laatst opgehaalde statussen per sectie vast.

    Bij een koude start (nog nooit opgehaald) wacht een aanvrager tot de
    eerste fetch klaar is, zodat de allereerste paginaweergave nooit een
    lege sectie toont. Daarna is het stale-while-revalidate: verlopen data
    wordt direct getoond, terwijl een achtergrondthread ververst.
    """

    def __init__(self, sections: dict[str, Callable[[], list[StatusEntry]]], ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self._sections = {key: Section(title=key, fetch=fn) for key, fn in sections.items()}
        self._locks = {key: threading.Lock() for key in sections}
        self._refreshing: set[str] = set()

    def _do_refresh(self, key: str) -> None:
        section = self._sections[key]
        try:
            section.entries = section.fetch()
            section.last_refreshed = time.time()
        finally:
            with self._locks[key]:
                self._refreshing.discard(key)

    def get(self, key: str) -> Section:
        section = self._sections[key]
        lock = self._locks[key]
        is_cold = section.last_refreshed == 0.0
        stale = (time.time() - section.last_refreshed) > self.ttl_seconds

        with lock:
            already_refreshing = key in self._refreshing
            if stale and not already_refreshing:
                self._refreshing.add(key)
                thread = threading.Thread(target=self._do_refresh, args=(key,), daemon=True)
                thread.start()
            elif already_refreshing:
                thread = None
            else:
                thread = None

        if is_cold and (stale or already_refreshing):
            # Eerste keer: wacht tot er iets te tonen valt i.p.v. een lege sectie te renderen.
            for _ in range(300):  # max ~30s
                if section.last_refreshed != 0.0:
                    break
                time.sleep(0.1)

        return section

    def refresh_all_async(self) -> None:
        for key in self._sections:
            with self._locks[key]:
                if key in self._refreshing:
                    continue
                self._refreshing.add(key)
            threading.Thread(target=self._do_refresh, args=(key,), daemon=True).start()

    def all_sections(self) -> dict[str, Section]:
        return {key: self.get(key) for key in self._sections}
