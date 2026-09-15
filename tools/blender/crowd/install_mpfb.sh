#!/bin/sh
# Install MPFB (MakeHuman's Blender extension) into Blender's *user* extensions,
# pinned by version and hash. Nothing system-wide. Idempotent.
#
#   sh tools/blender/crowd/install_mpfb.sh
set -e
cd "$(dirname "$0")/../../.." || exit 1
VERSION=2.0.17
SHA=4f0a879d64a39bf646fbf5f53601ac678855da329d650617dca5737548239a87
URL="https://extensions.blender.org/download/sha256:$SHA/add-on-mpfb-v$VERSION.zip"
ZIP=.work/crowd/mpfb-$VERSION.zip
mkdir -p .work/crowd
[ -f "$ZIP" ] || curl -sL -m 300 -o "$ZIP" "$URL"
echo "$SHA  $ZIP" | shasum -a 256 -c -
blender --background --factory-startup --python-expr "
import bpy
bpy.ops.extensions.package_install_files(filepath=r'$ZIP', repo='user_default', enable_on_install=True)
bpy.ops.wm.save_userpref()
import addon_utils
print('MPFB installed:', [m for m in addon_utils.addons_fake_modules if 'mpfb' in m])
"
