#!/usr/bin/env bash
#
# End of block 3, runs over lunch: installs the service mesh and monitoring.
#
#   scripts/mesh-up.sh
#
# 1. Istio, sidecar mode, minimal profile, lowered requests (mesh/istio-install.yaml)
# 2. Prometheus, Grafana and Kiali (mesh/addons/), with the course alert rules
# 3. The "Retro Game Shop" Grafana dashboard (mesh/monitoring/)
#
# It does NOT turn on sidecar injection for "shop". That is block 4, step 2,
# done by hand so you see it happen.

set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Installing Istio"
istioctl install -y -f mesh/istio-install.yaml

echo "==> Installing Prometheus, Grafana and Kiali"
kubectl create configmap shop-grafana-dashboard -n istio-system \
  --from-file=retro-game-shop.json=mesh/monitoring/retro-game-shop.json \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f mesh/addons/

echo "==> Waiting for them to start"
for name in istiod prometheus grafana kiali; do
  kubectl rollout status "deployment/$name" -n istio-system --timeout=300s
done

echo
kubectl get pods -n istio-system
echo
echo "Done. Sidecar injection for the namespace shop is still OFF:"
kubectl get pods -n shop
