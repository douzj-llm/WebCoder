#!/bin/bash
# v9 multi-model campaign: one line per "tag:out_dir" argument.
# Total concurrency is bounded by the judge endpoint; keep sum(P) modest.
#
# Env: JUDGE_URL (required)  WB_IMAGE  TASKS  TASKS_DIR  ACCEPT_ENV  P  LOGS_DIR
# Usage: JUDGE_URL=... bash run_v9_multi.sh opus48:opus48_v9_40 gpt54:gpt54_v9_40
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY 2>/dev/null || true
export no_proxy="*" NO_PROXY="*"
JUDGE_URL=${JUDGE_URL:?set JUDGE_URL to your OpenAI-compatible judge endpoint}
IMG=${IMG:-${WB_IMAGE:-vision2web-sandbox:wbench7}}
TASKS=${TASKS:-$HERE/SUBSET40.txt}
TASKS_DIR=${TASKS_DIR:-$HERE/tasks}
ACCEPT_ENV=${ACCEPT_ENV:-$HERE/.cc_env.judge}
P=${P:-6}
LOGS_DIR=${LOGS_DIR:-$HERE/logs}
mkdir -p "$LOGS_DIR"
for pair in "$@"; do
  tag=${pair%%:*}; out=${pair##*:}
  cat "$TASKS" | xargs -P $P -I {} python3 run_task_v9.py "$TASKS_DIR/{}" "results/${out}/{}" \
    --builder-env ".cc_env.$tag" --judge-url "$JUDGE_URL" --image "$IMG" \
    --accept-env "$ACCEPT_ENV" >> "$LOGS_DIR/v9m_${tag}.log" 2>&1 &
done
wait
echo "[v9-multi] DONE $(TZ=Asia/Shanghai date '+%F %T') CST"
