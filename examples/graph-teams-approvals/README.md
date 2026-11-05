# Test case: SAP purchase-order approvals in Microsoft Teams with Microsoft Graph

A complete, reproducible test of the agent's Microsoft 365 path: an SAP purchase order that needs approval is posted to a Teams channel as an Adaptive Card through **Microsoft Graph**; the approver replies in the thread (`APPROVE`, or `REJECT` with a reason); Graph **change notifications** arrive through **Azure Event Hubs** (no secrets); a consumer reads the reply and produces the SAP decision.

Skills involved: `microsoft-graph`, `azure-auth-entra`, `azure-bicep-iac`, `sap-api-integration` (to send the decision back to SAP).

> **Status:** 14 unit tests and 15 static checks pass (`tests/validate_example.py`); the validator caught all six faults deliberately injected into a copy. The runtime tests (TC-01…TC-10) have **not yet run against a real tenant**; record the results at the end.

## 1. Design decisions (verified on Microsoft Learn)

| Constraint | Consequence in this design |
| --- | --- |
| Graph can't post channel messages with **application** permissions (`Teamwork.Migrate.All` is for migration only) | The card is posted with **delegated** `ChannelMessage.Send` by a dedicated service account `svc-sap-teams`. |
| Cards posted through Graph only support **`Action.OpenUrl`** | No Approve/Reject buttons: the card links to SAP Fiori and asks for a **reply in the thread**. For real buttons use a bot or Teams Workflows. |
| Office 365 Connectors / incoming webhooks were **retired (May 2026)** | Not used. Teams **Workflows** is the supported low-code alternative for one-way alerts. |
| Channel message subscriptions last **max 4,320 minutes**; beyond 1 hour they **require `lifecycleNotificationUrl`** | Subscription with lifecycle notifications; renew before expiry. |
| Notifications **with** resource data require an encryption certificate | Subscription **without** resource data; the consumer GETs each reply. |
| Event Hubs delivery supports **Entra RBAC** (SAS is deprecated) | Event Hubs with local auth disabled; *Microsoft Graph Change Tracking* gets **Azure Event Hubs Data Sender**. |

## 2. Architecture

```
SAP (PO needs approval) ─► post_card.py ─Graph (delegated ChannelMessage.Send)─► Teams channel "PO Approvals"
                                                                                       │ approver replies "APPROVE"
Microsoft Graph change notifications (subscription on channel messages, no resource data)
   └─► Event Hubs (RBAC, no SAS) ─► consume.py ─► classify (clientState, subscription, reply?) 
                                                  └─► GET reply (Graph) ─► decide ─► {"status":"approved","po":"4500001234",...}
                                                                                     └─► SAP release (sap-api-integration)
```

## 3. Files

| File | Purpose |
| --- | --- |
| `config/settings.example.json` | Non-secret settings (team/channel IDs, app, approvers, Event Hubs). Copy to `settings.json` (ignored by Git). |
| `../../templates/bicep/eventhubs-graph-notifications.bicep` | Reusable template: Event Hubs without SAS, roles for Graph (sender) and the consumer (receiver). |
| `bicep/eventhubs.dev.bicepparam` | Parameters for the test. |
| `graph/subscription-channel-messages.json` | Graph subscription body. |
| `src/teams_approvals/card.py` | Builds and validates the card message (Graph rules). |
| `src/teams_approvals/notifications.py` | Classifies notifications: validation, lifecycle, wrong clientState/subscription, replies. |
| `src/teams_approvals/decision.py` | Turns a reply into a decision (approvers only, first decision wins, REJECT needs a reason). |
| `scripts/get_token.py` | Delegated Graph token via device code (public client, no secret). |
| `scripts/post_card.py` | Posts the card (`--dry-run` prints the request body). |
| `scripts/consume.py` | Reads Event Hubs, fetches replies, prints decisions. |
| `tests/test_units.py`, `tests/fixtures/` | 14 unit tests with realistic Graph payloads. |
| `tests/validate_example.py` | Static checks + unit tests. |

## 4. Offline checks

```bash
python3 examples/graph-teams-approvals/tests/validate_example.py
```

| ID | Check |
| --- | --- |
| ST-01 | JSON parses |
| ST-02…ST-06 | Subscription: `created` on channel messages; Event Hubs with RBAC + tenantId; lifecycle URL; no resource data; clientState not committed |
| ST-07 / ST-08 | Least-privilege permissions; token script requests exactly those scopes |
| ST-09 / ST-10 | Event Hubs without SAS; Graph Change Tracking = Data Sender, consumer = Data Receiver |
| ST-11 | Parameters, subscription and settings use the same hub |
| ST-12 / ST-13 | Scripts compile; tokens only from the environment, never written to disk |
| ST-14 | No secrets or tokens in any file |
| ST-15 | Unit tests UT-01…UT-14 pass |

| ID | Unit test |
| --- | --- |
| UT-01…UT-04 | Card follows Graph rules (attachment reference, string content, only `Action.OpenUrl`), formats amounts, rejects bad PO numbers / non-HTTPS links, validator catches `Action.Submit` |
| UT-05…UT-07 | Validation messages ignored; replies extracted; mixed batch: wrong clientState, unknown subscription, updates, top-level posts, lifecycle events |
| UT-08…UT-13 | APPROVE; REJECT with reason (HTML unescaped); REJECT without reason invalid; non-approvers unauthorized; notifier/bots/chatter/system/other threads ignored; first decision wins |
| UT-14 | Event Hubs event → Graph GET → decision, end to end with fixtures |

Preview the request body without calling Graph:

