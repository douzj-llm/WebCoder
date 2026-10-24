#!/bin/bash
# v9 gated-injection run for a paired base / RL comparison.
# Concurrency is set per replica count, not per line: equal worker counts would
# starve the line with fewer engine replicas and depress its score for infra reasons.
#
# Env: JUDGE_URL (required)  WB_IMAGE  TASKS  TASKS_DIR  ACCEPT_ENV
#      WPR (workers per replica)  BASE_TAG / RL_TAG  BASE_REPLICAS / RL29_REPLICAS
#      LOGS_DIR (default: logs)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY 2>/dev/null || true
export no_proxy="*" NO_PROXY="*"
JUDGE_URL=${JUDGE_URL:?set JUDGE_URL to your OpenAI-compatible judge endpoint, e.g. https://judge.example/v1}
IMG=${IMG:-${WB_IMAGE:-vision2web-sandbox:wbench7}}
TASKS=${TASKS:-$HERE/SUBSET40.txt}
TASKS_DIR=${TASKS_DIR:-$HERE/tasks}
ACCEPT_ENV=${ACCEPT_ENV:-$HERE/.cc_env.judge}
WPR=${WPR:-3}
BASE_TAG=${BASE_TAG:-base}
RL_TAG=${RL_TAG:-rl}
LOGS_DIR=${LOGS_DIR:-$HERE/logs}
mkdir -p "$LOGS_DIR"
run_line () {  # $1=env tag  $2=out dir  $3=replicas
  local tag=$1 out=$2 p=$(( $3 * WPR ))
  echo "[v9] $tag -> results/$out  workers=$p  judge=$JUDGE_URL  img=$IMG"
  cat "$TASKS" | xargs -P $p -I {} python3 run_task_v9.py "$TASKS_DIR/{}" "results/${out}/{}" \
    --builder-env ".cc_env.$tag" --judge-url "$JUDGE_URL" --image "$IMG" \
    --accept-env "$ACCEPT_ENV" >> "$LOGS_DIR/v9_${tag}.log" 2>&1
}
run_line "$BASE_TAG" "${BASE_OUT:-qwen27b_base_v9}" ${BASE_REPLICAS:-4} &
run_line "$RL_TAG"   "${RL_OUT:-qwen27b_rl29_v9}" ${RL29_REPLICAS:-3} &
wait
echo "[v9] ALL DONE $(TZ=Asia/Shanghai date '+%F %T') CST"
