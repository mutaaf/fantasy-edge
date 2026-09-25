#!/usr/bin/env python3
"""Emit Saturday.xcodeproj: one multiplatform target for visionOS, iOS and iPadOS.

# INTEGRATE: move to packages/tooling. This is fantasy-edge's
# apple/generate_project.py approach (a generated, deterministic pbxproj; ids
# from a hash of the path) extended to multiple platforms and resources. At
# the monorepo move both apps call one shared generator with their own
# settings; neither project file is ever edited by hand.

    python3 apps/saturday/apple/generate_project.py
    make build-visionos build-ios
"""
from __future__ import annotations

import hashlib
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
APP = ROOT / "Saturday"
PROJECT = ROOT / "Saturday.xcodeproj"
NAME = "Saturday"
BUNDLE = "com.mutaaf.saturday"
XROS, IOS, SWIFT = "2.0", "17.0", "5.0"


# The stadium is a package now (packages/swift/StadiumKit), visionOS only.
# This project links it for visionOS and not for iOS: the platform filter on
# the build file is what keeps an iPhone build from trying to link a library
# that has no iPhone version. The renderer itself is never copied here.
STADIUM_PACKAGE = "../../../packages/swift/StadiumKit"


def oid(*parts: str) -> str:
    return hashlib.sha1("/".join(parts).encode()).hexdigest()[:24].upper()


