"""Which team is yours, in what order, and what you have hidden.

This is the one piece of state the board writes rather than reads. It lives in
`~/.fantasy-edge/` beside the followed-leagues file, deliberately outside the
repository, for the same reason credentials do: it is yours, not the project's.

It is server-side rather than in browser storage because the console is meant
to run on more than one screen. A choice made on the laptop has to be the same
choice the television and the headset see, and `localStorage` is per-browser -
it would ask again on every surface, forever.
"""

from __future__ import annotations

import json
import pathlib

CONFIG = pathlib.Path.home() / ".fantasy-edge" / "prefs.json"
#: `projection` is which source drives the numbers on the board. It belongs
#: here with the rest for the same reason they do - the console runs on a
#: laptop, a television and a headset, and a source chosen on one of them has
#: to be the source the others show. An empty string means "not chosen", which
#: each client resolves to the first source it actually has loaded rather than
#: to a hardcoded name that may not be there.
DEFAULT = {"teams": {}, "order": [], "hidden": [], "projection": ""}


def load() -> dict:
    try:
        data = json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return dict(DEFAULT)
    out = dict(DEFAULT)
    if isinstance(data.get("teams"), dict):
        out["teams"] = {str(k): str(v) for k, v in data["teams"].items()}
    for key in ("order", "hidden"):
        if isinstance(data.get(key), list):
            out[key] = [str(x) for x in data[key]]
    if isinstance(data.get("projection"), str):
        out["projection"] = data["projection"][:32]
    return out


def save(prefs: dict) -> dict:
    clean = dict(DEFAULT)
    if isinstance(prefs.get("teams"), dict):
        clean["teams"] = {str(k)[:64]: str(v)[:64] for k, v in prefs["teams"].items()}
    for key in ("order", "hidden"):
        if isinstance(prefs.get(key), list):
            clean[key] = [str(x)[:64] for x in prefs[key]][:64]
    if isinstance(prefs.get("projection"), str):
        clean["projection"] = prefs["projection"][:32]
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(clean, indent=2))
    return clean


def merge(prefs: dict, patch: dict) -> dict:
    """Apply a partial update. Only the keys sent are touched, so two surfaces
    changing different things do not overwrite each other."""
    out = {"teams": dict(prefs.get("teams") or {}),
           "order": list(prefs.get("order") or []),
           "hidden": list(prefs.get("hidden") or []),
           "projection": str(prefs.get("projection") or "")}
    if isinstance(patch.get("teams"), dict):
        out["teams"].update({str(k): str(v) for k, v in patch["teams"].items()})
    for key in ("order", "hidden"):
        if isinstance(patch.get(key), list):
            out[key] = [str(x) for x in patch[key]]
    if isinstance(patch.get("projection"), str):
        out["projection"] = patch["projection"]
    return out