```bash
python3 examples/graph-teams-approvals/scripts/post_card.py --team T --channel C --po examples/graph-teams-approvals/tests/fixtures/po.json --fiori-url "https://fiori.example.com/po" --dry-run
```

## 5. Runbook

### Phase 1 — Teams and Entra ID (`azure-auth-entra`, `microsoft-graph`)

1. Create (or reuse) a **test team** and a channel **PO Approvals**; note the team ID and channel ID. Add the service account `svc-sap-teams`, one approver and one non-approver.
2. App registration **`sap-teams-approvals`**: *Allow public client flows* = yes (device code); delegated Graph permissions **`ChannelMessage.Send`** and **`ChannelMessage.Read.All`**; grant admin consent (Read.All requires it).
3. Note the object IDs of `svc-sap-teams` and the approver(s) in `settings.json`.

### Phase 2 — Event Hubs (`azure-bicep-iac`)

```bash
az ad sp show --id 0bf30f3b-4a52-48df-9a82-234910c4a086 --query id -o tsv
```

```bash
az ad signed-in-user show --query id -o tsv
```

Put both IDs in `bicep/eventhubs.dev.bicepparam`, then:

```bash
az group create --name rg-sapteams-dev --location westeurope
```

```bash
az deployment group what-if --resource-group rg-sapteams-dev --parameters examples/graph-teams-approvals/bicep/eventhubs.dev.bicepparam
```

```bash
az deployment group create --resource-group rg-sapteams-dev --parameters examples/graph-teams-approvals/bicep/eventhubs.dev.bicepparam
```

### Phase 3 — Subscription

Get a token as yourself (an admin who is a member of the team), generate a client state, fill `<team-id>`, `<channel-id>`, `<eventhub-namespace>`, `<primary-domain>`, `<expiration-utc>` (≤ 3 days ahead) and `<client-state>` in a local copy of `graph/subscription-channel-messages.json`, then create it:

```bash
export GRAPH_TOKEN=$(python3 examples/graph-teams-approvals/scripts/get_token.py --tenant <tenant-id> --client-id <app-client-id>)
```

```bash
export CLIENT_STATE=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
```

```bash
curl -s -X POST https://graph.microsoft.com/v1.0/subscriptions -H "Authorization: Bearer $GRAPH_TOKEN" -H "Content-Type: application/json" -d @subscription.local.json
```

Keep the returned subscription `id`. Renew before expiry with `PATCH /v1.0/subscriptions/{id}` and a new `expirationDateTime`.

### Phase 4 — Run the scenario

1. Start the consumer (as the user with *Data Receiver*): `pip install azure-eventhub azure-identity`, then run `scripts/consume.py` with the namespace, subscription ID, approvers and notifier.
2. Sign in as `svc-sap-teams` (`get_token.py`) and post the card with `scripts/post_card.py` (real Fiori link).
3. In Teams, reply in the card thread as described in the test cases below and watch the consumer output.

## 6. Runtime test cases

| ID | Test | Expected result |
| --- | --- | --- |
| TC-01 | Post the card as `svc-sap-teams` | 201; card shows supplier, amount, company code, requester and **Open in SAP Fiori** |
| TC-02 | Post with a token lacking `ChannelMessage.Send` | 403 from Graph |
| TC-03 | Create the subscription | 201; Event Hubs receives the validation message and the consumer ignores it |
| TC-04 | Approver replies `APPROVE` | Within ~1 minute: `{"status":"approved","po":"4500001234",…}` |
| TC-05 | Post a second card; approver replies `REJECT price above contract` | `rejected` with the reason |
| TC-06 | Approver replies `Reject` (no reason) | `invalid` — nothing sent to SAP |
| TC-07 | Non-approver replies `APPROVE` | `unauthorized` |
| TC-08 | Second decision on an already decided PO | `duplicate` |
| TC-09 | Ordinary chat in the thread / new top-level post | Ignored |
| TC-10 | Remove the Graph Change Tracking role from the hub, reply again | No events arrive (proves RBAC is what authorizes delivery); restore the role |

**Acceptance:** ST-01…ST-15 pass in strict mode and TC-01…TC-10 pass.

## 7. Production notes

- Replace the delegated listener with an **application** listener using **resource-specific consent** (`ChannelMessage.Read.Group`) so the app only reads the teams where it's installed; run the consumer in Azure Functions / Container Apps with a managed identity (*Data Receiver*).
- Renew subscriptions automatically and handle `reauthorizationRequired` / `subscriptionRemoved` lifecycle events.
- Keep the service account's password in a vault, with MFA exclusions or certificate-based auth decided by your identity team; or replace the posting step with a bot (proactive messages) for real Approve/Reject buttons.
- Send the decision to SAP with the `sap-api-integration` skill (e.g. release the purchase order through an API behind API Management) and post the outcome back to the thread.
- Don't use Teams as a log: post only messages people need to act on.

## 8. Cleanup

```bash
curl -s -X DELETE https://graph.microsoft.com/v1.0/subscriptions/<subscription-id> -H "Authorization: Bearer $GRAPH_TOKEN"
```

```bash
az group delete --name rg-sapteams-dev
```

(Only if nothing else lives in the resource group — irreversible.) Remove the app registration and test team if no longer needed.

## 9. Results log

| ID | Date | Result | Notes |
| --- | --- | --- | --- |
| UT-01…UT-14 | 2026-11-05 | Pass | Offline, realistic Graph payloads |
| ST-01…ST-15 | 2026-11-05 | Pass | Static checks, design mode (placeholders pending); 6/6 injected faults detected |
| TC-01…TC-10 | | Not run | Requires a Microsoft 365 tenant with Teams and an Azure subscription |
