"""Draait de PoolParty-tests los van het dashboard (dezelfde code als de sectie
PoolParty) en print per test level, detail en duur. Leest credentials uit .env /
de omgeving; toont nooit gebruikersnaam of token.

  python scripts/test_poolparty.py                 # alle omgevingen uit sources.yaml
  python scripts/test_poolparty.py --env test      # alleen één omgeving
  python scripts/test_poolparty.py --runs 3        # herhalen om de spreiding in duur te zien
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from app.checks.poolparty import DEFAULT_SLOW_SECONDS, run_environment
from app.config import load_sources


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", help="naam van één omgeving (productie/test)")
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()

    cfg = load_sources().get("poolparty", {})
    slow = cfg.get("slow_seconds", DEFAULT_SLOW_SECONDS)
    envs = [e for e in cfg.get("environments", []) if not args.env or e["name"] == args.env]
    if not envs:
        sys.exit(f"geen omgeving gevonden voor --env {args.env!r}")

    for run in range(1, args.runs + 1):
        for env in envs:
            start = time.perf_counter()
            entries = run_environment(env, slow)
            total = time.perf_counter() - start
            print(f"\n== {env['name']} ({env['host']}) - run {run}/{args.runs} - totaal {total:.1f}s")
            for e in entries:
                print(f"   {e.level.value:8} {e.label.split(': ', 1)[1]:22} {e.detail}")


if __name__ == "__main__":
    main()
