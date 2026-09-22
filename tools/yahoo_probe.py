"""What does a Yahoo credential actually reach? Ask it, don't guess.

Reconnaissance, not a feature. Probes every Yahoo surface this project might
plausibly want - the Fantasy Sports API it already speaks, and the sports-data
endpoints it does not - and reports status codes and response shapes so the
question "is a second source worth it" can be answered with evidence.

    python3 tools/yahoo_probe.py            # fantasy + sports data
    python3 tools/yahoo_probe.py --only sports

Credentials come from the environment (source ~/.fantasy-edge/env first) and
the token from ~/.fantasy-edge/yahoo.json, exactly as providers/yahoo.py does.
Nothing here prints a token, a secret, or a response body that might carry one:
every probe reports a status, a size and a shape. That is a rule, not a
courtesy - a probe script is precisely the kind of thing whose output gets
pasted into a chat window.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fantasyedge.providers.yahoo import YahooAuth  # noqa: E402

UA = "fantasy-edge/1.0 (yahoo probe)"
FANTASY = "https://fantasysports.yahooapis.com/fantasy/v2"

# Fantasy Sports, the surface the `fspt-r` scope is actually for.
FANTASY_PROBES = [
    ("games, all sports", f"{FANTASY}/users;use_login=1/games"),
    ("nfl leagues", f"{FANTASY}/users;use_login=1/games;game_keys=nfl/leagues"),
    ("nfl game metadata", f"{FANTASY}/game/nfl"),
    ("game stat categories", f"{FANTASY}/game/nfl/stat_categories"),
    ("game position types", f"{FANTASY}/game/nfl/position_types"),
]

# Per-league probes, filled in once a league key is discovered.
LEAGUE_PROBES = [
    ("league", "{lg}"),
    ("league settings", "{lg}/settings"),
    ("standings", "{lg}/standings"),
    ("scoreboard", "{lg}/scoreboard"),
    ("teams", "{lg}/teams"),
    ("draft results", "{lg}/draftresults"),
    ("transactions", "{lg}/transactions"),
    ("players, first 25", "{lg}/players"),
]

# Sports data. None of these is documented as part of the Fantasy Sports API;
# the point is to establish empirically whether this credential reaches any of
# them, since "Yahoo Sports API" means different things to different people.
SPORTS_PROBES = [
    ("sports core, nfl",
     "https://sports.yahooapis.com/v1/sports/nfl"),
    ("sports scoreboard",
     "https://sports.yahooapis.com/v1/sports/nfl/scoreboard"),
    ("sports games",
     "https://sports.yahooapis.com/v1/sports/nfl/games"),
    ("yql-era sports",
     "https://query.yahooapis.com/v1/public/yql?q=select%20*%20from%20fantasysports.games"),
    ("frontpage scores api (public, no auth)",
     "https://api-secure.sports.yahoo.com/v1/editorial/s/scoreboard?leagues=nfl"),
    ("sports graphite (public, no auth)",
     "https://graphite-secure.sports.yahoo.com/v1/query/shangrila/scoreboard?lang=en-US&region=US&tz=America%2FNew_York&leagues=nfl"),
]


def shape(node, depth: int = 0, limit: int = 3) -> str:
    """Describe JSON structurally. Keys are structure; values may be secrets."""
    if depth > limit:
        return "..."
    if isinstance(node, dict):
        keys = list(node.keys())[:8]
        inner = ", ".join(f"{k}:{shape(node[k], depth + 1, limit)}" for k in keys)
        more = f", +{len(node) - len(keys)}" if len(node) > len(keys) else ""
        return "{" + inner + more + "}"
    if isinstance(node, list):
        if not node:
            return "[]"
        return f"[{len(node)} x {shape(node[0], depth + 1, limit)}]"
    return type(node).__name__


def get(url: str, token: str | None) -> tuple[int, str, object]:
    """GET a URL. Returns (status, note, parsed-or-None). Never raises."""
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(url + sep + "format=json", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        with exc:
            body = exc.read()
        # The status is the finding. The body may echo a request, so it is
        # measured and described, never quoted.
        note = f"{len(body)}B"
        try:
            parsed = json.loads(body)
            desc = parsed.get("error", {}).get("description", "") if isinstance(parsed, dict) else ""
            if desc and "token" not in desc.lower():
                note = desc[:80]
        except ValueError:
            pass
        return exc.code, note, None
    except urllib.error.URLError as exc:
        return 0, f"unreachable: {exc.reason}", None
    except Exception as exc:  # pragma: no cover - defensive
        return 0, f"{type(exc).__name__}", None
    try:
        return status, f"{len(raw)}B", json.loads(raw)
    except ValueError:
        head = raw[:16].decode("utf-8", "replace").strip()
        kind = "html" if head.lower().startswith("<") else "non-json"
        return status, f"{len(raw)}B {kind}", None


def report(label: str, status: int, note: str, parsed) -> None:
    mark = "ok " if 200 <= status < 300 else "  "
    print(f"  {mark}{status:>3}  {label:<38} {note}")
    if parsed is not None and 200 <= status < 300:
        print(f"          shape: {shape(parsed)[:220]}")


def find_league_keys(parsed) -> list[str]:
    """Pull `{game_key}.l.{league_id}` keys out of Yahoo's costumed XML."""
    found: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "league_key" and isinstance(v, str):
                    found.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(parsed)
    return sorted(set(found))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=("fantasy", "sports"), default=None)
    args = ap.parse_args()

    token = None
    if args.only != "sports":
        auth = YahooAuth()
        try:
            token = auth.access_token()
            print("token: refreshed ok (value not shown)\n")
        except Exception as exc:
            print(f"token: FAILED - {type(exc).__name__}: {exc}\n")
            return

    if args.only != "sports":
        print("FANTASY SPORTS API")
        league_keys: list[str] = []
        for label, url in FANTASY_PROBES:
            status, note, parsed = get(url, token)
            report(label, status, note, parsed)
            if parsed is not None and "leagues" in url:
                league_keys = find_league_keys(parsed)

        if league_keys:
            print(f"\n  league keys discovered: {len(league_keys)}")
            for k in league_keys:
                print(f"    {k}")
            newest = league_keys[-1]
            print(f"\n  per-league probes on {newest}")
            for label, tmpl in LEAGUE_PROBES:
                url = f"{FANTASY}/league/{tmpl.format(lg=newest)}"
                status, note, parsed = get(url, token)
                report(label, status, note, parsed)
        else:
            print("\n  no league keys found")
        print()

    if args.only != "fantasy":
        print("SPORTS DATA")
        for label, url in SPORTS_PROBES:
            use = token if "yahooapis.com" in url else None
            status, note, parsed = get(url, use)
            report(label, status, note, parsed)


if __name__ == "__main__":
    main()
