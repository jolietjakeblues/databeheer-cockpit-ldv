"""PoolParty-tests, per omgeving (productie/test) uit `poolparty:` in sources.yaml.

Per omgeving, elk een eigen regel in de sectie PoolParty:
  - API + inloggen        GET /PoolParty/api/projects
  - Project <naam>        voor élke project-id in `expected_projects`: staat in de
                          projectenlijst, heeft concept schemes en topconcepten
  - Concept ophalen       prefLabel + uri in het antwoord
  - Hiërarchie            broaders van het concept, en narrowers van die parent
  - Extractor (suggest)   zoekterm levert suggesties op
  - Publieke URI (RDF)    concept-URI resolvet zonder login naar RDF/XML

Een mislukte *check* (ontbrekende of ongeldige credentials) is UNKNOWN, geen
FAIL: het zegt niets over of PoolParty zelf goed draait. Twee keer geen
antwoord binnen de timeout is een WARNING; een te trage respons ook.
"""

import os
import time
from collections.abc import Callable

import requests

from app.config import load_sources
from app.mutes import apply_mutes
from app.status import Level, StatusEntry

TIMEOUT = 30
ATTEMPTS = 2
DEFAULT_SLOW_SECONDS = 10

# Na één mislukte login (401/403) doen we een tijd geen enkele geauthenticeerde
# call meer voor die omgeving. PoolParty kan een account blokkeren na een paar
# foute pogingen; veel tests per refresh met een verkeerd wachtwoord zou dat
# zelf veroorzaken (en een blokkade vervolgens steeds weer verlengen).
AUTH_BACKOFF_SECONDS = 15 * 60
AUTH_FAIL_PREFIX = "kon niet inloggen"
_auth_backoff_until: dict[str, float] = {}

# (level, detail, seconden)
Outcome = tuple[Level, str, float]


def _fetch(url: str, creds: tuple[str | None, str] | None, *, params=None, accept="application/json"):
    """GET met retry op timeout. Geeft (response, seconden) van de laatste poging terug."""
    headers = {"Accept": accept}
    kwargs: dict = {}
    if creds:
        user, token = creds
        if user:
            kwargs["auth"] = (user, token)  # Basic uit gebruikersnaam + token
        else:
            headers["Authorization"] = f"Basic {token}"  # kant-en-klare base64-waarde
    last_timeout = None
    for _ in range(ATTEMPTS):
        start = time.perf_counter()
        try:
            response = requests.get(
                url, params=params, headers=headers, timeout=TIMEOUT, allow_redirects=True, **kwargs
            )
            return response, time.perf_counter() - start
        except requests.exceptions.Timeout as exc:
            last_timeout = exc
    raise last_timeout


def _auth_problem(response) -> Outcome | None:
    if response.status_code in (401, 403):
        return (
            Level.UNKNOWN,
            f"{AUTH_FAIL_PREFIX} (HTTP {response.status_code}) - controleer de PoolParty-credentials",
            0.0,
        )
    return None


def _json(response):
    try:
        return response.json()
    except ValueError:
        return None


def _api(env: dict) -> str:
    return f"{env['host']}/PoolParty/api"


def _project_list(env, creds, ctx) -> tuple[list | None, Outcome | None, float]:
    """Projectenlijst, één keer per run opgehaald en gedeeld door alle checks."""
    if "projects" in ctx:
        return ctx["projects"]
    response, secs = _fetch(f"{_api(env)}/projects", creds)
    if (problem := _auth_problem(response)):
        result = (None, problem, secs)
    else:
        data = _json(response)
        if response.status_code != 200 or not isinstance(data, list):
            result = (None, (Level.FAIL, f"HTTP {response.status_code}, geen projectenlijst", secs), secs)
        else:
            result = (data, None, secs)
    ctx["projects"] = result
    return result


def check_projects(env, creds, ctx) -> Outcome:
    data, problem, secs = _project_list(env, creds, ctx)
    if problem:
        return problem
    return Level.OK, f"{len(data)} projecten, {secs:.2f}s", secs


