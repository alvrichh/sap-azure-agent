# Test case: Logic Apps Standard exchanging IDocs with SAP

A complete, reproducible test of the agent's IDoc path in both directions with the **SAP built-in connector** of **Logic Apps Standard**. It needs no on-premises data gateway, keeps credentials in **Key Vault** and reaches SAP over **VNet integration**:

- **Azure → SAP:** an HTTP API turns a JSON sales order into an **ORDERS05** IDoc and sends it with an explicit **transaction ID (TID)**, so a retry can never create a duplicate order. A second API returns the IDoc's processing status.
- **SAP → Azure:** SAP sends **DEBMAS** (customer master) IDocs to a registered server program. The workflow acknowledges them at once, splits the packet and forwards the customers to a downstream API with the app's managed identity.

Skills involved: `sap-api-integration`, `azure-auth-entra`, `azure-bicep-iac`.

> **Status:** 14 unit tests and 16 static checks pass (`tests/validate_example.py`). The validator caught all ten faults deliberately injected into a copy; one of them exposed a blind spot in the expression check, which was then fixed. The runtime tests (TC-01…TC-14) have **not yet run against a real SAP system**. Seven details of the built-in connector's JSON and IDoc XML layout aren't published in the docs and must be confirmed in the designer or with a first real IDoc (section 4).

## 1. Scenario

| Item | Value |
| --- | --- |
| SAP | S/4HANA or ECC, SID `S4P`, client `100`, logical system `<sap-logical-system>`, technical user `RFC_IDOC_LA` |
| Azure → SAP | `ORDERS` / `ORDERS05`, inbound process code `ORDE`, processing **Trigger by background program** |
| SAP → Azure | `DEBMAS` / `DEBMAS07` through a tRFC port to the RFC destination `LOGICAPP_IDOC_DEV` (registered server program) |
| Azure | Logic App Standard (WS1, 64-bit) with VNet integration and **2 VNet private ports** (stateful mode), Key Vault, storage account |

```
Azure → SAP
Client ──HTTPS──► wf-send-sales-order-idoc (Stateful)
                    1. Request trigger: strict JSON schema (400 if invalid)
                    2. TID = transactionId from the caller, or guid()
                    3. Select + Compose + xml(): ORDERS05 (EDI_DC40, E1EDK01, E1EDK14 ×4, E1EDKA1, E1EDK02, E1EDP01/E1EDP19 per item)
                    4. [IDoc] Send document to SAP: SapPlainXml, tId = TID, confirmTid = false (retry ×3, same TID)
                    5. [IDOC - RFC] Confirm transaction Id (only after a successful send)
                    6. [IDoc] Get IDoc list for transaction → 202 {transactionId, idocNumbers}
                    Catch (Failed/TimedOut) → 502 {transactionId, runId}: the caller retries with the same transactionId
Client ──HTTPS──► wf-idoc-status (Stateless): [IDoc] Get IDoc status → 200 {status, description} | 502

SAP → Azure
SAP (BD12/BD14 or change pointers) ──tRFC──► gateway ──registered program LOGICAPP_IDOC_DEV──►
                  wf-receive-customer-idoc (Stateful, SAP trigger "When a message is received", SapPlainXml)
                    1. Respond to SAP server (first action: frees the SAP connection; IDoc status 03 in SAP)
                    2. MESTYP = DEBMAS?  no → run Cancelled (misrouted IDoc, not rejected back to SAP)
                    3. Select over every IDOC in the packet: DOCNUM, KUNNR, NAME1, LAND1, ORT01, LOEVM
                    4. HTTP POST to the customer API with managed identity (retry ×4, exponential)
                    5. Failure → run Failed with a clear error: resubmit the run (the IDoc is already accepted)
```

## 2. Files

