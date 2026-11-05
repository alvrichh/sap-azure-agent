---
name: sap-api-integration
description: Integrate applications and processes with SAP through APIs — SAP OData/REST services (SAP Gateway, S/4HANA, SAP Business Accelerator Hub), Azure API Management in front of SAP, Logic Apps SAP connector for RFC/BAPI/IDoc, Power Platform SAP OData connector, SAP BTP / Integration Suite (Cloud Integration, API Management, Event Mesh, Cloud Connector, Edge Integration Cell) with Azure, and the connectivity options (VNet peering, RISE, on-premises data gateway). Use for transactional or near-real-time integration; for bulk analytics extraction use adf-sap-pipeline / sap-cdc-incremental.
---

# SAP API integration (OData, RFC/BAPI/IDoc, Integration Suite)

Always respect SAP's API policy and licensing (named users, indirect access); flag it to the user. Verify connector capabilities and preview status with the `microsoft-learn` MCP server.

## 1. Pick the integration style

| Need | Protocol | Recommended Azure / Microsoft component |
| --- | --- | --- |
| Read/write business objects from apps, agents, Power Platform | **OData v2/v4, REST** (SAP Gateway, RAP services, S/4HANA APIs) | **Azure API Management** in front of SAP; Power Platform **SAP OData connector**; Logic Apps HTTP |
| Call function modules / BAPIs, send or receive **IDocs** | **RFC, BAPI, IDoc** | **Logic Apps SAP connector** (built-in in Standard preferred); Power Platform SAP ERP connector via on-premises data gateway |
| React to business events (order created, BP changed) | **Events** | **SAP Event Mesh → Azure Event Grid**, then Functions / Logic Apps / Service Bus |
| Customer already standardised on SAP BTP | Integration flows, managed APIs | **SAP Integration Suite** (Cloud Integration, API Management) calling Azure services; **Edge Integration Cell** on AKS for hybrid |
| Bulk / analytical extraction | ODP, table reads | Not here → `adf-sap-pipeline`, `sap-cdc-incremental`, `microsoft-fabric` |

S/4HANA Cloud public edition, SuccessFactors, Ariba and Concur expose **OData/REST only** (no RFC/BAPI). Look for released APIs in the **SAP Business Accelerator Hub** (api.sap.com) before building custom ones; build custom services with the ABAP RESTful Application Programming Model (RAP) or SAP Gateway Service Builder.

## 2. Connectivity (how Azure reaches SAP)

| SAP location | Path |
| --- | --- |
| SAP on Azure (native or **RISE**) | **VNet peering** / private network: APIM, Logic Apps Standard (VNet integration) reach SAP on private IPs — no proxy, best security and latency. RISE exposes RFC/HTTPS ports to the customer VNet; agree it with SAP ECS |
| On-premises behind a firewall | Site-to-site VPN / ExpressRoute (preferred), or **on-premises data gateway** (Power Platform, Logic Apps managed connector), or **self-hosted IR** (Data Factory) |
| Through SAP BTP | **SAP Cloud Connector** (HA: main + shadow instance on two VMs) and **SAP Private Link service** for BTP → Azure private connectivity |

Never expose SAP Gateway directly to the internet; put APIM (with WAF / Application Gateway if public) in front.

## 3. Expose SAP OData through Azure API Management

1. Deploy APIM with `templates/bicep/apim-sap-odata.bicep`: system identity with Key Vault access, Key Vault-backed named values and the SAP **backend** with TLS validation (never disable chain validation in production). Worked example with tests: `examples/sap-odata-apim/`.
2. Get the metadata: SAP Gateway client (`/IWFND/GW_CLIENT`), `https://<host>:<port>/sap/opu/odata/sap/<SERVICE>/$metadata`, or the Business Accelerator Hub (which also offers the OpenAPI file). Activate services with `/IWFND/MAINT_SERVICE`.
3. **Recommended**: convert the metadata to OpenAPI (Microsoft `odata-openapi-converter`) and import as **OpenAPI** (`az apim api import`); alternatively import directly as an **OData** API in the portal. Use the same URL suffix as the SAP service path.
4. Apply policies — template `templates/apim/sap-odata-csrf-policy.xml`:
   - `sap-client` query parameter;
   - technical-user authentication from Key Vault-backed named values **or** SAP **principal propagation** (official APIM snippet) when each user must act with their own SAP authorizations (see `azure-auth-entra`);
   - **X-CSRF-Token fetch** before write operations (SAP Gateway rejects POST/PUT/PATCH/DELETE without it);
   - the `validate-odata-request` policy when imported as an OData API.
