#!/usr/bin/env bash
# Screenshot the web client with headless Chrome, software WebGL.
#   tools/shoot.sh OUT.png WIDTHxHEIGHT "QUERY" [BASE]
# e.g. tools/shoot.sh shots/phone.png 390x844 "event=401772810&at=1929&mode=stadium&reduce=1"
set -euo pipefail
out="$1"; size="$2"; query="$3"; base="${4:-http://127.0.0.1:5193/}"
chrome="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
w="${size%x*}"; h="${size#*x}"
exec "$chrome" --headless=new --use-angle=swiftshader --enable-unsafe-swiftshader \
  --hide-scrollbars --force-device-scale-factor=1 --window-size="$w,$h" \
  --virtual-time-budget="${BUDGET:-9000}" --screenshot="$out" "${base}?${query}" 2>/dev/null