def check_project(env, creds, ctx, project: dict) -> Outcome:
    """Eén verwachte thesaurus: bestaat, heeft concept schemes én topconcepten."""
    data, problem, secs_list = _project_list(env, creds, ctx)
    if problem:
        return problem
    pid = project["id"]
    found = next((p for p in data if str(p.get("id", "")).lower() == pid.lower()), None)
    if not found:
        return Level.FAIL, f"project {pid} niet gevonden in PoolParty", secs_list
    title = (found.get("title") or "").strip() or pid

    base = f"{_api(env)}/thesaurus/{pid}"
    response, secs_a = _fetch(f"{base}/schemes", creds)
    if (problem := _auth_problem(response)):
        return problem
    schemes = _json(response)
    if response.status_code != 200 or not isinstance(schemes, list) or not schemes:
        return Level.FAIL, f"'{title}': geen concept schemes (HTTP {response.status_code})", secs_a

    response, secs_b = _fetch(f"{base}/topconcepts", creds, params={"scheme": schemes[0]["uri"]})
    tops = _json(response)
    total = secs_a + secs_b
    if response.status_code != 200 or not isinstance(tops, list) or not tops:
        return Level.FAIL, f"'{title}': geen topconcepten (HTTP {response.status_code})", total
    return Level.OK, f"'{title}': {len(schemes)} schema's, {len(tops)} topconcepten, {total:.2f}s", total


def check_concept(env, creds, ctx) -> Outcome:
    url = f"{_api(env)}/thesaurus/{env['project_id']}/concept"
    response, secs = _fetch(url, creds, params={"concept": env["concept_uri"], "properties": "all"})
    if (problem := _auth_problem(response)):
        return problem
    data = _json(response)
    if response.status_code != 200 or not isinstance(data, dict):
        return Level.FAIL, f"HTTP {response.status_code}", secs
    if not data.get("uri") or not data.get("prefLabel"):
        return Level.FAIL, "antwoord mist uri of prefLabel", secs
    return Level.OK, f"'{data['prefLabel']}' opgehaald, {secs:.2f}s", secs


def check_hierarchy(env, creds, ctx) -> Outcome:
    base = f"{_api(env)}/thesaurus/{env['project_id']}"
    response, secs_a = _fetch(f"{base}/broaders", creds, params={"concept": env["concept_uri"]})
    if (problem := _auth_problem(response)):
        return problem
    broaders = _json(response)
    if response.status_code != 200 or not isinstance(broaders, list) or not broaders:
        return Level.FAIL, f"broaders: HTTP {response.status_code}, geen parent gevonden", secs_a
    parent = broaders[0].get("uri")
    response, secs_b = _fetch(f"{base}/narrowers", creds, params={"concept": parent})
    narrowers = _json(response)
    if response.status_code != 200 or not isinstance(narrowers, list) or not narrowers:
        return Level.FAIL, f"narrowers: HTTP {response.status_code}, geen kinderen van parent", secs_a + secs_b
    return Level.OK, f"parent '{broaders[0].get('prefLabel', '?')}' heeft {len(narrowers)} narrowers", secs_a + secs_b


def check_suggest(env, creds, ctx) -> Outcome:
    base = env.get("public_host") or env["host"]
    term = env.get("suggest_term", "gotiek")
    response, secs = _fetch(
        f"{base}/extractor/api/suggest",
        creds,
        params={"projectId": env["project_id"], "language": env.get("suggest_language", "nl"), "searchString": term},
    )
    if (problem := _auth_problem(response)):
        return problem
    data = _json(response)
    if response.status_code != 200 or not isinstance(data, dict) or not data.get("success"):
        return Level.FAIL, f"HTTP {response.status_code}, suggest niet geslaagd", secs
    total = data.get("total", 0)
    if not total:
        return Level.FAIL, f"geen suggesties voor '{term}'", secs
    return Level.OK, f"{total} suggesties voor '{term}', {secs:.2f}s", secs


