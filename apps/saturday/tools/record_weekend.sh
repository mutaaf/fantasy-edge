#!/bin/zsh
# Record a college football weekend, unattended, with the Mac kept awake.
#
#   tools/record_weekend.sh 2026-09-19            # wait for the window, record, stop
#   tools/record_weekend.sh 2026-09-19 --dry-run 3 --out /tmp/dry
#   tools/record_weekend.sh plist 2026-09-19      # print the launchd agent for this slate
#
# caffeinate -i keeps the system from idle-sleeping and -s from sleeping on AC
# power, for exactly as long as the recorder runs (-w follows its pid). The lid
# still sleeps a laptop: leave it open, or on an external display. Nothing here
# changes a system setting.
set -u
REPO=${0:A:h:h}
PY=${PYTHON:-/opt/homebrew/bin/python3}
[[ -x $PY ]] || PY=$(command -v python3)

if [[ ${1:-} == plist ]]; then
  SLATE=${2:?usage: record_weekend.sh plist YYYY-MM-DD}
  sed -e "s#__REPO__#$REPO#g" -e "s#__SLATE__#$SLATE#g" -e "s#__PYTHON__#$PY#g" \
      "$REPO/tools/launchd/com.mutaaf.saturday.record-weekend.plist.template"
  exit 0
fi

SLATE=${1:?usage: record_weekend.sh YYYY-MM-DD [record_slate.py options]}
if [[ ! $SLATE =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "usage: record_weekend.sh YYYY-MM-DD [record_slate.py options]" >&2
  exit 2
fi
shift
# The wrapper's log belongs beside the recording it wrapped, so a dry run
# writing elsewhere does not leave a line in the real weekend's folder.
OUT="$REPO/data/capture/$SLATE"
for ((i = 1; i <= $#; i++)); do
  if [[ ${@[$i]} == --out ]]; then OUT=${@[$i+1]}; [[ $OUT == /* ]] || OUT="$REPO/$OUT"; fi
done
mkdir -p "$OUT"
echo "$(date '+%Y-%m-%d %H:%M:%S %Z') record_weekend: $SLATE with $PY, pid $$" >> "$OUT/wrapper.log"

cd "$REPO"
"$PY" tools/record_slate.py --slate "$SLATE" "$@" &
REC=$!
caffeinate -i -s -w $REC &
trap 'kill -TERM $REC 2>/dev/null' TERM INT
wait $REC
CODE=$?
echo "$(date '+%Y-%m-%d %H:%M:%S %Z') record_weekend: recorder exited $CODE" >> "$OUT/wrapper.log"
exit $CODE
