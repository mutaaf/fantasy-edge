#!/usr/bin/env python3
"""Emit FantasyEdge.xcodeproj.

There is no xcodegen on this machine and a .pbxproj is not a thing to maintain
by hand, so it is generated. Deterministic ids from a hash of the path, so a
regeneration produces the same file rather than a diff full of churn.

    python3 apple/generate_project.py && \
      xcodebuild -project apple/FantasyEdge.xcodeproj -scheme FantasyEdge \
        -destination 'platform=visionOS Simulator,name=Apple Vision Pro' build
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import plistlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent
APP = ROOT / "FantasyEdge"
PROJECT = ROOT / "FantasyEdge.xcodeproj"

BUNDLE = "com.mutaaf.fantasyedge"
DEPLOY = "2.0"          # runs on the visionOS 2.1 simulator that is installed
SWIFT = "5.0"

PROFILES = pathlib.Path.home() / "Library/Developer/Xcode/UserData/Provisioning Profiles"


def oid(*parts: str) -> str:
    """A stable 24-hex object id."""
    return hashlib.sha1("/".join(parts).encode()).hexdigest()[:24].upper()


def team_from_profiles() -> tuple[str, str]:
    """The team that can already sign for a headset, read off this Mac.

    A machine can carry certificates for several teams - a paid membership and
    a free personal team look alike in the keychain, and both are "Apple
    Development: <name>". What tells them apart for our purpose is which one
    has a provisioning profile that names xrOS: that is a team whose devices
    and App IDs are registered for visionOS, which is what a device build
    needs. Returns (team id, why), or ("", why) when nothing qualifies.
    """
    if not PROFILES.is_dir():
        return "", "no provisioning profiles on this Mac"
    found: dict[str, str] = {}
    for p in sorted(PROFILES.glob("*.mobileprovision")):
        try:
            raw = subprocess.run(["security", "cms", "-D", "-i", str(p)],
                                 capture_output=True, check=True).stdout
            prof = plistlib.loads(raw)
        except Exception:
            continue
        platforms = {str(x).lower() for x in (prof.get("Platform") or [])}
        if not ({"xros", "visionos"} & platforms):
            continue
        for team in prof.get("TeamIdentifier") or []:
            found.setdefault(str(team), prof.get("TeamName") or "")
    if not found:
        return "", "no visionOS provisioning profile on this Mac"
    if len(found) > 1:
        names = ", ".join(f"{t} ({n})" for t, n in sorted(found.items()))
        return "", f"several visionOS teams, pick one with FE_TEAM: {names}"
    team, name = next(iter(found.items()))
    return team, f"the one visionOS team on this Mac: {team} ({name})"


def resolve_team() -> tuple[str, str]:
    """Which team to sign for, and where that answer came from.

    Order: an explicit `FE_TEAM`, then `apple/signing.json` (machine-local,
    gitignored), then whatever this Mac's profiles imply. Empty means nobody
    said and nothing could be inferred, which is fine: simulator builds do not
    sign, so the project stays usable and only `make device` complains.
    """
    if env := os.environ.get("FE_TEAM", "").strip():
        return env, "FE_TEAM in the environment"
    local = ROOT / "signing.json"
    if local.is_file():
        try:
            team = str(json.loads(local.read_text()).get("team", "")).strip()
            if team:
                return team, f"{local.name}"
        except Exception as exc:
            print(f"warning: {local} unreadable ({exc})")
    return team_from_profiles()


def main() -> None:
    # Recursive, because `Sources/Stadium/` is a folder of its own: the
    # renderer that is meant to lift out into a Swift package. A flat glob
    # would have left it out of the target and the build would have failed on
    # every type it defines.
    sources = sorted(str(p.relative_to(APP / "Sources"))
                     for p in (APP / "Sources").rglob("*.swift"))
    if not sources:
        raise SystemExit("no sources found")

    # The asset catalog holds the app icon. Without it in a Resources phase
    # the build still succeeds and the app still installs - it just wears the
    # blank disc, which is exactly how this went unnoticed: nothing fails, the
    # icon is simply absent. ASSETCATALOG_COMPILER_APPICON_NAME was already
    # set, pointing at a catalog nobody had added to the target.
    catalog = "Assets.xcassets" if (APP / "Assets.xcassets").is_dir() else ""

    file_refs, build_files, group_children, sources_phase = [], [], [], []
    resources_phase: list[str] = []
    if catalog:
        cref, cbuild = oid("fref", catalog), oid("bfile", catalog)
        file_refs.append(
            f'\t\t{cref} /* {catalog} */ = {{isa = PBXFileReference; '
            f'lastKnownFileType = folder.assetcatalog; '
            f'path = FantasyEdge/{catalog}; sourceTree = SOURCE_ROOT; }};')
        build_files.append(
            f'\t\t{cbuild} /* {catalog} in Resources */ = {{isa = PBXBuildFile; '
            f'fileRef = {cref} /* {catalog} */; }};')
        group_children.append(f'\t\t\t\t{cref} /* {catalog} */,')
        resources_phase.append(
            f'\t\t\t\t{cbuild} /* {catalog} in Resources */,')
    # The design tokens, bundled unchanged. The scene endpoint carries the
    # same palette, so this is the offline copy, not a second source.
    tokens = ROOT.parent / "design" / "tokens.json"
    if tokens.exists():
        tref, tbuild = oid("fref", "tokens.json"), oid("bfile", "tokens.json")
        file_refs.append(
            f'\t\t{tref} /* tokens.json */ = {{isa = PBXFileReference; '
            f'lastKnownFileType = text.json; path = ../design/tokens.json; '
            f'sourceTree = SOURCE_ROOT; }};')
        build_files.append(
            f'\t\t{tbuild} /* tokens.json in Resources */ = {{isa = PBXBuildFile; '
            f'fileRef = {tref} /* tokens.json */; }};')
        group_children.append(f'\t\t\t\t{tref} /* tokens.json */,')
        resources_phase.append(f'\t\t\t\t{tbuild} /* tokens.json in Resources */,')
    # The stadium's source assets. `assets/` used to go in as a folder
    # reference, which bundles it byte for byte - including two kinds of file
    # an Apple build never opens:
    #
    #   *.glb     every model is exported twice by the art bible's rule, .usdz
    #             for the headset and .glb for Three.js and Filament. Nothing
    #             in Swift opens a .glb; it is the other ports' half.  ~70 MB
    #   review/   look-dev renders, committed so a critique can point at them. ~35 MB
    #
    # That was 105 MB of a 292 MB bundle, which matters on a headset in a way
    # it never did in a simulator: it installs over Wi-Fi onto a device
    # somebody also keeps photographs on. So it is copied by a script phase
    # that leaves those out. The folder keeps its name and its shape, so
    # `StadiumAssets.folder` finds it exactly as before, and the export rule
    # and the test that pairs each model with its twin are untouched: this
    # changes what ships, not what is authored.
    assets = ROOT.parent / "assets"
    has_assets = (assets / "actors").is_dir()
    for name in sources:
        fref, bfile = oid("fref", name), oid("bfile", name)
        file_refs.append(
            f'\t\t{fref} /* {name} */ = {{isa = PBXFileReference; '
            f'lastKnownFileType = sourcecode.swift; path = {name}; '
            f'sourceTree = "<group>"; }};')
        build_files.append(
            f'\t\t{bfile} /* {name} in Sources */ = {{isa = PBXBuildFile; '
            f'fileRef = {fref} /* {name} */; }};')
        group_children.append(f'\t\t\t\t{fref} /* {name} */,')
        sources_phase.append(f'\t\t\t\t{bfile} /* {name} in Sources */,')

    ids = {k: oid(k) for k in (
        "project", "target", "productRef", "mainGroup", "sourcesGroup",
        "productsGroup", "sourcesBuildPhase", "frameworksBuildPhase",
        "resourcesBuildPhase", "assetsBuildPhase", "configListProject",
        "configListTarget", "debugProject", "releaseProject", "debugTarget",
        "releaseTarget")}

    team, why = resolve_team()
    print(f"signing team: {team or '(none)'} - {why}")

    # The assets copy, as a script phase (see the note where `has_assets` is
    # set). rsync rather than cp: --delete keeps a rebuild after an asset is
    # removed from leaving the old one behind in the bundle, which is the way
    # a stale asset survives for weeks.
    assets_phase = ""
    assets_in_target = ""
    if has_assets:
        excludes = "--exclude='*.glb' --exclude='review/'"
        script = ("set -e\\n"
                  'DEST=\\"$TARGET_BUILD_DIR/$UNLOCALIZED_RESOURCES_FOLDER_PATH/assets\\"\\n'
                  'mkdir -p \\"$DEST\\"\\n'
                  f'rsync -a --delete {excludes} \\"$SRCROOT/../assets/\\" \\"$DEST/\\"\\n')
        assets_phase = (
            f"\t\t{ids['assetsBuildPhase']} /* Copy StadiumAssets */ = {{\n"
            f"\t\t\tisa = PBXShellScriptBuildPhase;\n"
            # Declaring no outputs makes Xcode warn that the phase runs every
            # build. It should: rsync decides in milliseconds whether anything
            # changed, and listing 700 asset files as outputs to avoid a
            # warning would be worse than the warning. `alwaysOutOfDate` says
            # so deliberately, which is what silences it.
            f"\t\t\talwaysOutOfDate = 1;\n"
            f"\t\t\tbuildActionMask = 2147483647;\n"
            f"\t\t\tfiles = ();\n"
            f"\t\t\tinputPaths = ();\n"
            f'\t\t\tname = "Copy StadiumAssets";\n'
            f"\t\t\toutputPaths = ();\n"
            f"\t\t\trunOnlyForDeploymentPostprocessing = 0;\n"
            f"\t\t\tshellPath = /bin/sh;\n"
            f'\t\t\tshellScript = "{script}";\n'
            f"\t\t}};\n")
        assets_in_target = f"\t\t\t\t{ids['assetsBuildPhase']},\n"
    # Signing is per SDK on purpose. The simulator has never signed and must
    # not start: `CODE_SIGNING_ALLOWED = NO` there keeps every existing
    # simulator build and every look-dev shot byte-for-byte what it was. A
    # headset refuses an unsigned bundle, so the device SDK signs with the
    # team's Apple Development identity, chosen automatically.
    signing = (
        f'\t\t\t\tCODE_SIGN_STYLE = Automatic;\n'
        f'\t\t\t\t"CODE_SIGNING_ALLOWED[sdk=xrsimulator*]" = NO;\n'
        f'\t\t\t\t"CODE_SIGNING_REQUIRED[sdk=xrsimulator*]" = NO;\n'
        f'\t\t\t\t"CODE_SIGN_IDENTITY[sdk=xros*]" = "Apple Development";\n')
    if team:
        signing += f'\t\t\t\tDEVELOPMENT_TEAM = {team};\n'

    common = (
        f'\t\t\t\tINFOPLIST_KEY_UIApplicationSceneManifest_Generation = YES;\n'
        f'\t\t\t\tINFOPLIST_KEY_CFBundleDisplayName = "Fantasy Edge";\n'
        f'\t\t\t\tINFOPLIST_KEY_NSLocalNetworkUsageDescription = "Fantasy Edge '
        f'reads your league board from the Mac on your network.";\n'
        f'\t\t\t\tINFOPLIST_KEY_UIApplicationSupportsMultipleScenes = YES;\n'
        f'\t\t\t\tGENERATE_INFOPLIST_FILE = YES;\n'
        f'\t\t\t\tPRODUCT_BUNDLE_IDENTIFIER = {BUNDLE};\n'
        f'\t\t\t\tPRODUCT_NAME = FantasyEdge;\n'
        f'\t\t\t\tSWIFT_VERSION = {SWIFT};\n'
        f'\t\t\t\tXROS_DEPLOYMENT_TARGET = {DEPLOY};\n'
        f'\t\t\t\tSUPPORTED_PLATFORMS = "xros xrsimulator";\n'
        f'\t\t\t\tTARGETED_DEVICE_FAMILY = 7;\n'
        f'\t\t\t\tSDKROOT = xros;\n'
        f'{signing}'
        f'\t\t\t\tASSETCATALOG_COMPILER_APPICON_NAME = AppIcon;\n')

    nl = "\n"
    pbx = f"""// !$*UTF8*$!
{{
\tarchiveVersion = 1;
\tclasses = {{}};
\tobjectVersion = 56;
\tobjects = {{

/* Begin PBXBuildFile section */
{nl.join(build_files)}
/* End PBXBuildFile section */

/* Begin PBXFileReference section */
\t\t{ids['productRef']} /* FantasyEdge.app */ = {{isa = PBXFileReference; explicitFileType = wrapper.application; includeInIndex = 0; path = FantasyEdge.app; sourceTree = BUILT_PRODUCTS_DIR; }};
{nl.join(file_refs)}
/* End PBXFileReference section */

/* Begin PBXFrameworksBuildPhase section */
\t\t{ids['frameworksBuildPhase']} = {{
\t\t\tisa = PBXFrameworksBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = ();
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
/* End PBXFrameworksBuildPhase section */

/* Begin PBXGroup section */
\t\t{ids['mainGroup']} = {{
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
\t\t\t\t{ids['sourcesGroup']} /* Sources */,
\t\t\t\t{ids['productsGroup']} /* Products */,
\t\t\t);
\t\t\tsourceTree = "<group>";
\t\t}};
\t\t{ids['sourcesGroup']} /* Sources */ = {{
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
{nl.join(group_children)}
\t\t\t);
\t\t\tpath = FantasyEdge/Sources;
\t\t\tsourceTree = "<group>";
\t\t}};
\t\t{ids['productsGroup']} /* Products */ = {{
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
\t\t\t\t{ids['productRef']} /* FantasyEdge.app */,
\t\t\t);
\t\t\tname = Products;
\t\t\tsourceTree = "<group>";
\t\t}};
/* End PBXGroup section */

/* Begin PBXNativeTarget section */
\t\t{ids['target']} /* FantasyEdge */ = {{
\t\t\tisa = PBXNativeTarget;
\t\t\tbuildConfigurationList = {ids['configListTarget']};
\t\t\tbuildPhases = (
\t\t\t\t{ids['sourcesBuildPhase']},
\t\t\t\t{ids['frameworksBuildPhase']},
\t\t\t\t{ids['resourcesBuildPhase']},
{assets_in_target}\t\t\t);
\t\t\tbuildRules = ();
\t\t\tdependencies = ();
\t\t\tname = FantasyEdge;
\t\t\tproductName = FantasyEdge;
\t\t\tproductReference = {ids['productRef']} /* FantasyEdge.app */;
\t\t\tproductType = "com.apple.product-type.application";
\t\t}};
/* End PBXNativeTarget section */

/* Begin PBXProject section */
\t\t{ids['project']} = {{
\t\t\tisa = PBXProject;
\t\t\tattributes = {{
\t\t\t\tBuildIndependentTargetsInParallel = 1;
\t\t\t\tLastSwiftUpdateCheck = 1600;
\t\t\t\tLastUpgradeCheck = 1600;
\t\t\t}};
\t\t\tbuildConfigurationList = {ids['configListProject']};
\t\t\tcompatibilityVersion = "Xcode 14.0";
\t\t\tdevelopmentRegion = en;
\t\t\thasScannedForEncodings = 0;
\t\t\tknownRegions = (en, Base);
\t\t\tmainGroup = {ids['mainGroup']};
\t\t\tproductRefGroup = {ids['productsGroup']} /* Products */;
\t\t\tprojectDirPath = "";
\t\t\tprojectRoot = "";
\t\t\ttargets = (
\t\t\t\t{ids['target']} /* FantasyEdge */,
\t\t\t);
\t\t}};
/* End PBXProject section */

/* Begin PBXResourcesBuildPhase section */
\t\t{ids['resourcesBuildPhase']} = {{
\t\t\tisa = PBXResourcesBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
{chr(10).join(resources_phase)}
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
/* End PBXResourcesBuildPhase section */

/* Begin PBXShellScriptBuildPhase section */
{assets_phase}/* End PBXShellScriptBuildPhase section */

/* Begin PBXSourcesBuildPhase section */
\t\t{ids['sourcesBuildPhase']} = {{
\t\t\tisa = PBXSourcesBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
{nl.join(sources_phase)}
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
/* End PBXSourcesBuildPhase section */

/* Begin XCBuildConfiguration section */
\t\t{ids['debugProject']} /* Debug */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
\t\t\t\tALWAYS_SEARCH_USER_PATHS = NO;
\t\t\t\tCLANG_ENABLE_OBJC_ARC = YES;
\t\t\t\tCOPY_PHASE_STRIP = NO;
\t\t\t\tDEBUG_INFORMATION_FORMAT = dwarf;
\t\t\t\tENABLE_TESTABILITY = YES;
\t\t\t\tGCC_OPTIMIZATION_LEVEL = 0;
\t\t\t\tONLY_ACTIVE_ARCH = YES;
\t\t\t\tSWIFT_ACTIVE_COMPILATION_CONDITIONS = DEBUG;
\t\t\t\tSWIFT_OPTIMIZATION_LEVEL = "-Onone";
\t\t\t\tSDKROOT = xros;
\t\t\t\tXROS_DEPLOYMENT_TARGET = {DEPLOY};
\t\t\t}};
\t\t\tname = Debug;
\t\t}};
\t\t{ids['releaseProject']} /* Release */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
\t\t\t\tALWAYS_SEARCH_USER_PATHS = NO;
\t\t\t\tCLANG_ENABLE_OBJC_ARC = YES;
\t\t\t\tCOPY_PHASE_STRIP = NO;
\t\t\t\tDEBUG_INFORMATION_FORMAT = "dwarf-with-dsym";
\t\t\t\tSWIFT_COMPILATION_MODE = wholemodule;
\t\t\t\tSDKROOT = xros;
\t\t\t\tXROS_DEPLOYMENT_TARGET = {DEPLOY};
\t\t\t}};
\t\t\tname = Release;
\t\t}};
\t\t{ids['debugTarget']} /* Debug */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
{common}\t\t\t}};
\t\t\tname = Debug;
\t\t}};
\t\t{ids['releaseTarget']} /* Release */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
{common}\t\t\t}};
\t\t\tname = Release;
\t\t}};
/* End XCBuildConfiguration section */

