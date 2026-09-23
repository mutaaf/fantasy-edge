"""Fetch MakeHuman's CC0 asset packs for the crowd, and keep only CC0 assets.

Packs come only from the index's "shared under CC0" sections, as their
`_cc0.zip` archives. Each asset file (.mhclo, .mhskin, .mhmat, .proxy...) is
then checked on its own `license` line; anything not CC0 is dropped, so a
mislabelled file in a CC0 pack still cannot reach the kit. Source zips land
in .work (not committed). Writes the accepted list, with each asset's pack,
path and licence line, to .work/crowd/mh_assets.json for LICENSES.md.

    python3 tools/blender/crowd/fetch_mh_assets.py
"""
import hashlib
import json
import pathlib
import re
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
WORK = ROOT / ".work/crowd/mh"
PACKS = ["makehuman_system_assets", "skins01", "skins02", "hair01", "shirts01", "shoes01", "suits01", "hats01", "pants01"]
URL = "https://files2.makehumancommunity.org/asset_packs/{p}/{p}_cc0.zip"
LICENSED = {".mhclo", ".mhskin", ".mhmat", ".proxy", ".mhpxy", ".mhhair", ".target", ".bvh", ".mhpose"}


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    accepted, rejected = [], []
    for p in PACKS:
        z = WORK / f"{p}_cc0.zip"
        if not z.exists():
            print("downloading", p)
            urllib.request.urlretrieve(URL.format(p=p), z)
        sha = hashlib.sha256(z.read_bytes()).hexdigest()
        out = WORK / p
        with zipfile.ZipFile(z) as zf:
            zf.extractall(out)
        scanned = []
        for f in sorted(out.rglob("*")):
            if f.suffix.lower() not in LICENSED:
                continue
            text = f.read_text(errors="ignore")[:4000]
            m = re.search(r"(?im)^\s*#?\s*license\s+(.+)$", text) or re.search(r"(?i)\"license\"\s*:\s*\"([^\"]+)\"", text)
            lic = m.group(1).strip() if m else ""
            # System assets carry no license line; each file's header states the release instead.
            if not lic and re.search(r"(?i)this asset was explicitly released as CC0", text):
                lic = "CC0 (explicit release header)"
            scanned.append((f, lic))
        cc0 = lambda lic: bool(re.fullmatch(r"(?i)cc-?0(\s*1\.0)?|creative commons zero.*|cc-?0 .*", lic))
        # An asset is its directory. Its primary file (.mhclo, .proxy, .mhskin...) carries the
        # licence; a .mhmat with no licence field of its own is that asset's material and
        # inherits the primary's CC0. A material with no CC0 primary beside it (a community
        # skin) stays rejected, and so does any file naming a licence that is not CC0.
        primary_cc0 = {f.parent for f, lic in scanned if f.suffix.lower() != ".mhmat" and cc0(lic)}
        doomed_dirs, doomed = set(), []
        for f, lic in scanned:
            entry = {"pack": p, "zipSha256": sha, "file": str(f.relative_to(WORK)), "license": lic}
            if not cc0(lic) and not lic and f.suffix.lower() == ".mhmat" and f.parent in primary_cc0:
                entry["license"] = "CC0 (asset's material; inherits " + next(
                    g.name for g, l in scanned if g.parent == f.parent and g.suffix.lower() != ".mhmat" and cc0(l)) + ")"
            if cc0(entry["license"]) or entry["license"].startswith("CC0 ("):
                accepted.append(entry)
            else:
                rejected.append(entry)
                doomed.append(f)
                if f.parent not in primary_cc0:
                    doomed_dirs.add(f.parent)
        # Remove rejected assets after the scan, so the kit cannot load them: whole directories
        # with no CC0 primary, and single rejected files elsewhere.
        import shutil
        for d in doomed_dirs:
            if d.exists() and d != out:
                shutil.rmtree(d)
        for f in doomed:
            if f.exists():
                f.unlink()
    (ROOT / ".work/crowd/mh_assets.json").write_text(json.dumps({"accepted": accepted, "rejected": rejected}, indent=1))
    print(f"accepted {len(accepted)} CC0 assets, rejected {len(rejected)}")
    for r in rejected[:20]:
        print("  rejected", r["file"], repr(r["license"]))


main()
