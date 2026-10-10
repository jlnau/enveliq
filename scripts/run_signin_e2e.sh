#!/usr/bin/env bash
# Start a throwaway Enveliq server and run the sign-in browser check against it.
# Usage: scripts/run_signin_e2e.sh   (needs: pip install -r requirements-dev.txt,
#        npm install playwright && npx playwright install chromium)
set -euo pipefail
cd "$(dirname "$0")/.."
DATA=$(mktemp -d)
SHOTS=${ENVELIQ_E2E_SHOTS:-$(mktemp -d)}
ENVELIQ_DATA_DIR=$DATA ENVELIQ_SETUP_CODE=e2e-setup-code-12345 ENVELIQ_PORT=8799 ENVELIQ_SYNC_MINUTES=0 \
  ENVELIQ_PUBLIC_URL=http://localhost:8799 python3 run.py > "$DATA/server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null; rm -rf "$DATA"' EXIT
for _ in $(seq 1 40); do curl -sf http://localhost:8799/api/v1/health >/dev/null && break; sleep 0.25; done
ENVELIQ_E2E_SHOTS=$SHOTS node scripts/check_signin_e2e.mjs
echo "Screenshots: $SHOTS"
