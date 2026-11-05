# Test case: SAP with Power Platform (Power Apps + Power Automate)

A complete, reproducible test of the agent's Power Platform path. **SAP Sales Assistant** is a canvas app for sales reps backed by two Power Automate cloud flows in one solution:

- **SAP - Check material availability**: the **SAP ERP connector** calls `BAPI_MATERIAL_AVAILABILITY` (RFC through the **on-premises data gateway**).
- **SAP - Search business partners**: the **SAP OData connector** queries `API_BUSINESS_PARTNER` through **Azure API Management** with **Microsoft Entra ID**. That API is the one from `examples/sap-odata-apim`.

There are no shared SAP accounts: both SAP connectors create *non-shareable* connections, so every user signs in as themselves and SAP checks their own authorizations. Test and production use SNC with Microsoft Entra ID single sign-on. The solution moves between dev, test and prod with **pac CLI** in GitHub Actions. The pipeline authenticates with **OIDC (no client secret)** and fills connection references and environment variables from a **deployment settings file** per environment.

Skills involved: `sap-api-integration`, `azure-auth-entra`, `adf-cicd` (ALM patterns).

> **Status:** 12 unit tests and 10 static checks pass (`tests/validate_example.py`). The validator caught all ten faults deliberately injected into a copy; one of them (a password hidden inside the SAP system JSON) was first caught only by a unit test, and the static check was tightened to catch it directly. The unit tests evaluate the flows' **real expressions** with a small Workflow Definition Language evaluator (`tests/wdl.py`). The runtime tests (TC-01…TC-14) have **not yet run** in real Power Platform environments against SAP. Five details of the flow JSON aren't published and must be confirmed in the designer (section 4).

## 1. Scenario

| Item | Value |
| --- | --- |
| SAP | S/4HANA (or ECC for the RFC flow), client `100`; users with `S_RFC` for `BAPI_MATERIAL_AVAILABILITY` and the `RFC_METADATA` functions the connector needs, plus business-partner display for the OData flow |
| Connectivity | On-premises data gateway (Windows VM next to SAP, SAP NCo 3.1 x64) for the SAP ERP connector; APIM (public or VNet-injected) for SAP OData |
| Power Platform | Environments dev, test, prod (Dataverse); solution `SapSalesAssistant`, publisher prefix `sap` |
| Licences | Premium (both SAP connectors are premium), per user or per app |

```
Power Apps canvas app ──Run()──► SAP - Check material availability (Power Apps V2 trigger)
                                   validate input → SAP ERP: Call SAP function (V2) BAPI_MATERIAL_AVAILABILITY
                                   (SAP system JSON from environment variable sap_SapSystem; user's own connection)
                                   RETURN-TYPE E/A → {status:error, message}; else {status:ok, quantity}; Catch → technical error
                                 ──► on-premises data gateway ──RFC──► SAP

Power Apps canvas app ──Run()──► SAP - Search business partners
                                   validate input (3-40 chars) → SAP OData: Query OData entities A_BusinessPartner
                                   $filter startswith(BusinessPartnerFullName,'<escaped>') · $select · $top ≤ 50
                                 ──HTTPS (Entra ID token)──► API Management (validate-jwt, roles) ──► SAP Gateway OData

GitHub Actions (OIDC) ── export/unpack (dev) · pack managed + solution checker · import test → prod (settings.<env>.json)
```

## 2. Files

| File | Purpose |
| --- | --- |
| `solution/solution.json` | Source of truth for the solution's components: publisher, environment variables, connection references, flows. |
| `solution/flows/*.json` | The two cloud flow definitions (as the designer shows them in *Peek code*). |
| `solution/src/` | Created by the *export* job: the solution unpacked with `pac solution unpack` (commit it). |
| `deployment/settings.{dev,test,prod}.json` | Deployment settings (documented format): `sap_SapSystem`, `sap_MaxResults`, connection IDs per environment. |
| `pipelines/powerplatform-alm.yml` | GitHub Actions: export/unpack, pack managed, solution checker, import into test and prod. |
| `app/formulas.md` | Power Fx for the canvas app screens. |
| `tests/wdl.py` | Small evaluator for the flows' expressions. |
| `tests/test_units.py`, `tests/validate_example.py`, `tests/fixtures/` | Offline tests, static checks, sample SAP responses (BAPI JSON, OData v2 and v4). |

## 3. Offline checks

```bash
pip install pyyaml
```

```bash
python3 examples/powerplatform-sap/tests/validate_example.py
```

