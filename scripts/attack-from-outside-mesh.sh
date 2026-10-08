#!/usr/bin/env bash
#
# Block 4: an attacker pod in the namespace shop, WITHOUT a sidecar.
#
#   scripts/attack-from-outside-mesh.sh
#
# Same request as attack-from-catalog.sh, but from a pod that is not part of
# the mesh: no sidecar, so no certificate, so no identity. Before STRICT
# mTLS it gets through. After STRICT it is refused at the door.

set -euo pipefail

if ! kubectl get pod outsider -n shop >/dev/null 2>&1; then
  echo "==> Starting the pod \"outsider\" (sidecar injection disabled for it)"
  kubectl run outsider -n shop --image=retro-shop/catalog:v1 --image-pull-policy=Never \
    --labels=sidecar.istio.io/inject=false --env=DATABASE_URL=unused \
    --command -- sleep 86400 >/dev/null
  kubectl wait pod/outsider -n shop --for=condition=Ready --timeout=60s >/dev/null
fi
kubectl get pod outsider -n shop

echo
echo "==> From the outsider pod: POST http://payments:8000/api/payments/refunds"
kubectl exec -n shop outsider -- python -c '
import json, urllib.request, urllib.error
body = json.dumps({"order_id": 4, "amount_huf": 16970}).encode()
request = urllib.request.Request("http://payments:8000/api/payments/refunds", data=body,
                                 headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(request, timeout=5) as reply:
        print(reply.status, reply.read().decode())
except urllib.error.HTTPError as error:
    print(error.code, error.read().decode())
except Exception as error:
    print("connection failed:", error)
'
