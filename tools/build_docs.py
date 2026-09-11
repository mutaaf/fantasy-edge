#!/usr/bin/env python3
"""Build the GitHub Pages site: an entry page and a demo board.

Pages has no server, so both halves have to be files.

    docs/index.html   connect.html - how a visitor reaches their *own* leagues
    docs/demo.html    the mosaic with one real season baked into it

The split exists because the demo alone was a dead end. A visitor landing on
somebody else's anonymised season sees dummy data and no way in, which is a
worse first impression than no page at all. So the front door is now the
connect page, which needs no build input at all: it talks to Sleeper and to
ESPN's public endpoints straight from the visitor's browser. The demo stays
exactly where it was in substance, one click away, and is labelled as what it
is rather than being passed off as anybody's live board.

    python3 tools/build_docs.py                # real leagues, images from the CDN
    python3 tools/build_docs.py --anon         # team and manager names scrubbed
    python3 tools/build_docs.py --embed        # inline images, no CDN needed

`--anon` matters if the repository is public. NFL players are public facts and
stay; the people in your league are not, so their team names become "Team 3".
`--embed` is for hosts that block external images - the Artifact sandbox does,
GitHub Pages does not, so it is off by default and keeps the page ~50KB
instead of ~2MB.
"""

from __future__ import annotations

import argparse
import base64
import json
import pathlib
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fantasyedge.api import Api                                   # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "fantasyedge" / "templates" / "mosaic.html"
CONNECT = ROOT / "fantasyedge" / "templates" / "connect.html"
OUT = ROOT / "docs" / "index.html"
DEMO = "demo.html"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140.0"


def anonymise(data: dict) -> dict:
    """Scrub the people, keep the football.

    Done as a sweep over every string in the payload rather than by naming the
    fields to clean. The field-by-field version missed `roster[].owner` and
    `teams[].name` - eighty-four real names that would have gone public in a
    build labelled anonymised, which is worse than not offering the flag at
    all. A sweep cannot miss a field somebody adds later.
    """
    labels: dict[str, str] = {}

    def label(name: str) -> str:
        key = (name or "").strip()
        if not key:
            return name
        if key not in labels:
            labels[key] = f"Team {len(labels) + 1}"
        return labels[key]

    # Collect every manager and league name first, so the mapping is stable
    # wherever the same person turns up.
    people: set[str] = set()
    for L in data.get("leagues") or []:
        for side in ("you", "opp"):
            n = ((L.get(side) or {}).get("name") or "").strip()
            if n:
                people.add(n)
        for t in L.get("teams") or []:
            if (t.get("name") or "").strip():
                people.add(t["name"].strip())
        for r in L.get("roster") or []:
            if (r.get("owner") or "").strip():
                people.add(r["owner"].strip())
        for k in (L.get("priors") or {}):
            if k.strip():
                people.add(k.strip())
    for n in sorted(people):
        label(n)

    leagues = {}
    for i, L in enumerate(data.get("leagues") or [], start=1):
        if L.get("league"):
            leagues[L["league"]] = f"League {i}"

    # One alternation, longest first, applied in a single pass. Longest first
    # so "Team Riaz" is not half-replaced by "Team". Single pass because
    # replacing name by name rescans text it has already substituted: a real
    # team called "Team 8" - ESPN's own placeholder for an unnamed team, and
    # present in real data - would match the label "Team 8" generated for
    # somebody else and rewrite it again, quietly merging two managers into
    # one person. No leak, but the anonymised league would be wrong.
    swaps = {**labels, **leagues}
    pattern = re.compile("|".join(re.escape(k) for k in
                                  sorted(swaps, key=len, reverse=True))) if swaps else None

    def scrub(value):
        if isinstance(value, dict):
            return {k: scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        if isinstance(value, str):
            return pattern.sub(lambda m: swaps[m.group(0)], value) if pattern else value
        return value

    scrubbed = scrub(data)
    # priors are keyed by name, so rebuild the keys too
    for L in scrubbed.get("leagues") or []:
        if isinstance(L.get("priors"), dict):
            L["priors"] = {labels.get(k.strip(), k): v
                           for k, v in L["priors"].items()}
    return scrubbed


def fetch(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read()
    except Exception:
        return None                     # a missing portrait must not fail a build


def embed_images(data: dict) -> dict:
    want: dict[str, str] = {}
    for L in data["leagues"]:
        for side in ("you", "opp"):
            for s in L[side]["starters"]:
                if s.get("img"):
                    want[f"p_{s['id']}"] = s["img"]
                if s.get("logo"):
                    want[f"t_{s['team']}"] = s["logo"]
    out = {}
    for key, url in sorted(want.items()):
        blob = fetch(url)
        if blob:
            out[key] = "data:image/png;base64," + base64.b64encode(blob).decode()
    print(f"  embedded {len(out)}/{len(want)} images")
    return out


#: Pinned over the demo board. The demo is one real person's real season with
#: the people scrubbed out, and a visitor who arrives on it with no context
#: reasonably reads it as either dummy data or as their own - both wrong. The
#: ribbon is injected here rather than added to mosaic.html so the board stays
#: one template whether it is served by `fantasyedge api` or baked for Pages;
#: only the Pages copy is a demo.
RIBBON = (
    "<div style=\"position:fixed;left:12px;bottom:12px;z-index:2147483000;"
    "max-width:330px;font:500 12px/1.5 -apple-system,BlinkMacSystemFont,"
    "'Helvetica Neue',sans-serif;color:#fff;background:rgba(5,15,56,.94);"
    "border:1px solid rgba(255,255,255,.28);border-radius:11px;padding:9px 12px;"
    "box-shadow:0 8px 26px rgba(0,0,0,.5)\">"
    "<b style=\"letter-spacing:.14em;font-size:10.5px;color:#6fd84a\">DEMO BOARD</b>"
    "<div style=\"margin-top:3px;color:rgba(255,255,255,.8)\">One real season, "
    "played by one real league, with every manager's name removed. Not your data. "
    "<a href=\"index.html\" style=\"color:#6fd84a\">Connect your own &rarr;</a></div>"
    "</div>")


#: The tab icon, inline. It is written out here rather than shipped as a file
#: because a linked icon is one more request to get wrong and a .ico is a
#: binary blob in a repository that otherwise has none - this is text, and it
#: is editable by hand.
#:
#: No plate behind it. The plated version lost most of its sixteen pixels to
#: navy padding and read as a green smudge in a tab; the bare ball fills the
#: square, and mid-green holds against both a white tab strip and a dark one,
#: which is the whole of what "dark mode safe" has to mean for a favicon.
# The same identity as the app icon, cut down until it survives 16 pixels.
#
# The app icon is turf, yard lines and a leather ball; a tab favicon cannot
# carry all three - at 16px the stripes alias into noise and brown on green
# goes muddy. So this keeps the two things that read at any size: the turf
# green ground and the ball's silhouette with its lacing, in chalk. Same
# palette, same object, less of it. A shrunken copy of the app icon would be
# a smudge, which is the usual way an icon family loses its family.
FAVICON = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
    "<rect width='64' height='64' rx='14' fill='#1e5b2a'/>"
    # One mown stripe either side, enough to say turf without becoming texture.
    "<rect x='8' y='0' width='10' height='64' fill='#24642e'/>"
    "<rect x='30' y='0' width='10' height='64' fill='#24642e'/>"
    "<rect x='52' y='0' width='10' height='64' fill='#24642e'/>"
    "<g transform='rotate(-32 32 32)'>"
    "<ellipse cx='32' cy='32' rx='22' ry='13.5' fill='#7a3b1d'"
    " stroke='#f2f6f0' stroke-width='2.5'/>"
    "<g stroke='#f2f6f0' stroke-linecap='round' fill='none'>"
    "<path d='M23 32h18' stroke-width='3.4'/>"
    "<path d='M27 28.4v7.2M32 28.4v7.2M37 28.4v7.2' stroke-width='2.6'/>"
    "</g></g></svg>")


def favicon_link() -> str:
    """A data URI, so the icon adds no host to the page's allowlist.

    Declared explicitly rather than left to the server: these pages are static
    files under a path on somebody else's domain, and a bare /favicon.ico is a
    request to the domain root that this deployment neither owns nor serves -
    which is exactly the 404 that was being logged.
    """
    uri = "data:image/svg+xml," + urllib.parse.quote(FAVICON, safe="='/ ")
    return f"<link rel=icon type='image/svg+xml' href=\"{uri}\">"


def wrap(body: str, description: str, title: str) -> str:
    """The document skeleton both pages share."""
    return ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{title}</title>"
            f"<meta name=description content='{description}'>"
            + favicon_link() +
            "</head><body>" + body + "</body></html>")