| ID | Static check |
| --- | --- |
| ST-01 | JSON and YAML parse |
| ST-02 | Flows use only the solution's connection references; components use the publisher prefix |
| ST-03 | Actions use operation IDs published in the SAP ERP / SAP OData connector references (deprecated `Invoke` rejected) |
| ST-04 | Environment variables used by the flows are declared |
| ST-05 | Deployment settings for dev, test and prod cover exactly the solution's environment variables and connection references |
| ST-06 | No credentials anywhere, including inside the SAP system JSON |
| ST-07 | Input validated before SAP; Try/Catch; retries; every exit answers Power Apps with the same schema |
| ST-08 | Read-only: allow-listed RFCs, no create/update/delete; OData with `$select` and capped `$top` |
| ST-09 | ALM: every `pac auth` uses GitHub federation; managed solution imported with each environment's settings; prod gated after test |
| ST-10 | Unit tests pass |

| ID | Unit test (evaluates the real flow expressions) |
| --- | --- |
| UT-01 | BAPI inputs trimmed and uppercased; SAP system JSON taken from the environment variable |
| UT-02 / UT-03 | Success and warning → `ok` with quantity; `E` → `error` with SAP's message |
| UT-04 | Invalid material, plant or unit → error answer, no SAP call |
| UT-05 / UT-06 | OData v2 (`d.results`) and v4 (`value`) responses shaped for the app; category text |
| UT-07 | Filter injection (`O'Brien`, `x') or (1 eq 1`, `'''`, …) stays inside one OData string literal |
| UT-08 / UT-09 | `$top` capped at 50; short search text rejected |
| UT-10 / UT-11 | SAP system JSON per environment uses only properties from the connector reference and the right ones for its logon type; SNC in test and prod |
| UT-12 | Every expression in both flows parses (quoting, brackets) |

## 4. To confirm in the designer (not covered by published docs)

| ID | What |
| --- | --- |
| UV-01 | Flow JSON layout: `OpenApiConnection` host keys, `connectionReferences`, environment variable parameter names `'<display name> (<schema name>)'` |
| UV-02 | `CallRfcJson` input nesting (`rfcInputs`) and output shape (`RETURN` object, `AV_QTY_PLT` number) |
| UV-03 | Power Apps (V2) trigger input names (`text`, `text_1`, `text_2`) and the response schema |
| UV-04 | SAP OData output through APIM (`d.results` for OData v2) and `top` as a number |
| UV-05 | SAP system JSON for SNC with Entra ID (Kerberos): `UseSnc` value and `SncQop`; test the connection in test |

Build each flow in the designer, open *Peek code*, compare, fix any difference here and rerun the validator.

## 5. Runbook

### Phase 0 — SAP and network (Basis team)

1. SAP users: `S_RFC` for `BAPI_MATERIAL_AVAILABILITY` and the connector's metadata functions (`RFC_METADATA_GET`, `RFC_METADATA_GET_TIMESTAMP`, `RFC_GROUP_SEARCH`, `DD_LANGU_TO_ISOLA`, per the connector reference), plus business-partner display authorizations for the OData service.
2. Test `BAPI_MATERIAL_AVAILABILITY` in **SE37** with the test material and plant; note the quantity.
3. For SSO in test and prod: SNC with CommonCryptoLib, SNC names `p:CN=<user UPN>` matching the users' Entra ID UPNs, and Kerberos constrained delegation for the gateway service account (see the SAP ERP connector reference).

### Phase 1 — Connectivity

1. Windows VM with network access to SAP: install the **on-premises data gateway** (3000.194 or later, same region as the Power Platform environments), the Visual C++ 14.x runtime and **SAP NCo 3.1 x64**. Use a gateway cluster in failover mode only: stateful SAP sessions don't support load balancing.
2. Deploy `examples/sap-odata-apim` and note its gateway URL and API app ID URI. In Entra ID, add the **SAP OData connector** client (`6bee4d13-fd19-43de-b82c-4b6401d174c3`, per Microsoft Learn) as an authorized client application of the API app, and assign users the `BusinessPartner.Read` role.

### Phase 2 — Power Platform

