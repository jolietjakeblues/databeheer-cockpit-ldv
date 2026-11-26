"""Test de PoolParty-API-calls los van het dashboard.

Leest credentials uit .env / de omgeving en toont alleen status, duur en
(bij falen) de foutklasse - nooit gebruikersnaam of token.

  python scripts/test_poolparty.py                 # alle poolparty_checks uit sources.yaml
  python scripts/test_poolparty.py --runs 5        # vaker herhalen (spreiding in duur)
  python scripts/test_poolparty.py --url URL --token-env POOLPARTY_TOKEN_TEST --user-env POOLPARTY_USER_TEST
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from dotenv import load_dotenv

load_dotenv()

from app.checks.services import poolparty_request_kwargs
from app.config import load_sources


def probe(name: str, url: str, token_env: str, user_env: str | None, runs: int, timeout: int) -> None:
    token = os.getenv(token_env)
    user = os.getenv(user_env) if user_env else None
    mode = "gebruiker+token" if user else "kant-en-klaar base64-token"
    print(f"\n== {name}\n   host: {requests.utils.urlparse(url).netloc}  |  {token_env}: {'gezet' if token else 'NIET gezet'}"
          f"  |  {user_env or '-'}: {'gezet' if user else 'niet gezet'}  |  modus: {mode}")
    if not token:
        print("   overgeslagen: geen token beschikbaar")
        return

    durations = []
    for i in range(1, runs + 1):
        start = time.perf_counter()
        try:
            resp = requests.get(url, allow_redirects=True, timeout=timeout, **poolparty_request_kwargs(token, user))
            secs = time.perf_counter() - start
            body = resp.content
            has_uri = b"uri" in body
            hops = len(resp.history)
            print(f"   #{i}: http={resp.status_code}  {secs:.2f}s  {len(body)} bytes  'uri' in body: {has_uri}"
                  f"  redirects: {hops}  eind-host: {requests.utils.urlparse(resp.url).netloc}")
            durations.append(secs)
        except requests.exceptions.RequestException as exc:
            secs = time.perf_counter() - start
            print(f"   #{i}: FOUT na {secs:.2f}s: {type(exc).__name__}")
    if durations:
        print(f"   samenvatting: min {min(durations):.2f}s  max {max(durations):.2f}s  ({len(durations)}/{runs} antwoorden)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=60, help="seconden; de app zelf gebruikt 30")
    parser.add_argument("--url")
    parser.add_argument("--token-env", default="POOLPARTY_TOKEN")
    parser.add_argument("--user-env")
    args = parser.parse_args()

    if args.url:
        probe("handmatige URL", args.url, args.token_env, args.user_env, args.runs, args.timeout)
        return

    for pp in load_sources().get("poolparty_checks", []):
        probe(pp["name"], pp["url"], pp.get("token_env", "POOLPARTY_TOKEN"), pp.get("user_env"), args.runs, args.timeout)


if __name__ == "__main__":
    main()
