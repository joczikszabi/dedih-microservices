#!/usr/bin/env bash
#
# Runs once, after the container is built. Prints the tool versions, so a
# broken setup is visible in the creation log rather than in block 3.

set -euo pipefail

echo "==> tools"
docker --version
docker compose version
kubectl version --client -o yaml | grep gitVersion | head -1
kind --version
istioctl version --remote=false
jq --version
