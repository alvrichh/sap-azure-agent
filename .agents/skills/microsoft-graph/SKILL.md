---
name: microsoft-graph
description: Use Microsoft Graph to connect SAP and Azure solutions with Microsoft 365 — Teams, Outlook, SharePoint, OneDrive, users and groups. Covers delegated vs application permissions and least privilege (Sites.Selected, resource-specific consent), change notifications (webhooks, Event Hubs, Event Grid), delta queries, paging, batching and throttling, Microsoft 365 Copilot connectors to bring SAP data into Copilot and Search, and Graph Data Connect for bulk Microsoft 365 data.
---

# Microsoft Graph

One endpoint (`https://graph.microsoft.com/v1.0`) for Microsoft 365 data. Use `v1.0` in production; `beta` can change without notice. Verify permissions and limits for each API with the `microsoft-learn` MCP server (permissions reference and the API page).

## 1. Typical SAP ↔ Microsoft 365 scenarios

| Scenario | Graph capability |
| --- | --- |
| Approvals / notifications for SAP events (PO approval, delivery delayed) | Teams (bot, Workflows, adaptive cards), Outlook mail — triggered from Logic Apps / Functions fed by SAP events (`sap-api-integration`) |
| SAP documents or exports stored in SharePoint / OneDrive | Drives and lists APIs, scoped with `Sites.Selected` |
| SharePoint list as lightweight front-end that writes back to SAP | List items API + change notifications → Logic App → SAP OData/BAPI |
| Make SAP data searchable in Microsoft 365 Copilot and Search | **Copilot connectors** (synced: index into Graph; federated: real-time via MCP) |
| User/HR sync between SAP and Entra ID | Users/groups APIs, Entra provisioning (`azure-auth-entra`) |
| Bulk Microsoft 365 data into Azure/Fabric analytics | **Graph Data Connect** (not the REST API) |

## 2. Permissions (least privilege first)

- **Delegated**: app acts as the signed-in user (only what the user can access). **Application**: daemon/background, needs admin consent and is tenant-wide unless scoped.
- Pick the **narrowest** permission listed on the API page; prefer `.Read` over `.ReadWrite`, and specific scopes over `.All`.
- **SharePoint/OneDrive for an app**: use `Sites.Selected` (application) and grant per site with `POST /sites/{site-id}/permissions` (`templates/graph/sites-selected-grant.json`; roles `read`/`write`/`manage`/`fullcontrol`). Do **not** also add `Sites.Read.All`, `Files.Read.All` etc.: broader permissions are additive and defeat the restriction.
- **Teams**: prefer resource-specific consent (RSC) for team/chat-scoped access. Posting channel messages via Graph is a **delegated** operation (`ChannelMessage.Send`); for app-originated messages use a bot or Teams Workflows instead (application permission `Teamwork.Migrate.All` is for message migration only). Send only messages people will read — using Teams as a log file violates the API terms of use. Cards posted through Graph only support `Action.OpenUrl`. Office 365 Connectors / incoming webhooks were retired in May 2026: use Teams **Workflows** for one-way alerts.
- **Credentials**: managed identity or workload identity federation (no secrets) where possible; otherwise certificates in Key Vault (`azure-auth-entra`). App permissions for managed identities are assigned with Graph app role assignments (no portal consent screen).
- Limit mailbox access for application permissions with Exchange **RBAC for Applications** (or application access policies), not tenant-wide `Mail.*`.

## 3. Calling Graph reliably

- **Paging**: always follow `@odata.nextLink` (opaque URL) until it is absent.
- **Delta queries** to sync changes efficiently; combine with change notifications as the trigger plus a backstop poll.
- **Batching**: `POST /$batch`, max **20** requests; each sub-request is throttled individually (a 200 batch can contain 429s) — retry those using their `Retry-After`.
- **Throttling**: on 429/503 honour `Retry-After`, reduce concurrency, avoid spikes; SDKs retry automatically (not inside batches).
- `$select` only needed fields; send a `client-request-id` GUID and log it for support.
- Quick calls with the user's own login: `az rest --method get --url "https://graph.microsoft.com/v1.0/me"`. In code use the Microsoft Graph SDKs (.NET, Python, JavaScript, Java, Go, PowerShell).

