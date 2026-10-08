#!/usr/bin/env bash
#
# Normal customers: a gentle, steady background of browsing, so the graphs in
# block 5 have something to compare the bot against. About one request per
# second. Stop it with Ctrl+C.
#
#   scripts/traffic.sh

set -uo pipefail

SHOP_URL="${SHOP_URL:-http://localhost:8080}"

TOKEN=$(curl -s "$SHOP_URL/api/orders/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.com","password":"alice123"}' \
  | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')

echo "Normal traffic against $SHOP_URL, about one request per second. Ctrl+C to stop."
n=0
while true; do
  n=$((n + 1))
  curl -s -o /dev/null "$SHOP_URL/"
  sleep 0.3
  curl -s -o /dev/null "$SHOP_URL/api/catalog/products"
  sleep 0.3
  curl -s -o /dev/null "$SHOP_URL/api/catalog/products/$(( (n % 8) + 1 ))"
  sleep 0.3
  curl -s -o /dev/null -H "Authorization: Bearer $TOKEN" "$SHOP_URL/api/orders/"
  # Every 30 rounds (about 40 seconds) Alice buys a memory card.
  if [ $((n % 30)) -eq 0 ]; then
    code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$SHOP_URL/api/orders/" \
      -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
      -d '{"items":[{"product_id":8,"quantity":1,"unit_price":2990}]}')
    echo "$(date +%H:%M:%S) normal checkout: $code"
  fi
  sleep 0.3
done