def check_public_uri(env, creds, ctx) -> Outcome:
    uri = env["concept_uri"]
    response, secs = _fetch(uri, None, accept="application/rdf+xml")
    if response.status_code != 200:
        return Level.FAIL, f"HTTP {response.status_code}", secs
    ctype = response.headers.get("content-type", "")
    if "rdf" not in ctype.lower():
        return Level.FAIL, f"geen RDF terug (content-type: {ctype or 'onbekend'})", secs
    if uri not in response.text:
        return Level.FAIL, "RDF bevat de concept-URI niet", secs
    return Level.OK, f"RDF/XML, {len(response.content)} bytes, {secs:.2f}s", secs


def _creds(env: dict) -> tuple[str | None, str] | None:
    token = os.getenv(env.get("token_env", "POOLPARTY_TOKEN"))
    if not token:
        return None
    user_env = env.get("user_env")
    return (os.getenv(user_env) if user_env else None, token)


def _project_name(project: dict) -> str:
    return project.get("label") or f"{project['id'][:8]}"


def build_tests(env: dict) -> list[tuple[str, Callable, bool]]:
    """(label-deel, functie(env, creds, ctx), vereist login)."""
    tests: list[tuple[str, Callable, bool]] = [("API + inloggen", check_projects, True)]
    for project in env.get("expected_projects") or [{"id": env["project_id"]}]:
        tests.append(
            (f"Project {_project_name(project)}", lambda e, c, x, p=project: check_project(e, c, x, p), True)
        )
    tests += [
        ("Concept ophalen", check_concept, True),
        ("Hiërarchie", check_hierarchy, True),
        ("Extractor (suggest)", check_suggest, True),
        ("Publieke URI (RDF)", check_public_uri, False),
    ]
    return tests


def run_environment(env: dict, slow_seconds: float) -> list[StatusEntry]:
    creds = _creds(env)
    ctx: dict = {}
    entries = []
    login_failed = False
    for name, func, needs_login in build_tests(env):
        label = f"PoolParty {env['name']}: {name}"
        url = env["host"]
        wait = _auth_backoff_until.get(env["name"], 0) - time.time()
        if needs_login and creds is not None and (login_failed or wait > 0):
            minutes = max(1, round(wait / 60)) if wait > 0 else AUTH_BACKOFF_SECONDS // 60
            entries.append(
                StatusEntry(
                    label=label,
                    level=Level.UNKNOWN,
                    detail=f"overgeslagen na mislukte login, volgende poging over ~{minutes} min (voorkomt accountblokkade)",
                    url=url,
                )
            )
            continue
        if needs_login and creds is None:
            entries.append(
                StatusEntry(
                    label=label,
                    level=Level.UNKNOWN,
                    detail=f"{env.get('token_env', 'POOLPARTY_TOKEN')} ontbreekt, check overgeslagen",
                    url=url,
                )
            )
            continue
        try:
            level, detail, secs = func(env, creds, ctx)
        except requests.exceptions.Timeout:
            entries.append(
                StatusEntry(
                    label=label,
                    level=Level.WARNING,
                    detail=f"geen antwoord binnen {TIMEOUT}s ({ATTEMPTS} pogingen)",
                    url=url,
                )
            )
            continue
        except Exception as exc:
            entries.append(StatusEntry(label=label, level=Level.FAIL, detail=f"fout: {type(exc).__name__}: {exc}", url=url))
            continue
        if level == Level.UNKNOWN and detail.startswith(AUTH_FAIL_PREFIX):
            login_failed = True
            _auth_backoff_until[env["name"]] = time.time() + AUTH_BACKOFF_SECONDS
        if level == Level.OK and secs > slow_seconds:
            level, detail = Level.WARNING, f"{detail} - traag (>{slow_seconds:g}s)"
        entries.append(StatusEntry(label=label, level=level, detail=detail, url=url))
    return entries


def gather_poolparty_statuses() -> list[StatusEntry]:
    cfg = load_sources()
    pp = cfg.get("poolparty", {})
    slow = pp.get("slow_seconds", DEFAULT_SLOW_SECONDS)
    entries: list[StatusEntry] = []
    for env in pp.get("environments", []):
        entries.extend(run_environment(env, slow))
    return apply_mutes(entries, cfg.get("mutes", []))
