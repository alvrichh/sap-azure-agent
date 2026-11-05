# Test case: Logic Apps Standard calling SAP through RFC

A complete, reproducible test of the agent's RFC path: a **Logic Apps Standard** workflow exposes an HTTP API that calls the SAP function module **`BAPI_MATERIAL_AVAILABILITY`** through the **SAP built-in connector** (no on-premises data gateway), plus a connectivity probe with **`STFC_CONNECTION`**. Credentials stay in **Key Vault**; the app reaches SAP over **VNet integration**.

Skills involved: `sap-api-integration`, `azure-auth-entra`, `azure-bicep-iac`.

> **Status:** 11 unit tests and 14 static checks pass (`tests/validate_example.py`); the validator caught all six faults deliberately injected into a copy, and a unit test (UT-11) was added after it found a real quoting bug in the workflow expressions. The runtime tests (TC-01…TC-10) have **not yet run against a real SAP system**. Four details of the built-in connector's JSON aren't published in the docs and must be confirmed in the designer (section 4).

## 1. Scenario

| Item | Value |
| --- | --- |
| SAP | S/4HANA or ECC, SID `S4P`, client `100`, technical RFC user `RFC_LOGICAPP` |
| Function modules | `STFC_CONNECTION` (connectivity), `BAPI_MATERIAL_AVAILABILITY` (available quantity of a material in a plant) |
| Azure | Logic App Standard (WS1, 64-bit) with VNet integration, Key Vault, storage account |
| API | `POST /api/wf-material-availability/...` `{"material":"MAT-1001","plant":"1000","unit":"ST"}` → `200 {"availableQuantity":125.0,...}`, `422` if SAP returns an error, `502` if the call fails |

```
Client ──HTTPS──► Logic App Standard (VNet-integrated, 64-bit, SAP NCo 3.1 in lib/builtinOperationSdks/net472)
                    1. Request trigger: strict JSON schema (400 if invalid)
                    2. Build RFC XML from a JSON object with xml()  → values escaped
                    3. [RFC] Call function in SAP: BAPI_MATERIAL_AVAILABILITY (retry ×2)
                    4. XPath on the response: AV_QTY_PLT, ENDLEADTME, RETURN-TYPE/MESSAGE
                    5. RETURN-TYPE E/A → 422, otherwise 200;  Catch (Failed/TimedOut) → 502 + run ID
                  ──RFC (dispatcher/gateway ports)──► SAP S4P/100 (user RFC_LOGICAPP, password from Key Vault)
```

## 2. Files

| File | Purpose |
| --- | --- |
| `../../templates/bicep/logicapp-standard-sap.bicep` | Reusable template: WS1 plan, 64-bit Logic App with VNet integration, storage, SAP app settings, Key Vault reference for the password, Key Vault role. |
| `bicep/logicapp.dev.bicepparam` | Parameters for the test. |
| `logicapp/host.json` | Extension bundle and SAP action timeout (2 minutes). |
| `logicapp/connections.json` | SAP built-in connection; every value from app settings. |
| `logicapp/wf-material-availability/workflow.json` | The API workflow. |
| `logicapp/wf-sap-ping/workflow.json` | `GET` connectivity probe (`STFC_CONNECTION`). |
| `logicapp/lib/builtinOperationSdks/net472/` | Where the SAP NCo DLLs go (not in Git: licensed by SAP). |
| `tests/fixtures/` | Sample SAP responses: success, error, warning, `STFC_CONNECTION`. |
| `tests/test_units.py` | 11 offline tests that read the workflow JSON and evaluate it. |
| `tests/validate_example.py` | 14 static checks + unit tests. |

## 3. Offline checks

```bash
pip install lxml jsonschema
```

```bash
python3 examples/logicapps-sap-rfc/tests/validate_example.py
```

