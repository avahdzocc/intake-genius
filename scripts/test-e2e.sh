#!/usr/bin/env bash
# End-to-end smoke test for Intake Genius.
# Requires the FastAPI server to be running (uvicorn src.main:app).
# Usage:  ./scripts/test-e2e.sh [BASE_URL]

set -euo pipefail

BASE=${1:-http://localhost:8000}
PASS=0
FAIL=0

green()  { echo -e "\033[32m✓ $*\033[0m"; }
red()    { echo -e "\033[31m✗ $*\033[0m"; }
header() { echo -e "\n\033[1;34m── $* ──\033[0m"; }

check() {
  local label=$1
  local actual=$2
  local expected=$3
  if echo "$actual" | grep -q "$expected"; then
    green "$label"
    PASS=$((PASS+1))
  else
    red "$label (expected '$expected' in: $actual)"
    FAIL=$((FAIL+1))
  fi
}

# ── 1. Health check ─────────────────────────────────────────────────────────
header "Health"
HEALTH=$(curl -sf "$BASE/api/internal/health")
check "GET /api/internal/health returns ok" "$HEALTH" '"status":"ok"'
check "health includes firm_name"           "$HEALTH" "firm_name"

# ── 2. Intake form ──────────────────────────────────────────────────────────
header "Intake Form"
FORM=$(curl -sf "$BASE/")
check "GET / returns HTML form" "$FORM" "consultation"

# ── 3. Submit a new intake ───────────────────────────────────────────────────
header "New Intake"
INTAKE=$(curl -sf -X POST "$BASE/api/intake/new" \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "E2E Test Client",
    "client_phone": "+15550009999",
    "description": "I was in a car accident last week in Los Angeles. The other driver ran a red light.",
    "intake_source": "e2e_test"
  }')
check "POST /api/intake/new returns case_id" "$INTAKE" "case_id"
check "POST /api/intake/new status is NEW"   "$INTAKE" '"status":"NEW"'

CASE_ID=$(echo "$INTAKE" | python3 -c "import sys,json; print(json.load(sys.stdin)['case_id'])")
echo "  Case ID: $CASE_ID"

# ── 4. Fetch the case ────────────────────────────────────────────────────────
header "Fetch Case"
sleep 1   # give background agent a moment to start
CASE=$(curl -sf "$BASE/api/intake/$CASE_ID")
check "GET /api/intake/{id} returns case"      "$CASE" "\"id\":\"$CASE_ID\""
check "GET /api/intake/{id} has client_name"   "$CASE" "E2E Test Client"

# ── 5. Audit trail ───────────────────────────────────────────────────────────
header "Audit Trail"
AUDIT=$(curl -sf "$BASE/api/internal/audit/$CASE_ID")
check "GET /api/internal/audit/{id} returns entries" "$AUDIT" "entries"

# ── 6. Cases list ────────────────────────────────────────────────────────────
header "Cases List"
CASES=$(curl -sf "$BASE/api/internal/cases")
check "GET /api/internal/cases includes new case" "$CASES" "$CASE_ID"

# ── 7. Stale cases (should be empty for a brand-new case) ────────────────────
header "Stale Cases"
STALE=$(curl -sf "$BASE/api/internal/cases/stale?hours=1000")
check "GET /api/internal/cases/stale returns array" "$STALE" "\["

# ── 8. Missing docs ──────────────────────────────────────────────────────────
header "Missing Docs"
DOCS=$(curl -sf "$BASE/api/internal/cases/$CASE_ID/missing-docs")
check "GET /api/internal/cases/{id}/missing-docs returns documents key" "$DOCS" "documents"

# ── 9. Simulate Twilio inbound (unknown number — should return TwiML) ─────────
header "Twilio Inbound (no match)"
TWIML=$(curl -sf -X POST "$BASE/webhooks/twilio/inbound" \
  -d "From=%2B19990000000&To=%2B10000000000&Body=Hello&MessageSid=SMtest&NumMedia=0")
check "POST /webhooks/twilio/inbound returns TwiML" "$TWIML" "Response"

# ── 10. n8n conflict-resolved webhook ─────────────────────────────────────────
header "n8n Webhook"
N8N=$(curl -sf -X POST "$BASE/webhooks/n8n/conflict-resolved" \
  -H "Content-Type: application/json" \
  -d "{\"case_id\": \"$CASE_ID\", \"cleared\": false}")
check "POST /webhooks/n8n/conflict-resolved returns case_id" "$N8N" "$CASE_ID"

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "─────────────────────────────────"
echo "  Passed: $PASS   Failed: $FAIL"
echo "─────────────────────────────────"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
