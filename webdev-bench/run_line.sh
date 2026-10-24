#!/usr/bin/env bash
# WebDev-Bench line runner over SUBSET40.txt.
#   TAG=<env suffix> OUT=<results dir name> P=<workers> IMG=<sandbox image> bash run_line.sh
# e.g. TAG=demo OUT=demo_v9 P=5 bash run_line.sh
#
# Env: TASKS  TASKS_DIR  ACCEPT_ENV  VS_API_KEY (optional; enables the visual
#      scoring step)  VS_BASE_URL  VS_MODEL  P  IMG
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY 2>/dev/null || true
export no_proxy="localhost,127.0.0.1"
TAG="${TAG:?set TAG to the .cc_env suffix}"
OUT="${OUT:-$TAG}"; P="${P:-5}"
IMG="${IMG:-${WB_IMAGE:-vision2web-sandbox:wbench7}}"
ACCEPT_ENV="${ACCEPT_ENV:-$HERE/.cc_env.judge}"
TASKS="${TASKS:-$HERE/SUBSET40.txt}"
TASKS_DIR="${TASKS_DIR:-$HERE/tasks}"
TASKLIST=$( [ -f "$TASKS" ] && cat "$TASKS" || ls "$TASKS_DIR" )
echo "[run_line $TAG -> results/$OUT] start $(TZ=Asia/Shanghai date '+%F %T') CST workers=$P img=$IMG tasks=$(echo "$TASKLIST" | wc -w)"
echo "$TASKLIST" | sort | xargs -P "$P" -I {} python3 run_task.py "$TASKS_DIR/{}" "results/$OUT/{}" \
  --builder-env ".cc_env.$TAG" --image "$IMG" --accept-env "$ACCEPT_ENV"
echo "[run_line $TAG] builds done $(TZ=Asia/Shanghai date '+%F %T') CST reports=$(ls results/$OUT/*/report.json 2>/dev/null | wc -l)"
if [ -n "${VS_API_KEY:-}" ]; then
  python3 visual_score.py --results "results/$OUT" --tasks-dir "$TASKS_DIR" --concurrency 5
else
  echo "[run_line $TAG] VS_API_KEY not set - skipping visual_score.py"
fi
python3 aggregate_bench.py "results/$OUT" --task-list "$TASKS" --tasks-dir "$TASKS_DIR"
echo "[run_line $TAG] ALL DONE $(TZ=Asia/Shanghai date '+%F %T') CST"
