# Test case: SAP OData behind Azure API Management (end to end)

A complete, reproducible test of the agent's API path: the standard SAP API **`API_BUSINESS_PARTNER`** (OData v2) exposed through **Azure API Management**, protected with **Microsoft Entra ID** (token validation + app roles), with SAP credentials only in **Key Vault**, per-caller rate limiting, and transparent **X-CSRF-Token** handling for writes.

Skills involved: `sap-api-integration`, `azure-auth-entra`, `azure-bicep-iac`.

Two options:

| Option | Backend | What it tests | Needs |
| --- | --- | --- | --- |
| **A — sandbox** (`authMode = sandbox`) | SAP Business Accelerator Hub sandbox (`sandbox.api.sap.com`), read-only | Entra ID auth, roles, reads, paging, filtering, rate limiting, header hygiene | Free api.sap.com account (API key) — **no own SAP system** |
| **B — own S/4HANA** (`authMode = s4hana`) | Your S/4HANA dev system through SAP Gateway | Everything in A plus writes with CSRF and the SAP technical user | S/4HANA dev, `API_BUSINESS_PARTNER` active, private network path from APIM |

> **Status:** static checks pass (`tests/validate_example.py`, 27 checks) and the runtime test script was exercised against a local mock of the gateway (10 pass, 2 skipped as expected). The runtime tests have **not yet run against a real APIM instance and SAP backend**; record the results at the end when you run them.

## 1. Architecture

```
Client (user or app) ──Entra ID token (aud = api://sap-odata-apim-test, role BusinessPartner.Read/Write)──►
  Azure API Management
    1. validate-azure-ad-token (audience + roles)
    2. rate-limit-by-key (per caller oid)
    3. writes require BusinessPartner.Write (403 otherwise)  [sandbox: writes → 405]
    4. drop client Authorization header
    5. SAP auth: technical user from Key Vault (B) | API key from Key Vault (A)
    6. writes: HEAD with X-CSRF-Token: Fetch → forward token + session cookies (B)
  ──► SAP OData service API_BUSINESS_PARTNER (TLS validated)
  ◄── response without SAP Set-Cookie / X-CSRF-Token headers
```

## 2. Files

| File | Purpose |
| --- | --- |
| `config/settings.example.json` | Non-secret values for the test. Copy to `settings.json` (ignored by Git). |
| `../../templates/bicep/apim-sap-odata.bicep` | Reusable template: APIM, Key Vault access for its identity, named values, SAP backend with TLS validation. |
| `bicep/apim.sandbox.dev.bicepparam`, `bicep/apim.s4hana.dev.bicepparam` | Parameters for options A and B. |
| `bicep/api-policy.bicep` | Applies the policy to the imported API. |
| `apim/policy-sandbox.xml`, `apim/policy-s4hana.xml` | API policies for options A and B. |
| `tests/validate_example.py` | Static checks (no Azure/SAP needed). |
| `tests/run_api_tests.sh` | Runtime tests against the deployed gateway (TC-01…TC-11). |

## 3. Static checks

```bash
python3 examples/sap-odata-apim/tests/validate_example.py
```

| ID | Check |
| --- | --- |
| ST-01 | Both policies are valid XML |
| ST-02 / ST-03 | Entra ID token validation runs first; audience and roles enforced |
| ST-04 | Rate limit per caller |
| ST-05 | Client bearer token never forwarded to SAP |
| ST-06 / ST-07 | Backend and every named value used by the policy exist in the Bicep template for that mode |
| ST-08 / ST-13 | SAP credentials only via named values; secrets are Key Vault references |
| ST-09 | SAP `Set-Cookie` removed from responses |
| ST-10 / ST-11 | (B) CSRF fetch for writes; Write role checked before routing to SAP |
| ST-12 | (A) Sandbox rejects writes with 405 |
| ST-14 | Backend validates the SAP TLS certificate |
| ST-15 / ST-16 | Parameter files and policy deployment reference existing files |
| ST-17 | Runtime script is valid Bash and covers TC-01…TC-11 |
| ST-18 | JSON parses; no secrets or tokens in any file |

Before deploying, fill in every placeholder and run with `--strict --verbose`.

## 4. Runbook

### Phase 0 — prerequisites

- **Option A:** sign in at api.sap.com, open `API_BUSINESS_PARTNER` (SAP S/4HANA Cloud), copy your **API key**, and download the API specification as **OpenAPI JSON** (`api.json`).
- **Option B (SAP Basis):** activate the service in `/IWFND/MAINT_SERVICE`; create a technical user with authorizations for business partner display/change only; test with `/IWFND/GW_CLIENT`; pick a **test business partner** you may modify. Network: APIM must reach the SAP Gateway privately (VNet integration/injection, VPN or peering). Get `$metadata` and convert it to OpenAPI with Microsoft's `odata-openapi-converter`.

### Phase 1 — Entra ID (`azure-auth-entra`)

1. App registration **`sap-odata-apim-test`** (the API): Application ID URI `api://sap-odata-apim-test`; app roles `BusinessPartner.Read` and `BusinessPartner.Write` (allowed member types: users/groups and applications).
2. Under *Expose an API*, add the Azure CLI as an authorized client application (`04b07795-8ddb-461a-bbee-02f9e1bf7b46`) so testers can get tokens with `az`.
3. In *Enterprise applications* → `sap-odata-apim-test` → *Users and groups*: assign `BusinessPartner.Read` to the reader test user, `BusinessPartner.Write` to the writer test user; leave one test user without roles (TC-03).

