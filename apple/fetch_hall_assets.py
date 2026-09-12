#!/usr/bin/env python3
"""Fetch and verify the CC0 assets the hall of fame borrows its light from.

The hall is a stadium at midday, and the thing that makes it read as one is a
real captured environment rather than a painted gradient. That environment is a
Poly Haven HDRI, and this script is how it gets onto a machine.

## Why a script and not a checked-in file

Same rule as everywhere else in this repository: **no binary asset is
committed.** The app icon is drawn by `tools/make_icon.py`, the nflverse
release is downloaded by `advanced.py` into `~/.fantasy-edge/`, and a 6 MB HDRI
is exactly the kind of blob that has no business in a git history. What *is*
committed is the manifest - a URL, a size, an md5 and a licence, in text - and
`FantasyEdge/Sources/HallAssets.swift` holds the same list so the app never has
to guess a URL. This script downloads them for inspection and, more usefully,
**re-verifies that manifest against the live API**, so the day Poly Haven moves
a file the failure is a red line here rather than a blank sky in a headset.

## The licences, verified rather than assumed

Every asset below is from https://polyhaven.com. Their licence page states, in
full sentences and unambiguously:

    All assets (HDRIs, textures and 3D models) on this site are the original
    work of Poly Haven staff, or artists who willingly and directly
    donate/sell their work to Poly Haven. Our assets are all licensed as CC0
    [...] You can use our assets for any purpose, including commercial work.
    You do not need to give credit or attribution when using them (although
    it is appreciated). You can redistribute them [...] even in a product you
    sell.

    -- https://polyhaven.com/license, read 2026-09-11

CC0 is a public-domain dedication, so there is no attribution obligation and no
share-alike. The app credits the photographers anyway, in the dial, because it
is appreciated and it costs one line. `--check` re-reads that page and fails if
the words "CC0" and "commercial" stop appearing on it, which is a crude test
and still better than trusting a memory of having read it once.

Note the licence is asserted site-wide by Poly Haven, not per item: the
`/info/<id>` endpoint carries no `license` field. That is why the site-wide
statement is quoted here in full rather than paraphrased.

Run:
    python3 apple/fetch_hall_assets.py            # verify, then download
    python3 apple/fetch_hall_assets.py --check    # verify only, no download
    python3 apple/fetch_hall_assets.py --where    # print the cache directory

Standard library only, like everything else here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
import urllib.request

API = "https://api.polyhaven.com"
LICENSE_PAGE = "https://polyhaven.com/license"
CACHE = pathlib.Path.home() / ".fantasy-edge" / "assets" / "hall"
SWIFT = pathlib.Path(__file__).resolve().parent / "FantasyEdge" / "Sources" \
    / "HallAssets.swift"

# What the room actually uses. Each entry names the Poly Haven asset id, the
# map and resolution, and the local filename the app caches it under.
#
# 2k for the HDRI, deliberately. It is an environment light and a distant
# backdrop, not something anybody reads text off: 4k is 25 MB for detail that
# only shows if you press your face against the horizon, and 8k is 102 MB and
# absurd for the job. 1k is available and is the honest choice on a slow link,
# but the sky is also drawn as the visible surround here and 1k shows its
# seams. 1k textures for the concrete because a plinth is a metre of surface
# seen from two metres away.
WANTED = [
    {
        "key": "sky",
        "asset": "orlando_stadium",
        "kind": "hdri",
        "res": "2k",
        "fmt": "hdr",
        "file": "orlando_stadium_2k.hdr",
        "why": "the light and the surround: a real football stadium at midday",
    },
    {
        "key": "concrete",
        "asset": "brushed_concrete_03",
        "kind": "Diffuse",
        "res": "1k",
        "fmt": "jpg",
        "file": "brushed_concrete_03_diff_1k.jpg",
        "why": "the plinths",
    },
    {
        "key": "concreteRough",
        "asset": "brushed_concrete_03",
        "kind": "Rough",
        "res": "1k",
        "fmt": "jpg",
        "file": "brushed_concrete_03_rough_1k.jpg",
        "why": "the plinths, roughness",
    },
]


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "fantasy-edge/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def api(path: str) -> dict:
    return json.loads(get(API + path))


def licence_ok() -> tuple[bool, str]:
    """Re-read the licence page rather than trusting the comment above."""
    try:
        text = re.sub(r"<[^>]+>", " ", get(LICENSE_PAGE).decode("utf-8", "replace"))
    except Exception as e:                                  # noqa: BLE001
        return False, f"could not read {LICENSE_PAGE}: {e}"
    flat = re.sub(r"\s+", " ", text)
    if "CC0" not in flat:
        return False, "the licence page no longer says CC0"
    if "commercial" not in flat.lower():
        return False, "the licence page no longer mentions commercial use"
    return True, "CC0, commercial use permitted, attribution not required"


def resolve(item: dict) -> dict:
    """Look the file up in the live API. Never build a CDN URL by hand."""
    files = api(f"/files/{item['asset']}")
    node = files[item["kind"]][item["res"]]
    node = node[item["fmt"]] if item["fmt"] in node else node
    info = api(f"/info/{item['asset']}")
    return {
        "key": item["key"],
        "asset": item["asset"],
        "name": info.get("name", item["asset"]),
        "authors": info.get("authors", {}),
        "categories": info.get("categories", []),
        "tags": info.get("tags", []),
        "file": item["file"],
        "url": node["url"],
        "size": node["size"],
        "md5": node.get("md5", ""),
        "why": item["why"],
        "source": f"https://polyhaven.com/a/{item['asset']}",
        "licence": "CC0 1.0 Universal (public domain dedication)",
    }


def pinned() -> dict[str, dict]:
    """The URLs and hashes the app itself is compiled with."""
    if not SWIFT.exists():
        return {}
    src = SWIFT.read_text()
    out = {}
    for m in re.finditer(
            r'Asset\(\s*key:\s*"([^"]+)"[^)]*?url:\s*"([^"]+)"[^)]*?'
            r'md5:\s*"([^"]*)"[^)]*?bytes:\s*(\d+)', src, re.S):
        out[m.group(1)] = {"url": m.group(2), "md5": m.group(3),
                           "size": int(m.group(4))}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="verify the manifest against the live API, download nothing")
    ap.add_argument("--where", action="store_true", help="print the cache directory")
    args = ap.parse_args()

    if args.where:
        print(CACHE)
        return 0

    ok, verdict = licence_ok()
    print(f"licence  {LICENSE_PAGE}: {verdict}")
    if not ok:
        print("\nFAIL - stop and re-read the licence before shipping anything "
              "that uses these files.", file=sys.stderr)
        return 1

    live = [resolve(i) for i in WANTED]
    have = pinned()
    bad = []
    for a in live:
        p = have.get(a["key"])
        mark = "  "
        if p is None:
            mark, note = "??", "not pinned in HallAssets.swift"
        elif p["url"] != a["url"] or p["md5"] != a["md5"] or p["size"] != a["size"]:
            mark, note = "!!", "PINNED COPY DISAGREES WITH THE LIVE API"
            bad.append(a["key"])
        else:
            note = "pinned and matching"
        who = ", ".join(a["authors"]) or "unknown"
        print(f"{mark} {a['key']:14s} {a['name']:22s} {a['size']/1e6:6.2f} MB  "
              f"{a['licence']}  by {who}  ({note})")
        print(f"       {a['why']}")
        print(f"       {a['source']}")

    manifest = {"read": LICENSE_PAGE, "verdict": verdict, "assets": live}
    if args.check:
        if bad:
            print(f"\nFAIL - update HallAssets.swift for: {', '.join(bad)}",
                  file=sys.stderr)
            return 1
        print("\nOK")
        return 0

    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    total = 0
    for a in live:
        dest = CACHE / a["file"]
        if dest.exists() and len(dest.read_bytes()) == a["size"]:
            print(f"have  {a['file']}")
            total += a["size"]
            continue
        print(f"fetch {a['file']} ({a['size']/1e6:.2f} MB)")
        blob = get(a["url"])
        got = hashlib.md5(blob).hexdigest()          # integrity, not security
        if a["md5"] and got != a["md5"]:
            print(f"  md5 mismatch: {got} != {a['md5']}", file=sys.stderr)
            return 1
        dest.write_bytes(blob)
        total += len(blob)

    print(f"\n{total/1e6:.2f} MB in {CACHE}")
    print("The app fetches these itself over the network and caches them in its "
          "own container; this copy is for inspection and for working offline. "
          "Nothing here is ever written into the repository.")
    if bad:
        print(f"\nFAIL - HallAssets.swift is out of date for: {', '.join(bad)}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
