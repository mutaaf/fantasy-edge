"""Report rendering.

One self-contained HTML file, no CDN, no build step. Open it anywhere,
mail it to your league, it still works in five years.
"""

from __future__ import annotations

import statistics

import json

import datetime
import html
import pathlib

from .analytics import Result

CSS = """
:root{--bg:#0e1416;--sf:#151d20;--sf2:#1b2528;--ln:#2a383c;--tx:#e4edec;
--mu:#7b9095;--dm:#516266;--gd:#4fd6a8;--wn:#f0a63c;--bd:#e4665c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);
font-family:'Barlow Semi Condensed',ui-sans-serif,system-ui,-apple-system,sans-serif;
line-height:1.45}
.wrap{max-width:1040px;margin:0 auto;padding:40px 20px 80px}
h1{font-size:30px;margin:0 0 4px;font-weight:600;letter-spacing:-.01em}
.sub{color:var(--mu);font-size:14px;margin-bottom:32px}
section{background:var(--sf);border:1px solid var(--ln);border-radius:10px;
padding:20px;margin-bottom:18px}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.18em;color:var(--dm);
margin:0 0 10px;font-weight:600}
.head{font-size:17px;margin:0 0 14px;color:var(--tx)}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:right;padding:6px 8px;color:var(--dm);font-weight:500;
border-bottom:1px solid var(--ln);font-size:11px;text-transform:uppercase;
letter-spacing:.08em;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
td{padding:6px 8px;border-bottom:1px solid var(--sf2);text-align:right;
font-variant-numeric:tabular-nums;font-family:ui-monospace,'IBM Plex Mono',monospace}
td:first-child{font-family:inherit;color:var(--tx)}
tbody tr:hover{background:var(--sf2)}
.pos{color:var(--gd)}.neg{color:var(--bd)}
.caveat{margin-top:14px;padding:10px 12px;border-radius:6px;background:var(--sf2);
border-left:2px solid var(--wn);color:var(--mu);font-size:12px}
.note{color:var(--dm);font-size:12px;margin-top:8px}
.empty{color:var(--dm);font-size:13px;font-style:italic}
footer{color:var(--dm);font-size:11px;margin-top:30px;line-height:1.7}
"""


def _cell(v) -> str:
    if v is None:
        return '<td style="color:var(--dm)">--</td>'
    if isinstance(v, (int, float)):
        cls = ""
        if isinstance(v, float) and abs(v) > 0:
            cls = ' class="pos"' if v > 0 else ' class="neg"'
        txt = f"{v:g}" if isinstance(v, float) else str(v)
        return f"<td{cls}>{html.escape(txt)}</td>"
    return f"<td>{html.escape(str(v))}</td>"


def _section(r: Result) -> str:
    parts = [f"<section><h2>{html.escape(r.title)}</h2>"]
    if r.empty:
        parts.append(f'<p class="empty">{html.escape(r.caveat or "No data.")}</p></section>')
        return "".join(parts)
    if r.headline:
        parts.append(f'<p class="head">{html.escape(r.headline)}</p>')
    parts.append("<table><thead><tr>")
    parts += [f"<th>{html.escape(c)}</th>" for c in r.columns]
    parts.append("</tr></thead><tbody>")
    for row in r.rows:
        parts.append("<tr>" + "".join(_cell(v) for v in row) + "</tr>")
    parts.append("</tbody></table>")
    if r.note:
        parts.append(f'<p class="note">{html.escape(r.note)}</p>')
    if r.caveat:
        parts.append(f'<p class="caveat"><b>Caveat.</b> {html.escape(r.caveat)}</p>')
    parts.append("</section>")
    return "".join(parts)


