#!/usr/bin/env python3
"""Render the mosaic as a standalone page for GitHub Pages.

The board normally gets its static half injected by `fantasyedge api`. Pages
has no server, so this bakes that payload straight into the HTML and drops the
result in `docs/`, which GitHub serves as-is.

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
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fantasyedge.api import Api                                   # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "fantasyedge" / "templates" / "mosaic.html"
OUT = ROOT / "docs" / "index.html"
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/fantasy.db")
    ap.add_argument("--anon", action="store_true",
                    help="replace league and manager names with generic labels")
    ap.add_argument("--embed", action="store_true",
                    help="inline images as data URIs instead of using the CDN")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    api = Api(args.db)
    try:
        data = api.mosaics()
    finally:
        api.close()

    if args.anon:
        data = anonymise(data)
    images = embed_images(data) if args.embed else {}

    page = (TEMPLATE.read_text(encoding="utf-8")
            .replace("__DATA__", json.dumps(data, separators=(",", ":"), default=str))
            .replace("__IMAGES__", json.dumps(images, separators=(",", ":"))))
    page = ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<meta name=description content='Leverage Mosaic - a fantasy football "
            "board where every cell is sized by how much it can still change your "
            "week.'></head><body>" + page + "</body></html>")

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    (out.parent / ".nojekyll").write_text("")      # serve the files verbatim
    print(f"  wrote {out.relative_to(ROOT)}  {len(page) // 1024}KB  "
          f"{len(data['leagues'])} leagues{'  (anonymised)' if args.anon else ''}")


if __name__ == "__main__":
    main()
