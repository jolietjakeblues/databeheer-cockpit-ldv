from pathlib import Path
from functools import lru_cache

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "sources.yaml"


@lru_cache
def load_sources() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)