def main() -> None:
    sources = sorted(p.relative_to(APP).as_posix() for p in (APP / "Sources").rglob("*.swift"))
    resources = sorted(p.relative_to(APP).as_posix() for p in (APP / "Fonts").glob("*.ttf"))
    if not sources:
        raise SystemExit("no sources found")

    assets = ROOT.parents[2] / "assets"          # the monorepo's one copy
    has_assets = (assets / "actors").is_dir()
    file_refs, build_files, src_children, font_children, src_phase, res_phase = [], [], [], [], [], []
    for rel in sources + resources:
        name = pathlib.PurePosixPath(rel).name
        kind = "sourcecode.swift" if rel.endswith(".swift") else "file"
        fref, bfile = oid("fref", rel), oid("bfile", rel)
        file_refs.append(f'\t\t{fref} /* {name} */ = {{isa = PBXFileReference; lastKnownFileType = {kind}; '
                         f'name = "{name}"; path = "{NAME}/{rel}"; sourceTree = SOURCE_ROOT; }};')
        phase = "Sources" if rel.endswith(".swift") else "Resources"
        build_files.append(f'\t\t{bfile} /* {name} in {phase} */ = {{isa = PBXBuildFile; fileRef = {fref} /* {name} */; }};')
        (src_children if phase == "Sources" else font_children).append(f'\t\t\t\t{fref} /* {name} */,')
        (src_phase if phase == "Sources" else res_phase).append(f'\t\t\t\t{bfile} /* {name} in {phase} */,')

    ids = {k: oid(k) for k in (
        "project", "target", "productRef", "mainGroup", "sourcesGroup", "fontsGroup", "productsGroup",
        "sourcesBuildPhase", "frameworksBuildPhase", "resourcesBuildPhase", "configListProject",
        "stadiumPackage", "stadiumProduct", "stadiumBuildFile", "assetsBuildPhase",
        "configListTarget", "debugProject", "releaseProject", "debugTarget", "releaseTarget")}

    # The stadium's models, textures and sounds. Copied rather than referenced
    # so the bundle holds what StadiumAssets looks for (`assets/` beside the
    # executable), and rsync'd so a build costs milliseconds when nothing
    # changed. `.glb` is the web/Android twin of every `.usdz`; an Apple build
    # never opens one.
    assets_phase = assets_in_target = ""
    if has_assets:
        script = ("set -e\\n"
                  'DEST=\\"$TARGET_BUILD_DIR/$UNLOCALIZED_RESOURCES_FOLDER_PATH/assets\\"\\n'
                  'mkdir -p \\"$DEST\\"\\n'
                  "rsync -a --delete --exclude='*.glb' --exclude='review/' "
                  '\\"$SRCROOT/../../../assets/\\" \\"$DEST/\\"\\n')
        assets_phase = (
            f"\t\t{ids['assetsBuildPhase']} /* Copy StadiumAssets */ = {{\n"
            f"\t\t\tisa = PBXShellScriptBuildPhase;\n"
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


    common = (
        '\t\t\t\tGENERATE_INFOPLIST_FILE = YES;\n'
        f'\t\t\t\tINFOPLIST_FILE = "{NAME}/Info.plist";\n'
        '\t\t\t\tINFOPLIST_KEY_CFBundleDisplayName = Saturday;\n'
        '\t\t\t\tINFOPLIST_KEY_UIApplicationSceneManifest_Generation = YES;\n'
        '\t\t\t\tINFOPLIST_KEY_UIApplicationSupportsMultipleScenes = YES;\n'
        '\t\t\t\tINFOPLIST_KEY_UILaunchScreen_Generation = YES;\n'
        '\t\t\t\tINFOPLIST_KEY_NSLocalNetworkUsageDescription = "Saturday reads the slate from the Mac on your network.";\n'
        '\t\t\t\tINFOPLIST_KEY_UISupportedInterfaceOrientations_iPad = "UIInterfaceOrientationPortrait UIInterfaceOrientationPortraitUpsideDown UIInterfaceOrientationLandscapeLeft UIInterfaceOrientationLandscapeRight";\n'
        '\t\t\t\tINFOPLIST_KEY_UISupportedInterfaceOrientations_iPhone = "UIInterfaceOrientationPortrait UIInterfaceOrientationLandscapeLeft UIInterfaceOrientationLandscapeRight";\n'
        f'\t\t\t\tPRODUCT_BUNDLE_IDENTIFIER = {BUNDLE};\n'
        f'\t\t\t\tPRODUCT_NAME = {NAME};\n'
        f'\t\t\t\tSWIFT_VERSION = {SWIFT};\n'
        '\t\t\t\tSDKROOT = auto;\n'
        '\t\t\t\tSUPPORTED_PLATFORMS = "iphoneos iphonesimulator xros xrsimulator";\n'
        '\t\t\t\tSUPPORTS_MACCATALYST = NO;\n'
        '\t\t\t\tSUPPORTS_MAC_DESIGNED_FOR_IPHONE_IPAD = NO;\n'
        '\t\t\t\tSUPPORTS_XR_DESIGNED_FOR_IPHONE_IPAD = NO;\n'
        '\t\t\t\tTARGETED_DEVICE_FAMILY = "1,2,7";\n'
        f'\t\t\t\tIPHONEOS_DEPLOYMENT_TARGET = {IOS};\n'
        f'\t\t\t\tXROS_DEPLOYMENT_TARGET = {XROS};\n'
        '\t\t\t\tCODE_SIGN_STYLE = Automatic;\n'
        '\t\t\t\tCODE_SIGNING_REQUIRED = NO;\n'
        '\t\t\t\tCODE_SIGNING_ALLOWED = NO;\n')
    project_common = (
        '\t\t\t\tALWAYS_SEARCH_USER_PATHS = NO;\n'
        '\t\t\t\tCLANG_ENABLE_OBJC_ARC = YES;\n'
        '\t\t\t\tSDKROOT = auto;\n'
        f'\t\t\t\tIPHONEOS_DEPLOYMENT_TARGET = {IOS};\n'
        f'\t\t\t\tXROS_DEPLOYMENT_TARGET = {XROS};\n')

    nl = "\n"
    pbx = f"""// !$*UTF8*$!
{{
\tarchiveVersion = 1;
\tclasses = {{}};
\tobjectVersion = 56;
\tobjects = {{

/* Begin PBXBuildFile section */
\t\t{ids['stadiumBuildFile']} /* StadiumKit in Frameworks */ = {{isa = PBXBuildFile; platformFilters = (xros, ); productRef = {ids['stadiumProduct']} /* StadiumKit */; }};
{nl.join(build_files)}
/* End PBXBuildFile section */

/* Begin PBXFileReference section */
\t\t{ids['productRef']} /* {NAME}.app */ = {{isa = PBXFileReference; explicitFileType = wrapper.application; includeInIndex = 0; path = {NAME}.app; sourceTree = BUILT_PRODUCTS_DIR; }};
{nl.join(file_refs)}
/* End PBXFileReference section */

/* Begin PBXFrameworksBuildPhase section */
\t\t{ids['frameworksBuildPhase']} = {{
\t\t\tisa = PBXFrameworksBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
\t\t\t\t{ids['stadiumBuildFile']} /* StadiumKit in Frameworks */,
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
/* End PBXFrameworksBuildPhase section */

/* Begin PBXGroup section */
\t\t{ids['mainGroup']} = {{
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
\t\t\t\t{ids['sourcesGroup']} /* Sources */,
\t\t\t\t{ids['fontsGroup']} /* Fonts */,
\t\t\t\t{ids['productsGroup']} /* Products */,
\t\t\t);
\t\t\tsourceTree = "<group>";
\t\t}};
\t\t{ids['sourcesGroup']} /* Sources */ = {{
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
{nl.join(src_children)}
\t\t\t);
\t\t\tname = Sources;
\t\t\tsourceTree = "<group>";
\t\t}};
\t\t{ids['fontsGroup']} /* Fonts */ = {{
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
{nl.join(font_children)}
\t\t\t);
\t\t\tname = Fonts;
\t\t\tsourceTree = "<group>";
\t\t}};
\t\t{ids['productsGroup']} /* Products */ = {{
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
\t\t\t\t{ids['productRef']} /* {NAME}.app */,
\t\t\t);
\t\t\tname = Products;
\t\t\tsourceTree = "<group>";
\t\t}};
/* End PBXGroup section */

/* Begin PBXNativeTarget section */
\t\t{ids['target']} /* {NAME} */ = {{
\t\t\tisa = PBXNativeTarget;
\t\t\tbuildConfigurationList = {ids['configListTarget']};
\t\t\tbuildPhases = (
\t\t\t\t{ids['sourcesBuildPhase']},
\t\t\t\t{ids['frameworksBuildPhase']},
\t\t\t\t{ids['resourcesBuildPhase']},
{assets_in_target}\t\t\t);
\t\t\tbuildRules = ();
\t\t\tdependencies = ();
\t\t\tname = {NAME};
\t\t\tpackageProductDependencies = (
\t\t\t\t{ids['stadiumProduct']} /* StadiumKit */,
\t\t\t);
\t\t\tproductName = {NAME};
\t\t\tproductReference = {ids['productRef']} /* {NAME}.app */;
\t\t\tproductType = "com.apple.product-type.application";
\t\t}};
/* End PBXNativeTarget section */

/* Begin PBXProject section */
\t\t{ids['project']} = {{
\t\t\tisa = PBXProject;
\t\t\tpackageReferences = (
\t\t\t\t{ids['stadiumPackage']} /* XCLocalSwiftPackageReference "{STADIUM_PACKAGE}" */,
\t\t\t);
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
\t\t\t\t{ids['target']} /* {NAME} */,
\t\t\t);
\t\t}};
/* End PBXProject section */

/* Begin PBXResourcesBuildPhase section */
\t\t{ids['resourcesBuildPhase']} = {{
\t\t\tisa = PBXResourcesBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
{nl.join(res_phase)}
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
{nl.join(src_phase)}
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
/* End PBXSourcesBuildPhase section */

/* Begin XCBuildConfiguration section */
\t\t{ids['debugProject']} /* Debug */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
{project_common}\t\t\t\tDEBUG_INFORMATION_FORMAT = dwarf;
\t\t\t\tENABLE_TESTABILITY = YES;
\t\t\t\tGCC_OPTIMIZATION_LEVEL = 0;
\t\t\t\tONLY_ACTIVE_ARCH = YES;
\t\t\t\tSWIFT_ACTIVE_COMPILATION_CONDITIONS = DEBUG;
\t\t\t\tSWIFT_OPTIMIZATION_LEVEL = "-Onone";
\t\t\t}};
\t\t\tname = Debug;
\t\t}};
\t\t{ids['releaseProject']} /* Release */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
{project_common}\t\t\t\tDEBUG_INFORMATION_FORMAT = "dwarf-with-dsym";
\t\t\t\tSWIFT_COMPILATION_MODE = wholemodule;
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

/* Begin XCLocalSwiftPackageReference section */
\t\t{ids['stadiumPackage']} /* XCLocalSwiftPackageReference "{STADIUM_PACKAGE}" */ = {{
\t\t\tisa = XCLocalSwiftPackageReference;
\t\t\trelativePath = {STADIUM_PACKAGE};
\t\t}};
/* End XCLocalSwiftPackageReference section */

/* Begin XCSwiftPackageProductDependency section */
\t\t{ids['stadiumProduct']} /* StadiumKit */ = {{
\t\t\tisa = XCSwiftPackageProductDependency;
\t\t\tproductName = StadiumKit;
\t\t}};
/* End XCSwiftPackageProductDependency section */

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
    ref = (f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{ids["target"]}" '
           f'BuildableName="{NAME}.app" BlueprintName="{NAME}" ReferencedContainer="container:{NAME}.xcodeproj"/>')
    schemes = PROJECT / "xcshareddata" / "xcschemes"
    schemes.mkdir(parents=True, exist_ok=True)
    (schemes / f"{NAME}.xcscheme").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="1600" version="1.7">
   <BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES">
      <BuildActionEntries>
         <BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">
            {ref}
         </BuildActionEntry>
      </BuildActionEntries>
   </BuildAction>
   <LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.PosixSpawn" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugDocumentVersioning="YES" allowLocationSimulation="YES">
      <BuildableProductRunnable runnableDebuggingMode="0">
         {ref}
      </BuildableProductRunnable>
   </LaunchAction>
   <ProfileAction buildConfiguration="Release"/>
   <AnalyzeAction buildConfiguration="Debug"/>
   <ArchiveAction buildConfiguration="Release"/>
</Scheme>
""")
    print(f"wrote {PROJECT.name}: {len(sources)} sources, {len(resources)} fonts")


if __name__ == "__main__":
    main()