1. Three environments with Dataverse. **Data policy** (DLP): put *SAP ERP*, *SAP OData* and *Microsoft Dataverse* in the **Business** group, and block *HTTP* and other unneeded connectors for these environments.
2. In dev, create the solution `SapSalesAssistant` (publisher prefix `sap`), the environment variables and connection references from `solution/solution.json`, the two flows from `solution/flows/` and the canvas app from `app/formulas.md`.
3. Create the connections:
   - **SAP ERP**: *SAP Authentication* in dev; *Microsoft Entra ID (with Kerberos)* in test and prod; always through the gateway.
   - **SAP OData**: *Microsoft Entra ID Integrated (with APIM)*, with OData Base URI `https://<apim-name>.azure-api.net/sap/opu/odata/sap/API_BUSINESS_PARTNER` and resource URI `api://sap-odata-apim-test`.
   Copy each connection ID into the matching `deployment/settings.<env>.json`.
4. Complete the checks in section 4.

### Phase 3 — ALM

1. Entra app registration for ALM with federated credentials for this repository's workflow (`repo:<org>/<repo>:environment:powerplatform-test`, `…:environment:powerplatform-prod`, and one for the export/build jobs). Add it as an **application user** with *System Customizer* in each environment.
2. GitHub: repository variables `PP_TENANT_ID`, `PP_APP_ID`, `PP_DEV_URL`, `PP_TEST_URL`, `PP_PROD_URL`; environments `powerplatform-test` and `powerplatform-prod` (with required reviewers).
3. Copy `pipelines/powerplatform-alm.yml` to `.github/workflows/`. Run it with **export**, then commit the unpacked solution into `solution/src/` through a pull request.
4. Run it with **deploy**: it packs a managed solution, runs the solution checker and imports into test and, after approval, into prod.

## 6. Runtime test cases

| ID | Test | Expected result |
| --- | --- | --- |
| TC-01 | SAP ERP *Run Diagnostics* in dev | Gateway running, credentials OK, `STFC_CONNECTION` callable |
| TC-02 | App: availability of the test material | Quantity equals the SE37 result |
| TC-03 | Material that doesn't exist in the plant | Red message with SAP's text; flow run *Succeeded* |
| TC-04 | Plant with 3 characters | Message *Check material…*; no SAP call in the run |
| TC-05 | Partner search `Contoso` | List with names and categories; APIM logs the user's token, not a technical user |
| TC-06 | Partner search `O'Brien` and `x') or (1 eq 1` | Correct results / empty list; no OData syntax error, no extra rows |
| TC-07 | User without the APIM role | Friendly error; APIM returns 403 |
| TC-08 | Stop the gateway service | Availability shows *SAP is not reachable…* with a run reference; start it again |
| TC-09 | User without `S_RFC` for the BAPI | SAP authorization error shown; SU53 shows the missing check |
| TC-10 | SSO in test (Entra ID with Kerberos) | SAP security audit log (SM20) shows the user's own SAP user, not a shared one |
| TC-11 | Export run | Unpacked solution artifact; generated settings list the same names as `deployment/` |
| TC-12 | Deploy run | Solution checker passes; managed import into test with settings; flows on, connection references bound |
| TC-13 | Prod job | Waits for approval; after it, same version in prod with prod settings (SNC) |
| TC-14 | DLP | Adding an HTTP action to a flow in these environments is blocked |

**Acceptance:** ST-01…ST-10 pass in strict mode, UV-01…UV-05 confirmed, TC-01…TC-14 pass.

## 7. Production notes

- Prefer **SSO** (Entra ID with Kerberos or certificates for SAP ERP; Entra ID with APIM for SAP OData) over SAP passwords in connections.
- Keep the flows **read-only** unless the business process needs writes; for BAPIs that change data, use a stateful session with an explicit `BAPI_TRANSACTION_COMMIT`.
- Watch the connector limits: 2,500 calls per connection per 60 s, and the gateway's 2 MB write / 8 MB compressed read limits.
- Use **managed environments**, DLP policies and the solution checker in the pipeline. Never edit flows directly in test or prod.
- Replace any *Call SAP function* (v1) actions: their support ended in July 2026 (connector reference).

## 8. Cleanup

Delete the solution from test and prod (`pac solution delete --solution-name SapSalesAssistant`), the connections, the ALM app registration and, if not shared with other workloads, the gateway VM.

## 9. Results log

| ID | Date | Result | Notes |
| --- | --- | --- | --- |
| UT-01…UT-12 | 2026-11-05 | Pass | Offline, real flow expressions evaluated |
| ST-01…ST-10 | 2026-11-05 | Pass | 10/10 injected faults detected (ST-06 tightened for credentials inside the SAP system JSON) |
| UV-01…UV-05 | | To confirm | Designer *Peek code* and first connection tests |
| TC-01…TC-14 | | Not run | Requires Power Platform environments, gateway and SAP |
