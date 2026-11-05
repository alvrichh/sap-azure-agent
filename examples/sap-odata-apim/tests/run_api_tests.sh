#!/usr/bin/env bash
# Runtime tests for the SAP OData + API Management test case.
# Needs the deployed environment (see README). Tokens come from the environment, never from files.
#
# Required:
#   GATEWAY_URL      e.g. https://apim-sapodata-dev-xyz.azure-api.net
#   TOKEN_READER     token for the API audience, user/app with role BusinessPartner.Read
# Optional:
#   AUTH_MODE        sandbox (default) | s4hana
#   API_PATH         default sap/opu/odata/sap/API_BUSINESS_PARTNER
#   TOKEN_NOROLE     token for the API audience without any role          (TC-03)
#   TOKEN_WRITER     token with role BusinessPartner.Write (s4hana only)   (TC-09)
#   TEST_BP          business partner ID to update in the write test       (TC-09)
#   RATE_LIMIT_CALLS calls per minute configured in the policy (default 60) (TC-10)
#
# Example (tokens via Azure CLI, which must be an authorized client of the API app):
#   export TOKEN_READER=$(az account get-access-token --scope api://sap-odata-apim-test/.default --query accessToken -o tsv)
set -uo pipefail

: "${GATEWAY_URL:?set GATEWAY_URL}"
: "${TOKEN_READER:?set TOKEN_READER}"
AUTH_MODE="${AUTH_MODE:-sandbox}"
API_PATH="${API_PATH:-sap/opu/odata/sap/API_BUSINESS_PARTNER}"
BASE="${GATEWAY_URL%/}/${API_PATH}"
RATE_LIMIT_CALLS="${RATE_LIMIT_CALLS:-60}"

pass=0; fail=0; skip=0
result() { # id, description, expected, actual
  if [[ "$4" == "$3" ]]; then echo "PASS $1 $2 (HTTP $4)"; pass=$((pass+1));
  else echo "FAIL $1 $2 (expected $3, got $4)"; fail=$((fail+1)); fi
}
skipped() { echo "SKIP $1 $2"; skip=$((skip+1)); }
code() { curl -s -o /tmp/sapodata_body.$$ -D /tmp/sapodata_headers.$$ -w '%{http_code}' "$@"; }

# TC-01 no token -> 401
result TC-01 "request without token is rejected" 401 "$(code "$BASE/A_BusinessPartner?\$top=1")"

# TC-02 token for another audience (Azure Resource Manager) -> 401
ARM_TOKEN=$(az account get-access-token --resource https://management.azure.com --query accessToken -o tsv 2>/dev/null || true)
if [[ -n "$ARM_TOKEN" ]]; then
  result TC-02 "token with wrong audience is rejected" 401 "$(code -H "Authorization: Bearer $ARM_TOKEN" "$BASE/A_BusinessPartner?\$top=1")"
else skipped TC-02 "no az login available for a wrong-audience token"; fi

# TC-03 token for the API but without roles -> 401
if [[ -n "${TOKEN_NOROLE:-}" ]]; then
  result TC-03 "token without roles is rejected" 401 "$(code -H "Authorization: Bearer $TOKEN_NOROLE" "$BASE/A_BusinessPartner?\$top=1")"
else skipped TC-03 "TOKEN_NOROLE not set"; fi

AUTH=(-H "Authorization: Bearer $TOKEN_READER" -H "Accept: application/json")

# TC-04 service metadata
result TC-04 "\$metadata is reachable" 200 "$(code "${AUTH[@]}" "$BASE/\$metadata")"

# TC-05 read with \$top and \$select
c=$(code "${AUTH[@]}" "$BASE/A_BusinessPartner?\$top=5&\$select=BusinessPartner,BusinessPartnerFullName")
result TC-05 "read 5 business partners" 200 "$c"
if [[ "$c" == 200 ]]; then
  n=$(python3 -c "import json;d=json.load(open('/tmp/sapodata_body.$$'));print(len(d.get('d',{}).get('results',[])))" 2>/dev/null || echo 0)
  result TC-05b "response contains 5 entities" 5 "$n"
fi

# TC-06 paging with \$skip
result TC-06 "paging with \$top/\$skip" 200 "$(code "${AUTH[@]}" "$BASE/A_BusinessPartner?\$top=2&\$skip=2&\$select=BusinessPartner")"

# TC-07 filter
result TC-07 "filter by category" 200 "$(code "${AUTH[@]}" "$BASE/A_BusinessPartner?\$top=3&\$filter=BusinessPartnerCategory%20eq%20'1'&\$select=BusinessPartner")"

# TC-08 write with read-only role -> 403 (s4hana) / 405 (sandbox is read-only)
expected=403; [[ "$AUTH_MODE" == "sandbox" ]] && expected=405
result TC-08 "write is blocked for a reader" "$expected" \
  "$(code -X PATCH "${AUTH[@]}" -H "Content-Type: application/json" -d '{"SearchTerm1":"APIMTEST"}' "$BASE/A_BusinessPartner('0000000000')")"

# TC-09 write with writer role (s4hana only): APIM fetches the CSRF token transparently -> 204
if [[ "$AUTH_MODE" == "s4hana" && -n "${TOKEN_WRITER:-}" && -n "${TEST_BP:-}" ]]; then
  c=$(code -X PATCH -H "Authorization: Bearer $TOKEN_WRITER" -H "Accept: application/json" -H "Content-Type: application/json" \
        -H "If-Match: *" -d '{"SearchTerm1":"APIMTEST"}' "$BASE/A_BusinessPartner('$TEST_BP')")
  result TC-09 "update with writer role (CSRF handled by APIM)" 204 "$c"
else skipped TC-09 "write test needs AUTH_MODE=s4hana, TOKEN_WRITER and TEST_BP"; fi

# TC-11 no SAP session cookies or CSRF tokens leak to the client
code "${AUTH[@]}" "$BASE/A_BusinessPartner?\$top=1&\$select=BusinessPartner" >/dev/null
if grep -qiE '^(set-cookie|x-csrf-token):' /tmp/sapodata_headers.$$; then result TC-11 "no SAP cookies/CSRF headers in response" none present
else result TC-11 "no SAP cookies/CSRF headers in response" none none; fi

# TC-10 rate limit -> 429 after RATE_LIMIT_CALLS calls in a minute (runs last)
last=""
for _ in $(seq 1 $((RATE_LIMIT_CALLS + 5))); do
  last=$(code "${AUTH[@]}" "$BASE/A_BusinessPartner?\$top=1&\$select=BusinessPartner")
  [[ "$last" == 429 ]] && break
done
result TC-10 "rate limit returns 429" 429 "$last"

rm -f /tmp/sapodata_body.$$ /tmp/sapodata_headers.$$
echo "Passed: $pass  Failed: $fail  Skipped: $skip"
[[ $fail -eq 0 ]]