def render(results: list[Result], meta: dict, out_path: str | pathlib.Path) -> pathlib.Path:
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    seasons = meta.get("seasons", [])
    span = f"{min(seasons)} to {max(seasons)}" if seasons else "no seasons loaded"
    body = "".join(_section(r) for r in results)
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(meta.get('league_name') or 'League report')}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<style>{CSS}</style></head><body><div class="wrap">
<h1>{html.escape(meta.get('league_name') or 'League analytics')}</h1>
<p class="sub">{html.escape(meta.get('provider',''))} league {html.escape(str(meta.get('league_id','')))}
 · {span} · generated {stamp}</p>
{body}
<footer>
Every table above is computed from your own league history, not from projections.
Caveats are stated per analysis rather than buried; where a method has a real
limitation it is named in the box under the table.<br>
Regenerate any time with <code>python -m fantasyedge report</code>.
</footer>
</div></body></html>"""
    p = pathlib.Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(doc, encoding="utf-8")
    return p


def render_text(results: list[Result]) -> str:
    """Terminal rendering, same numbers as the HTML."""
    lines: list[str] = []
    for r in results:
        lines.append("")
        lines.append(f"── {r.title} " + "─" * max(0, 60 - len(r.title)))
        if r.empty:
            lines.append(f"   {r.caveat or 'no data'}")
            continue
        if r.headline:
            lines.append(f"   {r.headline}")
            lines.append("")
        widths = [max(len(str(c)), *(len(str(row[i])) for row in r.rows))
                  for i, c in enumerate(r.columns)]
        lines.append("   " + "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(r.columns)))
        for row in r.rows[:25]:
            lines.append("   " + "  ".join(
                ("--" if v is None else str(v)).ljust(widths[i]) for i, v in enumerate(row)))
        if len(r.rows) > 25:
            lines.append(f"   ... {len(r.rows) - 25} more rows, see the HTML report")
        if r.caveat:
            lines.append(f"   caveat: {r.caveat}")
    return "\n".join(lines)

# ─────────────────────────── standalone draft report ──────────────────────────

TEMPLATE = pathlib.Path(__file__).parent / "templates" / "draft_report.html"
_SKILL = ("QB", "RB", "WR", "TE")


def draft_report_payload(store, provider: str, league: str,
                         season: int | None = None, me: str | None = None) -> dict:
    """Everything the standalone draft page needs, for any league.

    Provider-agnostic on purpose: it reads the normalized tables, so a Yahoo
    or manually pasted league renders the same page an ESPN one does.
    """
    from . import analytics

    rows = store.q(
        """
        SELECT d.season, d.overall, d.round, d.team_id,
               p.name AS name, p.pos AS pos, a.rank AS rank
        FROM draft_pick d
        LEFT JOIN player p
               ON p.provider=d.provider AND p.player_id=d.player_id
        LEFT JOIN adp a
               ON a.season=d.season AND a.provider=d.provider
              AND a.player_id=d.player_id
        WHERE d.provider=? AND d.league_id=?
        ORDER BY d.overall
        """,
        (provider, league),
    )
    if not rows:
        raise ValueError(f"no draft picks stored for {provider}:{league}")
    season = season or max(r["season"] for r in rows)
    rows = [r for r in rows if r["season"] == season]

    owners = analytics._owner_map(store, provider, league)
    label = lambda tid: owners.get((season, tid), tid)

    # Draft slot comes from who owned each pick in round one.
    slots = {r["team_id"]: i + 1
             for i, r in enumerate(sorted((r for r in rows if r["round"] == 1),
                                          key=lambda r: r["overall"]))}

    teams: dict[str, dict] = {}
    for r in rows:
        t = teams.setdefault(r["team_id"], {
            "team": label(r["team_id"]), "slot": slots.get(r["team_id"], 0),
            "tid": r["team_id"], "you": r["team_id"] == me, "picks": [], "pos": {},
        })
        reach = (r["rank"] - r["overall"]) if r["rank"] is not None else None
        t["picks"].append({"o": r["overall"], "rd": r["round"],
                           "nm": r["name"] or "?", "pos": r["pos"] or "?",
                           "adp": round(r["rank"], 1) if r["rank"] is not None else None,
                           "reach": round(reach, 1) if reach is not None else None})
        t["pos"][r["pos"] or "?"] = t["pos"].get(r["pos"] or "?", 0) + 1

    scored = []
    for t in teams.values():
        # K and DEF carry placeholder ADP, so they stay out of the aggregates
        # for the same reason the storylines exclude them.
        sk = [p for p in t["picks"] if p["reach"] is not None and p["pos"] in _SKILL]
        early = [p["reach"] for p in sk if p["rd"] <= 5]
        t["meanReach"] = round(statistics.mean([p["reach"] for p in sk]), 1) if sk else 0
        t["earlyReach"] = round(statistics.mean(early), 1) if early else 0
        t["bestVal"] = min(sk, key=lambda p: p["reach"]) if sk else None
        t["worstReach"] = max(sk, key=lambda p: p["reach"]) if sk else None
        scored.append(t)
    scored.sort(key=lambda t: t["slot"])

    every = [(p, t) for t in scored for p in t["picks"]
             if p["reach"] is not None and p["pos"] in _SKILL]
    values = [{**p, "team": t["team"]}
              for p, t in sorted(every, key=lambda x: x[0]["reach"])[:6]]
    reaches = [{**p, "team": t["team"]}
               for p, t in sorted(every, key=lambda x: -x[0]["reach"])[:6]]

    meta = store.q(
        "SELECT name, team_count, scoring FROM league "
        "WHERE provider=? AND league_id=? AND season=?",
        (provider, league, season),
    )
    m = meta[0] if meta else {}
    adp_n = store.q("SELECT COUNT(*) AS n FROM adp WHERE provider=? AND season=?",
                    (provider, season))[0]["n"]

    st = analytics.draft_storylines(store, provider, league)
    stories = None if st.empty else {
        "headline": st.headline, "note": st.note,
        "caveat": st.caveat, "rows": st.rows,
    }

    return {
        "provider": provider, "leagueId": league, "season": season,
        "leagueName": (m.get("name") if isinstance(m, dict) else m["name"]) or f"League {league}",
        "teamCount": len(scored), "rounds": max(r["round"] for r in rows),
        "pickCount": len(rows), "scoring": "", "adpRows": adp_n,
        "leagueMean": round(statistics.mean([p["reach"] for p, _ in every]), 1) if every else 0,
        "teams": scored, "values": values, "reaches": reaches, "stories": stories,
    }


def render_draft_report(payload: dict, out_path: str | pathlib.Path) -> pathlib.Path:
    out = pathlib.Path(out_path)
    html = (TEMPLATE.read_text(encoding="utf-8")
            .replace("__TITLE__", f"{payload['season']} Draft Report")
            .replace("__DATA__", json.dumps(payload, separators=(",", ":"))))
    out.write_text(html, encoding="utf-8")
    return out
