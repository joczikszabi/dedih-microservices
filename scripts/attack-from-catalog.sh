#!/usr/bin/env bash
#
# Block 4: pretend the catalog service has been hacked.
#
#   scripts/attack-from-catalog.sh
#
# From inside a catalog pod, ask payments to refund Bob's order 3. catalog
# has no business calling payments at all, but nothing in the network stops
# it. Then show the last lines of the payments ledger, with "requested by".

set -euo pipefail

echo "==> From inside the catalog pod: POST http://payments:8000/api/payments/refunds"
kubectl exec -n shop deploy/catalog -c catalog -- python -c '
import json, urllib.request, urllib.error
body = json.dumps({"order_id": 3, "amount_huf": 39990}).encode()
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

echo
echo "==> The payments ledger, newest first"
kubectl exec -n shop deploy/payments -c payments -- python -c '
import json, urllib.request
for e in json.load(urllib.request.urlopen("http://localhost:8000/api/payments/entries?limit=3")):
    print("#%-3s %-7s order %-3s %7s HUF   requested by: %s"
          % (e["id"], e["kind"], e["order_id"], e["amount_huf"], e["requested_by"]))
'
