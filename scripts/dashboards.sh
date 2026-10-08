#!/usr/bin/env bash
#
# Opens the monitoring tools and the two internal pages on fixed ports.
#
#   scripts/dashboards.sh
#
#   3000   Grafana         dashboards, "Retro Game Shop" in the "shop" folder
#   20001  Kiali           service graph, mTLS locks
#   9090   Prometheus      raw metrics, Alerts page
#   8003   payments        /api/payments/ledger
#   8004   invoicing       /api/invoicing/invoices
#
# These are `kubectl port-forward`s running in the background. Each one is
# restarted automatically if its pod is replaced (for example by a rollout
# restart). Run the script again any time, it replaces the old ones.
# Stop them all: pkill -f "kubectl port-forward"

pkill -f "kubectl port-forward" 2>/dev/null || true
sleep 1

forward() {  # namespace, service, local port, service port
  ( while true; do
      kubectl port-forward -n "$1" "svc/$2" "$3:$4" >/dev/null 2>&1
      sleep 2
    done ) &
}

forward istio-system grafana 3000 3000
forward istio-system kiali 20001 20001
forward istio-system prometheus 9090 9090
forward shop payments 8003 8000
forward shop invoicing 8004 8000

sleep 3
echo "Grafana     http://localhost:3000   (folder shop, dashboard Retro Game Shop)"
echo "Kiali       http://localhost:20001/kiali  (Traffic Graph, namespace shop)"
echo "Prometheus  http://localhost:9090   (Alerts)"
echo "Ledger      http://localhost:8003/api/payments/ledger"
echo "Invoices    http://localhost:8004/api/invoicing/invoices"
echo "In the Codespace: PORTS tab, open the matching port."
