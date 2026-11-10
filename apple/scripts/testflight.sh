#!/bin/sh
# Archive the Fantasy Edge visionOS app and upload it to TestFlight for INTERNAL testers, with an
# App Store Connect API key. Modelled on hinge-pop's ios/scripts/testflight.sh.
#
#   make testflight                   tests, signing, archive, export, upload, wait, What to Test, internal group
#   SKIP_TESTS=1 make testflight      skip `make test` + `make whats-new-test` (don't, unless they just ran)
#   VALIDATE=1 make testflight        archive + export an .ipa and run App Store validation, without uploading
#
# Needs apple/.env.testflight (gitignored): TEAM_ID, ASC_KEY_ID, ASC_ISSUER_ID, ASC_KEY_PATH. The same team and
# key as the other apps; altool also wants the key at ~/.appstoreconnect/private_keys/AuthKey_<id>.p8.
# Build numbers are UTC timestamps (YYYYMMDDHHMM), so they only ever go up and never need a commit.
# Internal only: no external group, no Beta App Review, no App Review submission.
set -e
cd "$(dirname "$0")/.."   # apple/
[ -f .env.testflight ] || { echo "Missing apple/.env.testflight (see AGENTS.md, TestFlight)"; exit 1; }
. ./.env.testflight
: "${TEAM_ID:?}" "${ASC_KEY_ID:?}" "${ASC_ISSUER_ID:?}" "${ASC_KEY_PATH:?}"
case "$ASC_KEY_PATH" in "~"*) ASC_KEY_PATH="$HOME${ASC_KEY_PATH#\~}";; esac
BUILD=$(date -u +%Y%m%d%H%M)
VERSION=$(sed -nE 's/^VERSION = "([^"]+)".*/\1/p' generate_project.py | head -1)
AUTH="-allowProvisioningUpdates -authenticationKeyPath $ASC_KEY_PATH -authenticationKeyID $ASC_KEY_ID -authenticationKeyIssuerID $ASC_ISSUER_ID"

node scripts/asc.mjs notes "$VERSION" >/dev/null   # no WhatsNew.json entry for this version, no ship
node scripts/asc.mjs signing                       # our own distribution cert + App Store profile: App Manager keys cannot cloud-sign
[ "${SKIP_TESTS:-0}" = 1 ] || (cd .. && make test && make whats-new-test)
FE_TEAM="$TEAM_ID" python3 generate_project.py >/dev/null

rm -rf build/archive
# Archive signs for development (Automatic, the project's own setting); the export below re-signs for distribution.
xcodebuild -project FantasyEdge.xcodeproj -scheme FantasyEdge -configuration Release -destination "generic/platform=visionOS" \
  -archivePath build/archive/FantasyEdge.xcarchive DEVELOPMENT_TEAM="$TEAM_ID" CODE_SIGN_STYLE=Automatic \
  MARKETING_VERSION="$VERSION" CURRENT_PROJECT_VERSION="$BUILD" $AUTH -quiet archive

DEST=upload; [ "${VALIDATE:-0}" = 1 ] && DEST=export
cat > build/archive/export.plist <<PLIST
<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>method</key><string>app-store-connect</string><key>teamID</key><string>$TEAM_ID</string>
<key>destination</key><string>$DEST</string><key>signingStyle</key><string>manual</string>
<key>signingCertificate</key><string>Apple Distribution</string>
<key>provisioningProfiles</key><dict><key>com.mutaaf.fantasyedge</key><string>Fantasy Edge App Store</string></dict>
<key>manageAppVersionAndBuildNumber</key><false/>
</dict></plist>
PLIST
xcodebuild -exportArchive -archivePath build/archive/FantasyEdge.xcarchive -exportOptionsPlist build/archive/export.plist \
  -exportPath build/archive/out $AUTH

if [ "$DEST" = export ]; then
  xcrun altool --validate-app -f build/archive/out/FantasyEdge.ipa -t visionos --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID"
  echo "✓ Fantasy Edge $VERSION ($BUILD) passed App Store validation (not uploaded)."
  exit 0
fi
echo "✓ Fantasy Edge $VERSION ($BUILD) uploaded."
node scripts/asc.mjs ship "$BUILD"
