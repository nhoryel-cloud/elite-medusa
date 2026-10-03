#!/usr/bin/env bash
# One-off production setup for the Medusa backend (run from any machine that
# can reach the prod admin API).
#
# Usage:
#   MEDUSA_URL=https://ydqvdaypuucvw3htjiks52ot.198.211.99.38.sslip.io \
#   MEDUSA_ADMIN_EMAIL=john@widsix.com \
#   MEDUSA_ADMIN_PASSWORD=<password> \
#   bash scripts/prod-setup.sh
#
# Does:
#   1. Log in as admin
#   2. Store -> USD only (delete EUR)
#   3. Create US region (countries: us), delete seed regions (gb/de/dk)
#   4. Delete ALL demo products + categories (payload import recreates them)
#   5. Create publishable API key linked to the default sales channel
set -euo pipefail

MEDUSA_URL="${MEDUSA_URL:-http://localhost:9000}"
EMAIL="${MEDUSA_ADMIN_EMAIL:-john@widsix.com}"
PASSWORD="${MEDUSA_ADMIN_PASSWORD:?set MEDUSA_ADMIN_PASSWORD}"

req() { # method path [body]
  local method="$1" path="$2" body="${3:-}"
  curl -sS -f -X "$method" "$MEDUSA_URL$path" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    ${body:+--data "$body"}
}

echo "== login"
TOKEN=$(curl -sS -f -X POST "$MEDUSA_URL/auth/user/emailpass" \
  -H "Content-Type: application/json" \
  --data "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
echo "token ok"

echo "== store -> USD"
STORE_ID=$(req GET /admin/stores | python3 -c "import sys,json;print(json.load(sys.stdin)['stores'][0]['id'])")
req POST "/admin/stores/$STORE_ID" "{\"supported_currencies\":[{\"currency_code\":\"usd\",\"is_default\":true}]}"

echo "== regions"
for reg in $(req GET /admin/regions?limit=50 | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(' '.join(r['id'] for r in d.get('regions',[])))"); do
  country=$(req GET "/admin/regions/$reg" | python3 -c "import sys,json;print(','.join(c['iso_2'] for c in json.load(sys.stdin)['region']['countries'] or []))")
  if [ "$country" = "us" ]; then
    echo "keep us region $reg"
  else
    echo "delete region $reg ($country)"
    req DELETE "/admin/regions/$reg"
  fi
done

echo "== create US region"
US_REGION=$(req POST /admin/regions "{\"name\":\"United States\",\"currency_code\":\"usd\",\"countries\":[\"us\"]}" | python3 -c "import sys,json;print(json.load(sys.stdin)['region']['id'])")
echo "US_REGION=$US_REGION"

echo "== delete demo products"
for pid in $(req GET /admin/products?limit=100 | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(' '.join(p['id'] for p in d.get('products',[])))"); do
  echo "delete product $pid"
  req DELETE "/admin/products/$pid"
done

echo "== delete categories"
for cid in $(req GET /admin/product-categories?limit=100 | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(' '.join(c['id'] for c in d.get('product_categories',[])))"); do
  echo "delete category $cid"
  req DELETE "/admin/product-categories/$cid"
done

echo "== sales channels"
SC_ID=$(req GET /admin/sales-channels | python3 -c "
import sys,json
d=json.load(sys.stdin)
sc=d.get('sales_channels',[])
print(sc[0]['id'] if sc else '')")
echo "SC_ID=$SC_ID"

echo "== publishable api key"
PK=$(req POST /admin/api-keys "{\"title\":\"storefront\",\"type\":\"publishable\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['api_key']['token'])")
PK_ID=$(req GET "/admin/api-keys?type=publishable" | python3 -c "
import sys,json
print([k['id'] for k in json.load(sys.stdin)['api_keys'] if k['token']=='$PK'][0])")
req POST "/admin/api-keys/$PK_ID/sales-channels" "{\"add\":[\"$SC_ID\"]}"
echo "PUBLISHABLE_KEY=$PK"

echo
echo "DONE. Record for payload envs:"
echo "NEXT_PUBLIC_MEDUSA_REGION_ID=$US_REGION"
echo "NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY=$PK"