### Phase 2 — Key Vault secret

Option A:

```bash
az keyvault secret set --vault-name <key-vault-name> --name sap-sandbox-apikey --value "$(read -rsp 'SAP API key: ' k; echo "$k")"
```

Option B:

```bash
az keyvault secret set --vault-name <key-vault-name> --name sap-odata-password --value "$(read -rsp 'SAP password: ' p; echo "$p")"
```

### Phase 3 — API Management (`azure-bicep-iac`)

```bash
az group create --name rg-sapodata-dev --location westeurope
```

```bash
az deployment group what-if --resource-group rg-sapodata-dev --parameters examples/sap-odata-apim/bicep/apim.sandbox.dev.bicepparam
```

```bash
az deployment group create --resource-group rg-sapodata-dev --parameters examples/sap-odata-apim/bicep/apim.sandbox.dev.bicepparam
```

(Developer tier provisioning takes 30+ minutes. If a Key Vault named value fails on the first run, wait for the role assignment to propagate and rerun.)

### Phase 4 — import the API and apply the policy

```bash
az apim api import --resource-group rg-sapodata-dev --service-name <apim-name> --api-id sap-business-partner --path sap/opu/odata/sap/API_BUSINESS_PARTNER --specification-format OpenApiJson --specification-path api.json --subscription-required false
```

If the OpenAPI file has no `$metadata` operation, add it (TC-04):

```bash
az apim api operation create --resource-group rg-sapodata-dev --service-name <apim-name> --api-id sap-business-partner --operation-id get-metadata --display-name "Get metadata" --method GET --url-template '/$metadata'
```

```bash
az deployment group create --resource-group rg-sapodata-dev --template-file examples/sap-odata-apim/bicep/api-policy.bicep --parameters apimName=<apim-name> authMode=sandbox
```

Subscription keys are disabled for this API because callers authenticate with Entra ID; keep it that way only if every caller gets a token.

### Phase 5 — run the tests

```bash
export GATEWAY_URL=https://<apim-name>.azure-api.net
```

```bash
export TOKEN_READER=$(az account get-access-token --scope api://sap-odata-apim-test/.default --query accessToken -o tsv)
```

Sign in as the user without roles in another shell (or with `az login` again) to get `TOKEN_NOROLE`; for option B also `TOKEN_WRITER`, `TEST_BP` and `AUTH_MODE=s4hana`. Then:

```bash
bash examples/sap-odata-apim/tests/run_api_tests.sh
```

## 5. Runtime test cases

| ID | Test | Expected (A sandbox) | Expected (B S/4HANA) |
| --- | --- | --- | --- |
| TC-01 | No token | 401 | 401 |
| TC-02 | Token for another audience (ARM) | 401 | 401 |
| TC-03 | Token for the API without roles | 401 | 401 |
| TC-04 | `GET $metadata` | 200 | 200 |
| TC-05 | `GET A_BusinessPartner?$top=5&$select=…` | 200, 5 entities | 200, 5 entities (client 100 applied) |
| TC-06 | Paging `$top=2&$skip=2` | 200 | 200 |
| TC-07 | `$filter=BusinessPartnerCategory eq '1'` | 200 | 200 |
| TC-08 | `PATCH` with reader role | 405 (read-only) | 403 |
| TC-09 | `PATCH` with writer role (`If-Match: *`) | n/a | 204 — APIM fetched the CSRF token; SAP change visible in BP transaction |
| TC-10 | More than 60 calls/minute | 429 | 429 |
| TC-11 | No `Set-Cookie` / `X-CSRF-Token` in responses | none | none |

Also check manually: the SAP security audit log (SM20) / Gateway log shows calls as the technical user (B); APIM diagnostic logs show the caller's identity.

**Acceptance:** ST-01…ST-18 pass in strict mode and every applicable TC passes.

## 6. Production notes

- Replace the shared technical user with **SAP principal propagation** when users must act with their own SAP authorizations (`azure-auth-entra`, APIM policy snippet referenced in `sap-api-integration`).
- Put APIM in a VNet (internal mode or v2 VNet integration) and front it with Application Gateway / WAF if it must be public; enable **Defender for APIs**.
- Use a production tier (not Developer) with SLA.

## 7. Cost control and cleanup

- The Developer tier is billed hourly while it exists; delete it after the test.
- Remove the test role assignments and the app registration if no longer needed.
- Delete the test resource group only when nothing else lives in it (irreversible):

```bash
az group delete --name rg-sapodata-dev
```

## 8. Results log

| ID | Date | Result | Notes |
| --- | --- | --- | --- |
| ST-01…ST-18 | 2026-11-05 | Pass | Static checks, design mode (placeholders pending) |
| Script vs mock | 2026-11-05 | 10 pass, 2 skipped | Local mock of the gateway (sandbox behaviour); validates the test script, not APIM |
| TC-01…TC-11 | | Not run | Requires APIM instance and SAP backend (sandbox or own S/4HANA) |