| File | Purpose |
| --- | --- |
| `../../templates/bicep/logicapp-standard-sap.bicep` | Reusable template (shared with the RFC case). Now also takes `vnetPrivatePortsCount` (stateful mode) and `additionalAppSettings`. |
| `bicep/logicapp.dev.bicepparam` | Parameters: private ports = 2, gateway/program ID, IDoc partner settings, downstream API. |
| `config/settings.example.json` | Non-secret test data and SAP objects to create. |
| `logicapp/host.json` | Extension bundle and SAP action timeout (2 minutes). |
| `logicapp/connections.json` | SAP built-in connection; every value from app settings. |
| `logicapp/parameters.json` | Workflow parameters from app settings, plus IDoc status texts. |
| `logicapp/wf-send-sales-order-idoc/workflow.json` | Azure → SAP: JSON order → ORDERS05 with explicit TID. |
| `logicapp/wf-idoc-status/workflow.json` | IDoc status lookup. |
| `logicapp/wf-receive-customer-idoc/workflow.json` | SAP → Azure: DEBMAS packets to the customer API. |
| `logicapp/lib/builtinOperationSdks/net472/` | Where the SAP NCo DLLs go (not in Git: licensed by SAP). |
| `tests/fixtures/` | Sample order, DEBMAS07 packet (2 customers, one flagged for deletion), MATMAS05 (wrong message type). |
| `tests/test_units.py` | 14 offline tests that read the workflow JSON and evaluate it. |
| `tests/validate_example.py` | 16 static checks + unit tests. |

## 3. Offline checks

```bash
pip install lxml jsonschema
```

```bash
python3 examples/logicapps-sap-idoc/tests/validate_example.py
```

| ID | Static check |
| --- | --- |
| ST-01 | JSON parses |
| ST-02 / ST-03 / ST-04 | SAP connection values only from app settings; every app setting is deployed by Bicep (template or `additionalAppSettings`); every workflow parameter is defined |
| ST-05 | Password as Key Vault reference, 64-bit, VNet integration, **VNet private ports = 2** |
| ST-06 | Trigger and actions use a defined connection and an operation ID published in the connector reference |
| ST-07 | SAP trigger: IDoc format, parallelism, gateway host/service and program ID present, taken from settings, program ID in one consistent (uppercase) form |
| ST-08 | Inbound: *Respond to SAP server* is the first action; no exception sent back to SAP for application errors |
| ST-09 | Outbound: one TID per order, `confirmTid=false`, explicit confirm only after a successful send, retries |
| ST-10 | Strict request schemas (closed objects, patterns, `maxItems`) with schema validation; 202/200/502 responses |
| ST-11 | Send and receive workflows are stateful (run history for audit and resubmission) |
| ST-12 | SAP action timeout ≤ 230 s |
| ST-13 | Downstream call with managed identity (no keys) |
| ST-14 / ST-15 | NCo DLLs not in Git, parameter file → template; no secrets anywhere |
| ST-16 | Unit tests pass |

| ID | Unit test (evaluates the real `workflow.json`) |
| --- | --- |
| UT-01 / UT-02 | Order schema accepts a valid order; rejects missing/extra fields, empty items, bad `POSEX`, decimal comma, markup, bad sales org, non-GUID TID |
| UT-03…UT-05 | Built ORDERS05: control record (`DIRECT=2`, partners from settings), segment order, `E1EDK14` qualifiers 008/007/006/012, sold-to `AG`, PO number, one `E1EDP01`+`E1EDP19` per item, `SEGMENT="1"` attributes |
| UT-06 / UT-07 | Send, confirm and list share one TID; confirm runs only after success; 502 returns the TID for a safe retry |
| UT-08…UT-11 | Receive: respond first; DEBMAS packet split into 2 customers (entities decoded, deletion flag); MATMAS not forwarded; downstream failure fails the run; managed identity |
| UT-12 / UT-13 | Status texts (53, 51, unknown); status request schema |
| UT-14 | Expression string literals well formed (catches `'` inside `'…'`) |

## 4. To confirm (not covered by published docs)