def build_connect(out: pathlib.Path) -> int:
    """The entry page. Takes no build input at all - by design.

    Everything it shows, it fetches from the visitor's own browser, so there is
    nothing here to bake in and nothing about it that could leak one league's
    data into another visitor's page.
    """
    page = wrap(
        CONNECT.read_text(encoding="utf-8"),
        "Connect your own fantasy football leagues - Sleeper needs no "
        "credentials, a public ESPN league needs none either, and nothing is "
        "sent anywhere.",
        "Connect your leagues - fantasy-edge")
    out.write_text(page, encoding="utf-8")
    return len(page)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/fantasy.db")
    ap.add_argument("--anon", action="store_true",
                    help="replace league and manager names with generic labels")
    ap.add_argument("--embed", action="store_true",
                    help="inline images as data URIs instead of using the CDN")
    ap.add_argument("--out", default=str(OUT),
                    help="the entry page; the demo board is written beside it")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    (out.parent / ".nojekyll").write_text("")      # serve the files verbatim

    # The entry page first, and unconditionally. It needs no database, so an
    # empty or missing one must still leave visitors a working front door
    # rather than a 404 where the site used to be.
    size = build_connect(out)
    print(f"  wrote {out.relative_to(ROOT)}  {size // 1024}KB  (connect)")

    api = Api(args.db)
    try:
        data = api.mosaics()
        # Baked in for the same reason the served page inlines it: the demo has
        # no API behind it, and a source picker that cannot switch anything is
        # worse than none. It carries player names and numbers only - no league
        # and no manager - so it needs no scrubbing and gets none, which is
        # also why it is added after mosaics() rather than folded into it.
        try:
            data["projections"] = api.projections({})
        except Exception as exc:
            print(f"  no projections baked in: {exc}")
            data["projections"] = None
    finally:
        api.close()

    if args.anon:
        data = anonymise(data)
    images = embed_images(data) if args.embed else {}

    page = (TEMPLATE.read_text(encoding="utf-8")
            .replace("__DATA__", json.dumps(data, separators=(",", ":"), default=str))
            .replace("__IMAGES__", json.dumps(images, separators=(",", ":"))))
    page = wrap(RIBBON + page,
                "Leverage Mosaic - a fantasy football board where every cell is "
                "sized by how much it can still change your week. A demo built "
                "from one real, anonymised season.",
                "Demo board - fantasy-edge")

    demo = out.parent / DEMO
    demo.write_text(page, encoding="utf-8")
    print(f"  wrote {demo.relative_to(ROOT)}  {len(page) // 1024}KB  "
          f"{len(data['leagues'])} leagues{'  (anonymised)' if args.anon else ''}")


if __name__ == "__main__":
    main()
