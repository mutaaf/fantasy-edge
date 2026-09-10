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
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
APP = ROOT / "FantasyEdge"
PROJECT = ROOT / "FantasyEdge.xcodeproj"

BUNDLE = "com.mutaaf.fantasyedge"
DEPLOY = "2.0"          # runs on the visionOS 2.1 simulator that is installed
SWIFT = "5.0"


def oid(*parts: str) -> str:
    """A stable 24-hex object id."""
    return hashlib.sha1("/".join(parts).encode()).hexdigest()[:24].upper()


def main() -> None:
    sources = sorted(p.name for p in (APP / "Sources").glob("*.swift"))
    if not sources:
        raise SystemExit("no sources found")

    file_refs, build_files, group_children, sources_phase = [], [], [], []
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
        "resourcesBuildPhase", "configListProject", "configListTarget",
        "debugProject", "releaseProject", "debugTarget", "releaseTarget")}

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
        f'\t\t\t\tCODE_SIGN_STYLE = Automatic;\n'
        f'\t\t\t\tCODE_SIGNING_REQUIRED = NO;\n'
        f'\t\t\t\tCODE_SIGNING_ALLOWED = NO;\n'
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
\t\t\t);
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
\t\t\tfiles = ();
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
/* End PBXResourcesBuildPhase section */

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
