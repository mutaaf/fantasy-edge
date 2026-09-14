"""Write design/tokens.json out as CSS custom properties.

    python3 tools/make_tokens.py            # writes fantasyedge/templates/tokens.css
    python3 tools/make_tokens.py --check    # exit 1 if the CSS is stale

The JSON is the source; this file is a rendering of it, like the pbxproj is a
rendering of the Swift sources. The scene endpoint embeds the same palette in
every payload and the visionOS app bundles the JSON itself, so a colour
changed here reaches the web board, the headset and any later client alike.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOKENS = ROOT / "design" / "tokens.json"
CSS = ROOT / "fantasyedge" / "templates" / "tokens.css"


def css_name(*parts: str) -> str:
    raw = "-".join(parts)
    return "--fe-" + re.sub(r"[^a-z0-9]+", "-", re.sub(r"([a-z])([A-Z])", r"\1-\2", raw).lower()).strip("-")


def render(tokens: dict) -> str:
    lines = ["/* Generated from design/tokens.json by tools/make_tokens.py. Do not edit. */",
             ":root {"]
    for name, value in tokens["color"].items():
        lines.append(f"  {css_name('color', *name.split('.'))}: {value};")
    for name, value in tokens["chip"].items():
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.startswith("#")):
            lines.append(f"  {css_name('chip', name)}: {value};")
    for name, value in tokens["motion"].items():
        if isinstance(value, (int, float)):
            unit = "s" if name.endswith("Seconds") else ""
            lines.append(f"  {css_name('motion', name)}: {value}{unit};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    out = render(json.loads(TOKENS.read_text()))
    if args.check:
        if not CSS.exists() or CSS.read_text() != out:
            sys.exit(f"{CSS.relative_to(ROOT)} is stale: run python3 tools/make_tokens.py")
        print("tokens.css is current")
        return
    CSS.write_text(out)
    print(f"wrote {CSS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
