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
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fantasyedge.api import Api                                   # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "fantasyedge" / "templates" / "mosaic.html"
OUT = ROOT / "docs" / "index.html"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140.0"


def anonymise(data: dict) -> dict:
    """Scrub the people, keep the football."""
    labels: dict[str, str] = {}

    def label(name: str) -> str:
        if name not in labels:
            labels[name] = f"Team {len(labels) + 1}"
        return labels[name]

    for i, L in enumerate(data["leagues"], 1):
        L["league"] = f"League {i}"
        for side in ("you", "opp"):
            L[side]["name"] = label(L[side]["name"])
        L["priors"] = {label(k): v for k, v in (L.get("priors") or {}).items()}
    return data


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
