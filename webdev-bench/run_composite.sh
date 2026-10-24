#!/usr/bin/env bash
# Focused paired run on the composite subset (SUBSET40.txt).
#   TAG=<env suffix> OUT=<results dir> P=<build workers> bash run_composite.sh
#
# Phase A replays acceptance on tasks that already have build.tar but no report
# (no rebuild); Phase B builds and accepts the rest.
# Env: WB_IMAGE  TASKS  TASKS_DIR  ACCEPT_ENV  RP (reaccept workers)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY 2>/dev/null || true
export no_proxy="localhost,127.0.0.1"
TAG="${TAG:?set TAG to the .cc_env suffix, e.g. .cc_env.rl29 -> TAG=rl29}"
OUT="${OUT:?set OUT to a results subdirectory name}"
P="${P:-15}"; RP="${RP:-8}"
IMG="${IMG:-${WB_IMAGE:-vision2web-sandbox:wbench7}}"
ACCEPT_ENV="${ACCEPT_ENV:-$HERE/.cc_env.judge}"
TASKS="${TASKS:-$HERE/SUBSET40.txt}"
TASKS_DIR="${TASKS_DIR:-$HERE/tasks}"
N=$(grep -c . "$TASKS")
echo "[composite $TAG] start $(TZ=Asia/Shanghai date '+%F %T') CST build_workers=$P reaccept_workers=$RP"
# Phase A: replay acceptance on composites already built (no rebuild)
for t in $(cat "$TASKS"); do
  [ -f "results/$OUT/$t/build.tar" ] && [ ! -f "results/$OUT/$t/report.json" ] && echo "$t"
done | xargs -r -P "$RP" -I {} python3 reaccept.py {} --src "results/$OUT" --out "results/$OUT" \
  --prompt v1 --image "$IMG" --accept-env "$ACCEPT_ENV" --tasks-dir "$TASKS_DIR"
echo "[composite $TAG] phase A done: $(for t in $(cat "$TASKS"); do [ -f results/$OUT/$t/report.json ] && echo x; done | wc -l)/$N"
# Phase B: build+accept the rest
cat "$TASKS" | xargs -P "$P" -I {} python3 run_task.py "$TASKS_DIR/{}" "results/$OUT/{}" \
  --builder-env ".cc_env.$TAG" --image "$IMG" --accept-env "$ACCEPT_ENV"
echo "[composite $TAG] ALL DONE $(TZ=Asia/Shanghai date '+%F %T') CST reports=$(for t in $(cat "$TASKS"); do [ -f results/$OUT/$t/report.json ] && echo x; done | wc -l)/$N"
