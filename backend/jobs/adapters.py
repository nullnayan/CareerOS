"""One adapter contract for APIs and feeds; no network or database work at import.

An inventory entry is connectable only when it has a registered implementation.
New adapters reuse the same scheduler, checkpoints, ingestion and source health.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Adapter:
    provider: str
    kind: str
    scope: str
    authentication: str = "none"


ADAPTERS = {name: Adapter(name, "company_api", "company_board") for name in
            ("greenhouse", "lever", "ashby", "smartrecruiters", "workable")}
ADAPTERS.update({name: Adapter(name, "public_feed", "rolling_feed") for name in ("remotive", "jobicy", "himalayas")})
ADAPTERS["structured_feed"] = Adapter("structured_feed", "public_feed", "rolling_feed")
for name in ("workday", "taleo", "sap_successfactors", "oracle_recruiting", "icims"):
    ADAPTERS[name] = Adapter(name, "employer_configured", "rolling_feed")


def normalize(provider, board):
    from jobs.connectors import board_slug
    if provider not in ADAPTERS: raise ValueError("This platform has no registered collection adapter. Check its connection requirements.")
    if provider in {"remotive", "jobicy", "himalayas"}: return "public"
    if provider == "structured_feed": raise ValueError("Use the structured-feed setup with a public feed URL.")
    if ADAPTERS[provider].kind == "employer_configured": raise ValueError("Use employer connection setup with its exact public URL and access review.")
    return board_slug(provider, board)


def dispatch(provider, board, company, preferences):
    from jobs.engine import mode
    if mode() == "oss":
        from jobs.connectors import SourceError
        raise SourceError("Legacy adapter dispatch is inactive in open-source mode.")
    from jobs.connectors import greenhouse, lever, _bounded_board, SourceError
    from jobs.company_connectors import COMPANY_ADAPTERS
    from jobs.public_feeds import public_feed
    from jobs.structured_feeds import fetch_feed
    if provider not in ADAPTERS: raise SourceError("This source has no registered free collection adapter.")
    cursor = preferences.get("_cursor")
    if provider in {"remotive", "jobicy", "himalayas"}: return public_feed(provider, cursor)
    if provider == "structured_feed": return fetch_feed(preferences.get("_configuration") or {}, company, cursor)
    if ADAPTERS[provider].kind == "employer_configured":
        from jobs.enterprise import fetch
        return fetch(provider, company, preferences.get("_configuration") or {}, cursor)
    if provider == "greenhouse": return _bounded_board(greenhouse(board, company), cursor)
    if provider == "lever": return lever(board, company, int(cursor or 0))
    if provider == "smartrecruiters":
        offset = int(cursor or 0)
        result = COMPANY_ADAPTERS[provider](board, company, offset=offset, max_pages=1, max_details=8)
        if offset: result.complete, result.scope = False, "continuation"
        return result
    return _bounded_board(COMPANY_ADAPTERS[provider](board, company), cursor)
