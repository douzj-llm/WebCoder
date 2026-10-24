#!/bin/bash
# Build the base sandbox image and tag it as the WebDev-Bench sandbox.
#
# The published image vision2web-sandbox:wbench7 was NOT built from a single
# Dockerfile: it descends from this base (:latest) through several docker-commit
# steps. See Dockerfile.wbench.md for what is reconstructible and what is not.
#
# Usage: ./build.sh [tag]        (default tag: vision2web-sandbox:wbench7)
set -euo pipefail

TAG="${1:-vision2web-sandbox:wbench7}"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "Building sandbox base image -> ${TAG} ..."
docker build -t "$TAG" -f "${SCRIPT_DIR}/Dockerfile.sandbox" "${SCRIPT_DIR}"

cat <<EOF

Built: ${TAG}

This is the base image only. If you need the extra layers that the published
wbench7 image carries (judge routing config, browser build pins, etc.), read
docker/Dockerfile.wbench.md and apply the steps marked as recoverable there.

EOF