| ID | Static check |
| --- | --- |
| ST-01 | JSON parses |
| ST-02 / ST-03 | SAP connection values only from app settings, and those settings exist in Bicep |
| ST-04 | SAP password is a Key Vault reference; the app identity has *Key Vault Secrets User* |
| ST-05 | `functionapp,workflowapp`, 64-bit, VNet integration with route-all, HTTPS only, FTP off, `APP_KIND`, worker runtime |
| ST-06 | SAP actions use a defined connection and an operation ID published in the connector reference |
| ST-07 | Trigger schema strict (required fields, patterns, no extra properties) with schema validation on |
| ST-08 / ST-09 | Try/Catch returns 502 on failure or timeout; 200, 422 and 502 responses exist |
| ST-10 | Retry policy on the SAP call; action timeout ≤ 230 s (synchronous HTTP response window) |
| ST-11 | SAP NCo DLLs not committed and ignored by Git |
| ST-12 / ST-13 | Parameter file → template; no secrets anywhere |
| ST-14 | Unit tests pass |

| ID | Unit test (evaluates the real `workflow.json`) |
| --- | --- |
| UT-01 / UT-02 | Trigger schema accepts a valid body; rejects missing/extra fields, lowercase, markup, wrong plant length, material > 18 chars |
| UT-03…UT-05 | RFC request XML shape (namespace, fields, empty tables so SAP returns them); values XML-escaped; call uses the composed request |
| UT-06…UT-09 | Workflow XPaths on SAP responses: success → 200 with quantity; `E` → 422 with SAP message; `W` → 200; `A` → 422 |
| UT-10 | Ping workflow XPaths on the `STFC_CONNECTION` response |
| UT-11 | Every expression's string literals are well formed (catches `'` inside `'…'`, which breaks Workflow Definition Language) |

## 4. To confirm in the designer (not covered by published docs)

The connector reference documents the operations (`callRfc`, `readTable`, …) and their parameters, but not every JSON key the designer writes. Create one SAP connection and one **[RFC] Call function in SAP** action in the portal designer, open **Code view**, and compare:

| ID | What | Where |
| --- | --- | --- |
| UV-01 | `serviceProviderId` = `/serviceProviders/sap` | `connections.json`, both workflows |
| UV-02 | Connection parameter keys (`client`, `authType`, `userName`, `password`, `logonType`, `appServerHost`, `systemNumber`, `language`) | `connections.json` |
| UV-03 | RFC payload key `body`; the action output is the RFC response XML | workflows |
| UV-04 | `operationOptions: "EnableSchemaValidation"` = *Settings → Schema Validation: On* | `wf-material-availability` trigger |

Fix any difference in the repository and rerun the validator; record it in the results log.

## 5. Runbook

### Phase 0 — SAP (Basis team)

1. Technical user `RFC_LOGICAPP` (type *System*), authorized only for `S_RFC` on `STFC_CONNECTION` and `BAPI_MATERIAL_AVAILABILITY` (function group as required) and the business authorizations the BAPI checks for the test plant.
2. Test both function modules in **SE37** with the test material, plant and unit (internal unit format, e.g. `ST`); note the expected quantity.
3. Network: allow the integration subnet to the application server's dispatcher (`32<NN>`) and gateway (`33<NN>`) ports (`NN` = system number).

### Phase 1 — Azure

1. VNet with a subnet delegated to `Microsoft.Web/serverFarms` that can reach SAP (peering, VPN or ExpressRoute).
2. Store the SAP password in Key Vault (prompted, not saved to history):

```bash
az keyvault secret set --vault-name <key-vault-name> --name sap-rfc-password --value "$(read -rsp 'SAP password: ' p; echo "$p")"
```

3. Deploy:

```bash
az deployment group what-if --resource-group rg-saprfc-dev --parameters examples/logicapps-sap-rfc/bicep/logicapp.dev.bicepparam
```

```bash
az deployment group create --resource-group rg-saprfc-dev --parameters examples/logicapps-sap-rfc/bicep/logicapp.dev.bicepparam
```

### Phase 2 — SAP libraries and workflows

1. Download *SAP Connector for Microsoft .NET 3.1 (compiled with .NET Framework 4.6.2), x64* from the SAP Support Portal; upload `rscp4n.dll`, `sapnco.dll`, `sapnco_utils.dll` as **Client/SDK Assembly (.NET Framework)** (portal → logic app → *Assemblies*), or place them in `logicapp/lib/builtinOperationSdks/net472/` locally (ignored by Git).
2. Complete the checks in section 4.
3. Deploy the project (VS Code *Deploy to logic app*, or zip deploy of the `logicapp/` folder from CI).
4. Copy each workflow's trigger URL from the portal. It contains a SAS signature: treat it as a secret and don't commit it.

### Phase 3 — Run the tests

```bash
export PING_URL='<wf-sap-ping trigger URL>'
```

```bash
export AVAIL_URL='<wf-material-availability trigger URL>'
```

```bash
curl -s "$PING_URL"
```

```bash
curl -s -X POST "$AVAIL_URL" -H "Content-Type: application/json" -d '{"material":"<material-number>","plant":"<plant>","unit":"ST"}'
```

## 6. Runtime test cases

| ID | Test | Expected result |
| --- | --- | --- |
| TC-01 | `GET` ping | 200; `echo` = `logicapp-ping`; `sapInfo` shows SID `S4P` and user `100/RFC_LOGICAPP` |
| TC-02 | Availability for the test material | 200; `availableQuantity` equals SE37 result |
| TC-03 | Material that doesn't exist in the plant | 422 with SAP's message |
| TC-04 | Body with an extra field / missing `unit` / lowercase material | 400 (schema validation) — no SAP call in run history |
| TC-05 | Wrong password in Key Vault (temporarily) | 502 with run ID; run history shows the logon error; restore the secret |
| TC-06 | Block the SAP ports in the NSG | 502 after retries (~2 × 10 s); `partner not reached` in run history; restore |
| TC-07 | Remove the DLLs from *Assemblies* | Action fails with an NCo load error; restore |
| TC-08 | 20 parallel requests | All 200; no SAP session errors (stateless calls) |
| TC-09 | SAP security audit log (SM20) | Calls appear as `RFC_LOGICAPP` from the integration subnet only |
| TC-10 | Key Vault reference status (portal → Environment variables) | `SAP_PASSWORD` resolved by Key Vault reference (green), no plain value |

**Acceptance:** ST-01…ST-14 pass in strict mode, UV-01…UV-04 confirmed, TC-01…TC-10 pass.

## 7. Production notes

- Don't expose the SAS trigger URL directly: put **API Management** in front with Entra ID (see `examples/sap-odata-apim`), or enable App Service authentication on the logic app.
- Prefer **SNC** (X.509) over basic authentication for the RFC connection; the built-in connector supports it with the CommonCryptoLib files.
- Use **message server / logon groups** for load balancing in production; open the message server port too.
- For BAPIs that change data, use stateful sessions and commit explicitly (the connector's *Auto commit* doesn't commit when the BAPI returns warnings).
- Hide sensitive inputs/outputs from run history (*Secure inputs/outputs*) when payloads contain personal data.

## 8. Cleanup

```bash
az group delete --name rg-saprfc-dev
```

(Only if nothing else lives in the resource group — irreversible.) Lock or delete the `RFC_LOGICAPP` user in SAP after the test.

## 9. Results log

| ID | Date | Result | Notes |
| --- | --- | --- | --- |
| UT-01…UT-11 | 2026-11-05 | Pass | Offline; UT-11 added after it caught a real quoting bug in the workflow XPaths |
| ST-01…ST-14 | 2026-11-05 | Pass | Static checks, design mode; 6/6 injected faults detected |
| UV-01…UV-04 | | To confirm | Compare with designer code view |
| TC-01…TC-10 | | Not run | Requires SAP system, VNet path and Azure subscription |
