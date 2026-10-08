#!/usr/bin/env bash
#
# Puts the shop back to its starting state: products and stock, the three
# test customers and their orders, an empty payments ledger, no invoices.
# Works on Docker Compose (blocks 1 and 2) and on the kind cluster (3 to 5).
#
#   scripts/reset-demo.sh
#
# Each service resets its own database. This script does not touch any
# database directly: that is the "a service owns its data" rule again.

set -euo pipefail

SERVICES="catalog orders payments invoicing"

if kubectl get deployment orders -n shop >/dev/null 2>&1; then
  echo "Resetting the shop on Kubernetes (namespace shop)"
  for svc in $SERVICES; do
    kubectl exec -n shop "deploy/$svc" -c "$svc" -- python db.py --reset
  done
  exit 0
fi

found=0
for svc in $SERVICES; do
  container=$(docker ps -q --filter "label=com.docker.compose.service=$svc" | head -1)
  if [ -n "$container" ]; then
    docker exec "$container" python db.py --reset
    found=1
  fi
done

if [ "$found" -eq 0 ]; then
  echo "Neither the kind cluster nor the Compose stack is running. Nothing to reset."
  exit 1
fi
