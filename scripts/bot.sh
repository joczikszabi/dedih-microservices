#!/usr/bin/env bash
#
# The bot. Logs in as bob and tries to buy the limited console, as fast as it
# can, over and over.
#
#   scripts/bot.sh          30 attempts (block 1 and block 2)
#   scripts/bot.sh 3000     a longer run, for the graphs in block 5
#
# It prints the HTTP status of every attempt:
#   200  order placed        409  sold out
#   429  refused by the gateway rate limit

set -uo pipefail

SHOP_URL="${SHOP_URL:-http://localhost:8080}"
ATTEMPTS="${1:-30}"
ORDER='{"items":[{"product_id":1,"quantity":1,"unit_price":49990}]}'

TOKEN=$(curl -s "$SHOP_URL/api/orders/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"bob@example.com","password":"bob123"}' \
  | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')

if [ -z "$TOKEN" ]; then
  echo "Login failed. Is the shop running on $SHOP_URL?"
  exit 1
fi

echo "Bot logged in as bob@example.com, trying to buy the limited console $ATTEMPTS times."
placed=0; soldout=0; limited=0; other=0
for i in $(seq 1 "$ATTEMPTS"); do
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$SHOP_URL/api/orders/" \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d "$ORDER")
  case "$code" in
    200) placed=$((placed + 1)) ;;
    409) soldout=$((soldout + 1)) ;;
    429) limited=$((limited + 1)) ;;
    *)   other=$((other + 1)) ;;
  esac
  printf '%s ' "$code"
  if [ $((i % 15)) -eq 0 ]; then echo; fi
done
echo
echo "Orders placed: $placed   sold out (409): $soldout   rate limited (429): $limited   other: $other"