/* Begin XCConfigurationList section */
\t\t{ids['configListProject']} = {{
\t\t\tisa = XCConfigurationList;
\t\t\tbuildConfigurations = (
\t\t\t\t{ids['debugProject']} /* Debug */,
\t\t\t\t{ids['releaseProject']} /* Release */,
\t\t\t);
\t\t\tdefaultConfigurationIsVisible = 0;
\t\t\tdefaultConfigurationName = Release;
\t\t}};
\t\t{ids['configListTarget']} = {{
\t\t\tisa = XCConfigurationList;
\t\t\tbuildConfigurations = (
\t\t\t\t{ids['debugTarget']} /* Debug */,
\t\t\t\t{ids['releaseTarget']} /* Release */,
\t\t\t);
\t\t\tdefaultConfigurationIsVisible = 0;
\t\t\tdefaultConfigurationName = Release;
\t\t}};
/* End XCConfigurationList section */
\t}};
\trootObject = {ids['project']};
}}
"""
    PROJECT.mkdir(exist_ok=True)
    (PROJECT / "project.pbxproj").write_text(pbx)

    shared = PROJECT / "xcshareddata" / "xcschemes"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "FantasyEdge.xcscheme").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="1600" version="1.7">
   <BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES">
      <BuildActionEntries>
         <BuildActionEntry buildForTesting="YES" buildForRunning="YES"
            buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">
            <BuildableReference BuildableIdentifier="primary"
               BlueprintIdentifier="{ids['target']}" BuildableName="FantasyEdge.app"
               BlueprintName="FantasyEdge" ReferencedContainer="container:FantasyEdge.xcodeproj"/>
         </BuildActionEntry>
      </BuildActionEntries>
   </BuildAction>
   <LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier=""
      selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.PosixSpawn"
      launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO"
      debugDocumentVersioning="YES" allowLocationSimulation="YES">
      <BuildableProductRunnable runnableDebuggingMode="0">
         <BuildableReference BuildableIdentifier="primary"
            BlueprintIdentifier="{ids['target']}" BuildableName="FantasyEdge.app"
            BlueprintName="FantasyEdge" ReferencedContainer="container:FantasyEdge.xcodeproj"/>
      </BuildableProductRunnable>
   </LaunchAction>
   <ProfileAction buildConfiguration="Release"/>
   <AnalyzeAction buildConfiguration="Debug"/>
   <ArchiveAction buildConfiguration="Release"/>
</Scheme>
""")
    print(f"wrote {PROJECT.relative_to(ROOT.parent)} with {len(sources)} sources")


if __name__ == "__main__":
    main()