The [connector reference](https://learn.microsoft.com/azure/logic-apps/connectors/built-in/reference/sap/) documents operation IDs and parameters, but not every JSON key the designer writes or the exact IDoc XML layout. Create the three operations once in the portal designer, open **Code view**, send one test IDoc each way and compare:

| ID | What | Where |
| --- | --- | --- |
| UV-01 | `serviceProviderId` and connection parameter keys | `connections.json` |
| UV-02 | `sendIDoc` payload key `body` | `wf-send-sales-order-idoc` |
| UV-03 | `SapPlainXml` layout accepted by `sendIDoc` and produced by the trigger for packets (`<DEBMAS07><IDOC BEGIN="1">…`) | both directions; fixtures |
| UV-04 | `getIDocList` output `iDocNumbers` (list or string) and `getIDocStatus` output `iDocStatus` | send and status workflows |
| UV-05 | `respondToSapServer` body for a tRFC IDoc (empty assumed: tRFC has no response) | receive workflow |
| UV-06 | Keys starting with `@` (`@SEGMENT`, `@BEGIN`) accepted by Compose/Select; otherwise escape as `@@SEGMENT` | send workflow |
| UV-07 | Trigger output `content` vs `Content` | receive workflow |

Fix any difference in the repository, rerun the validator and record it in the results log.

## 5. Runbook

### Phase 0 — SAP (Basis team)

Common:

1. Technical user `RFC_IDOC_LA` (type *System*): `S_RFC` for the function groups the connector calls (typically `ARFC`, `ERFC`, `EDIN` for `IDOC_INBOUND_ASYNCHRONOUS`, `EDIMEXT` for IDoc metadata, `RFC1`, `SDIFRUNTIME`) and `S_IDOCDEFT` for the IDoc types. Record an authorization trace (**STAUTHTRACE**) during TC-02/TC-05 and trim the role to what it shows. Posting the order runs in background (`RBDAPP01`) under that job's user, which needs the sales-order authorizations for the test sales area.
2. Logical systems (**BD54**): `LOGICAPP` (Azure) and the SAP client's own logical system.
3. Network: the integration subnet must reach the application server's dispatcher (`32<NN>`) and gateway (`33<NN>`) ports.

SAP → Azure (registered server program):

4. **SM59** → *TCP/IP connection* `LOGICAPP_IDOC_DEV`, activation type **Registered Server Program**, program ID `LOGICAPP_IDOC_DEV` (case-sensitive, same value as `SAP_PROGRAM_ID`), **Unicode** communication.
5. Gateway ACL (**SMGW** → *Goto → Expert Functions → External Security → Maintenance of ACL Files*, `reginfo`): `P TP=LOGICAPP_IDOC_DEV HOST=<integration-subnet-addresses> ACCESS=*`. Without it, registration fails with *Registration of tp … not allowed*.
6. **WE21** → tRFC port pointing to `LOGICAPP_IDOC_DEV`.
7. **WE20** → partner `LOGICAPP` (LS), outbound parameters: `DEBMAS` / `DEBMAS07`, receiver port from step 6, *Transfer IDoc immediately* (or collect into packets for the packet test).
8. Distribution model (**BD64**) or **BD12** to send customers to `LOGICAPP`.

Azure → SAP:

9. **WE20** → partner `LOGICAPP` (LS), inbound parameters: `ORDERS`, process code `ORDE`, **Trigger by background program** (otherwise SAP processes the IDoc inside the call and the 2-minute action timeout can expire). Schedule `RBDAPP01` for the partner.
10. Customer, material and sales area of the test order exist and allow order creation (test once in **VA01**).

### Phase 1 — Azure

1. VNet with a subnet delegated to `Microsoft.Web/serverFarms` that reaches SAP. If you use NSGs, allow ports **20000–30000** inside the subnet (VNet private ports for stateful mode).
2. Store the SAP password in Key Vault (prompted, not saved to history):

```bash
az keyvault secret set --vault-name <key-vault-name> --name sap-idoc-password --value "$(read -rsp 'SAP password: ' p; echo "$p")"
```

3. Fill the placeholders in `bicep/logicapp.dev.bicepparam`, then deploy:

```bash
az deployment group what-if --resource-group rg-sapidoc-dev --parameters examples/logicapps-sap-idoc/bicep/logicapp.dev.bicepparam
```

```bash
az deployment group create --resource-group rg-sapidoc-dev --parameters examples/logicapps-sap-idoc/bicep/logicapp.dev.bicepparam
```

4. Stateful mode also needs a fixed instance count so that a scale-in can't drop the trigger's context: logic app → *Scale out* → *Enforce scale out limit* = Yes and *Always ready instances* = maximum (e.g. 1 for this test).
5. The downstream API (`CUSTOMER_API_URL`) must accept tokens for `CUSTOMER_API_AUDIENCE` from the logic app's managed identity (see `azure-auth-entra`). For a first test, another Request-triggered workflow can stand in for it.

### Phase 2 — SAP libraries and workflows

1. Upload the x64 NCo 3.1 DLLs (`rscp4n.dll`, `sapnco.dll`, `sapnco_utils.dll`) as **Client/SDK Assembly (.NET Framework)**, or place them in `logicapp/lib/builtinOperationSdks/net472/` locally (ignored by Git).
2. Deploy the `logicapp/` project (VS Code *Deploy to logic app*, or zip deploy from CI). Saving the receive workflow registers the program ID: check **SMGW** → *Logged-On Clients* (registered server `LOGICAPP_IDOC_DEV`) and **SM59** → *Connection Test*.
3. Complete the checks in section 4.
4. Copy the trigger URLs of the two HTTP workflows. They contain a SAS signature: keep them only in your local `.env` (see the repository's `.env.example`), never in Git.

### Phase 3 — Run the tests

```bash
set -a; source .env; set +a
```

```bash
curl -s -X POST "$IDOC_SEND_TRIGGER_URL" -H "Content-Type: application/json" -d @examples/logicapps-sap-idoc/tests/fixtures/order-request.json
```

```bash
curl -s -X POST "$IDOC_STATUS_TRIGGER_URL" -H "Content-Type: application/json" -d '{"idocNumber":"<idoc-number>"}'
```

Send customers from SAP with **BD12** (customer `<customer-number>`, message type `DEBMAS`, logical system `LOGICAPP`), then check the receive workflow's run history and **WE02** (status 03).

## 6. Runtime test cases

| ID | Test | Expected result |
| --- | --- | --- |
| TC-01 | SM59 connection test of `LOGICAPP_IDOC_DEV` after deploying | Success; SMGW lists the registered server |
| TC-02 | Send the sample order | 202 with `transactionId` and one IDoc number; WE02 shows the ORDERS05 with status 64 → 53 after `RBDAPP01`; sales order created |
| TC-03 | Repeat TC-02 with the same `transactionId` | 202 with the **same** IDoc number; no second sales order (SAP deduplicates the TID) |
| TC-04 | Order with an unknown customer | 202 (transport OK); IDoc status 51 with SAP's message; TC-05 reports it |
| TC-05 | Status of the IDocs from TC-02 and TC-04 | 200 with `53` *Application document posted* and `51` *Application document not posted* |
| TC-06 | Order with an extra field / `quantity` "1,5" / 101 items | 400 (schema validation); no SAP call |
| TC-07 | Block the SAP ports during a send | 502 with `transactionId`; retrying with it after unblocking creates exactly one IDoc |
| TC-08 | BD12 for one customer | Receive run succeeds; the customer API gets 1 customer; WE02 status 03 |
| TC-09 | BD12 for 2 customers collected into one packet | One run, 2 customers forwarded |
| TC-10 | Send a MATMAS to the same partner by mistake | Run *Cancelled*; IDoc not rejected in SAP (SM58 empty) |
| TC-11 | Customer API returns 500 | Run *Failed* with `DownstreamFailed`; resubmitting the run after fixing the API delivers it |
| TC-12 | Remove the ACL line (temporarily) and restart the app | Registration rejected (*Registration of tp … not allowed*) in the gateway log; restore |
| TC-13 | Program ID in a different case in SM59 | SM58 shows *Function IDOC_INBOUND_ASYNCHRONOUS not found* or a partner type error; restore |
| TC-14 | Key Vault reference status (portal → Environment variables) | `SAP_PASSWORD` resolved by Key Vault reference; no plain value |

**Acceptance:** ST-01…ST-16 pass in strict mode, UV-01…UV-07 confirmed, TC-01…TC-14 pass.

## 7. Production notes

- Put **API Management** with Entra ID in front of the HTTP workflows (see `examples/sap-odata-apim`) instead of exposing SAS URLs.
- Use **SNC** for the RFC connection and the registered program, and list the allowed partners in the trigger's *SNC partner names*.
- Don't reject IDocs for data errors after acknowledging them: send application errors to a dead-letter store or alert, and keep SAP free to send the next IDoc.
- Raise *Degree of parallelism* only after checking that the downstream API is idempotent per `idocNumber`.
- Keep stateful mode stable: fixed instance count, and NSG rules for ports 20000–30000 inside the subnet.
- Hide IDoc payloads from run history (*Secure inputs/outputs*) when they contain personal data (customer master does).

## 8. Cleanup

```bash
az group delete --name rg-sapidoc-dev
```

(Only if nothing else lives in the resource group; deletion is irreversible.) In SAP, remove the ACL line, the RFC destination, the ports and the partner profiles, and lock `RFC_IDOC_LA`.

## 9. Results log

| ID | Date | Result | Notes |
| --- | --- | --- | --- |
| UT-01…UT-14 | 2026-11-05 | Pass | Offline |
| ST-01…ST-16 | 2026-11-05 | Pass | Static checks, design mode; 10/10 injected faults detected (UT-14 tightened after the first run missed one) |
| UV-01…UV-07 | | To confirm | Designer code view and a first real IDoc each way |
| TC-01…TC-14 | | Not run | Requires SAP system, VNet path and Azure subscription |