## 4. Change notifications (subscriptions)

- Delivery: **webhooks**, **Azure Event Hubs** or **Azure Event Grid**. Prefer Event Hubs/Event Grid for volume or when the endpoint can't answer fast.
- Webhook validation: respond within **10 s** with `200`, `text/plain`, URL-decoded `validationToken`. For notifications respond `202` immediately, process asynchronously.
- Validate every notification (`clientState` from Key Vault; JWT `validationTokens` for rich notifications).
- Subscriptions **expire** (per-resource maximum, e.g. 30 days for SharePoint lists): renew with `PATCH /subscriptions/{id}`; add a `lifecycleNotificationUrl` to handle reauthorization and missed notifications.
- Template: `templates/graph/subscription-sharepoint-list.json` (SharePoint lists support `changeType: updated`).
- **Event Hubs without secrets**: notificationUrl `EventHub:https://<ns>.servicebus.windows.net/eventhubname/<hub>?tenantId=<primary-domain>`, SAS disabled, *Microsoft Graph Change Tracking* (appId `0bf30f3b-4a52-48df-9a82-234910c4a086`) as *Azure Event Hubs Data Sender* — `templates/bicep/eventhubs-graph-notifications.bicep`.
- Teams `chatMessage` subscriptions: max 4,320 minutes; more than 1 hour requires `lifecycleNotificationUrl`; with resource data an encryption certificate is mandatory.
- Worked example (Teams approvals for SAP purchase orders, with unit tests): `examples/graph-teams-approvals/`.

## 5. Bring SAP data into Microsoft 365 Copilot (Copilot connectors)

| | Synced connector | Federated connector |
| --- | --- | --- |
| Data | Indexed into Microsoft Graph (semantic index) | Stays in source; fetched at query time via **MCP** |
| Fits | Master data, documents, knowledge (materials, customers, policies) | Volatile or regulated data (stock, open orders) |

Synced custom connector steps (application permissions, e.g. `ExternalConnection.ReadWrite.OwnedBy`, `ExternalItem.ReadWrite.OwnedBy`):

1. Create the connection — `templates/graph/copilot-connector-connection.json`.
2. Register the schema (long-running; poll the operation) — `templates/graph/copilot-connector-schema.json`. Apply semantic labels `title`, `url`, `iconUrl` (required for Copilot) and mark content properties `isSearchable`.
3. Ingest items (`PUT /external/connections/{id}/items/{item-id}`) with **ACLs** mapped to Entra users/groups so users only see what they may see in SAP.
4. Keep in sync incrementally (e.g. from the SAP CDC Delta tables or OData delta), delete removed items.

Ingested items count against the tenant's connector item quota; check licensing. Never index data whose SAP authorizations can't be mapped to ACLs.

## 6. Checklist

- [ ] Delegated vs application decided; narrowest permissions; admin consent documented.
- [ ] `Sites.Selected` / RSC / Exchange RBAC for Applications used instead of tenant-wide access.
- [ ] No client secrets where managed identity or federation works; certificates in Key Vault otherwise.
- [ ] Paging, delta, batching and `Retry-After` handling implemented.
- [ ] Subscriptions renewed automatically, lifecycle notifications handled, notifications validated.
- [ ] Copilot connector items carry correct ACLs; data classification reviewed.

## References (Microsoft Learn)

- Graph best practices: https://learn.microsoft.com/graph/best-practices-concept
- Throttling: https://learn.microsoft.com/graph/throttling
- JSON batching: https://learn.microsoft.com/graph/json-batching
- Paging: https://learn.microsoft.com/graph/paging
- Change notifications: https://learn.microsoft.com/graph/change-notifications-overview
- Webhook delivery: https://learn.microsoft.com/graph/change-notifications-delivery-webhooks
- Sites.Selected / resource-specific consent for SharePoint: https://learn.microsoft.com/sharepoint/dev/sp-add-ins-modernize/understanding-rsc-for-msgraph-and-sharepoint-online
- Copilot connectors API: https://learn.microsoft.com/graph/connecting-external-content-connectors-api-overview
- Copilot connectors overview: https://learn.microsoft.com/microsoft-365/copilot/connectors/overview