5. Protect with Entra ID (`validate-azure-ad-token` with audience and app roles), rate limits, **Defender for APIs**. Manage APIs as code (APIOps).

## 4. Consume SAP OData

- **Data Factory** — SAP ECC connector (`SapEcc`, works for any SAP Gateway OData service, Azure or self-hosted IR, basic auth): `templates/adf/linked-services/sap-ecc-odata.json`, `templates/adf/datasets/sap-ecc-odata.json`; filter with an OData query (`$select=...&$filter=...`). For full tables prefer the SAP Table connector (faster).
- **Power Platform / Copilot Studio** — SAP OData connector (V2–V4): basic, Entra ID via APIM (principal propagation), Entra ID via SuccessFactors, OAuth 2.0 (preview).
- **Logic Apps / Functions / apps** — HTTP calls through APIM.

OData practicalities with SAP Gateway:
- Always use `$select` and `$filter`; page with `$top`/`$skip` and follow server-driven paging links (`__next` in V2, `@odata.nextLink` in V4).
- Writes need `X-CSRF-Token` + the session cookies from the fetch call; updates usually need `If-Match` with the entity ETag.
- Use `$batch` for multiple changes in one logical unit of work.
- Pass `sap-client` (and `sap-language` if needed).

## 5. RFC, BAPI and IDoc with Logic Apps

| | **SAP built-in connector** (Logic Apps Standard) | SAP managed connector |
| --- | --- | --- |
| Network | Direct from the VNet-integrated app — **no data gateway** | On-premises data gateway |
| Client library | SAP NCo **3.1**, uploaded with the app (non-redistributable, from SAP) | SAP NCo 3.0 on the gateway |
| Operations | Dedicated actions: **[BAPI] Call method**, **[RFC] Call function**, **[IDoc] Send document**; triggers to receive IDocs/RFCs | Generic send/receive |
| Scale / payload | Stateful mode for HA and scale-out; payloads up to 100 MB | Gateway limits (single-instance triggers) |
| Auth | Username/password or **SNC** (PSE in app settings) | Same |

Prefer the **built-in connector**. Use a dedicated RFC user with least authorizations; for BAPIs that change data enable **Auto Commit** or call `BAPI_TRANSACTION_COMMIT` explicitly.

## 6. SAP BTP and Integration Suite with Azure

- **Cloud Integration (CPI)** iFlows can call Azure services (Service Bus, Event Grid, Storage, APIM-fronted APIs) — keep credentials in the BTP keystore / Azure Key Vault, not in iFlows.
- **SAP Event Mesh ↔ Azure Event Grid** for event-driven extensions.
- **Edge Integration Cell** (hybrid Integration Suite runtime) can run on **AKS** (Azure accelerator, Terraform) and on-premises via Azure Arc.
- **SAP Private Link service** connects BTP apps privately to Azure workloads.
- SAP Process Orchestration (PI/PO) is legacy; Integration Suite is the successor.

## 7. Checklist

- [ ] Integration style matches the need (API vs RFC vs events vs bulk).
- [ ] Released SAP API checked in the Business Accelerator Hub before building custom.
- [ ] Private connectivity (peering/VPN/ExpressRoute, Cloud Connector or gateway) — no internet-exposed SAP.
- [ ] APIM in front of SAP OData with Entra ID auth, CSRF handling, rate limits, Defender for APIs.
- [ ] Technical users least-privilege, secrets in Key Vault; principal propagation where per-user authorizations matter.
- [ ] SAP API policy and licensing confirmed.

## References (Microsoft Learn)

- SAP and Microsoft integration scenarios: https://learn.microsoft.com/azure/sap/workloads/integration-get-started
- Import SAP OData into API Management: https://learn.microsoft.com/azure/api-management/sap-api
- Logic Apps SAP connector: https://learn.microsoft.com/azure/logic-apps/connectors/sap
- Data Factory SAP ECC (OData) connector: https://learn.microsoft.com/azure/data-factory/connector-sap-ecc
- Power Platform SAP OData connector: https://learn.microsoft.com/power-platform/sap/connect/sap-odata-connector
- Integrate Azure services with SAP RISE: https://learn.microsoft.com/azure/sap/workloads/rise-integration-services
- SAP Edge Integration Cell on Azure: https://learn.microsoft.com/azure/sap/workloads/sap-edge-integration-cell-with-azure
- Copilot Studio with SAP (connectivity patterns): https://learn.microsoft.com/azure/sap/microsoft-ai/copilot-studio/copilot-with-sap-overview
