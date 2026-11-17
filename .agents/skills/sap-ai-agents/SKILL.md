---
name: sap-ai-agents
description: Build AI agents and copilots that read or act on SAP data with Microsoft AI — Microsoft Foundry Agent Service (OpenAPI, MCP and Azure Functions tools), Copilot Studio (SAP OData connector, Power Automate flows, MCP servers), Azure API Management as the governed gateway that exposes SAP OData APIs as MCP tools, the Joule ↔ Microsoft 365 Copilot integration, the Microsoft AI SDK for SAP ABAP, and Logic Apps agent workflows. Use when the user wants a chat, agent or generative AI feature over SAP; for the underlying OData/RFC plumbing use sap-api-integration, for bulk data use adf-sap-pipeline / microsoft-fabric.
---

# AI agents and copilots over SAP

Agents must reach SAP through the same governed APIs as any other client: never give a model a direct SAP connection, a technical super-user or raw table access. Verify product names, preview status, regions and model support with the `microsoft-learn` MCP server before recommending anything: this area changes monthly.

## 1. Pick the pattern

| Need | Recommended pattern | Notes |
| --- | --- | --- |
| Users live in Microsoft 365 and the customer already has SAP Joule | **Joule ↔ Microsoft 365 Copilot** (bi-directional, generally available) | An SAP offering: needs Joule Base or SAP AI Units. Configured on the SAP side; no custom code. Confirm entitlement with the customer's SAP account team. |
| Low-code agent in Teams / Microsoft 365 Copilot, owned by a business or Power Platform team | **Copilot Studio** + SAP OData connector (Premium) or a Power Automate flow, or an **MCP server** added as a tool | Fastest path. Per-user SAP access through Entra ID via APIM (principal propagation). See `examples/powerplatform-sap/` for the connector and ALM side. |
| Pro-code agent with custom logic, evaluation and observability | **Microsoft Foundry Agent Service** with an **OpenAPI tool** (OpenAPI 3.0) or an **MCP tool** pointing at APIM | Use the new Foundry agents: classic agents are deprecated and retire on 31 March 2027. |
| Many agents (Copilot Studio, Foundry, GitHub Copilot, Claude, Codex) must share the same SAP capabilities | **API Management MCP server** built from the SAP OData API already in APIM | One governed endpoint; API operations become MCP tools. |
| SAP itself (ABAP) must call a model, e.g. summarise a document in a Fiori app or classify a free-text field | **Microsoft AI SDK for SAP ABAP** / ABAP SDK for Azure calling Azure OpenAI in Foundry | Runs in the SAP system; secrets in SSF/STRUST or SAP-side secure store, never in code. Check the SDK's supported SAP releases. |
| A deterministic integration flow needs one AI step (validate, extract, classify) | **Logic Apps agent workflows** (Agent action with an Azure OpenAI deployment) next to the SAP built-in connector | Keeps RFC/IDoc handling in `sap-api-integration`; the agent only judges, the workflow acts. |
| Questions over large or historical SAP data (trends, "top 10 suppliers last year") | Replicate first (`sap-cdc-incremental` → `microsoft-fabric`), then ground the agent on Fabric / Azure AI Search | Don't page millions of rows through OData into a prompt. |

## 2. Reference architecture (pro-code and multi-agent)

```
User ─► Teams / Microsoft 365 Copilot / web app
        └─► Copilot Studio agent or Foundry agent
              └─► MCP tool or OpenAPI tool  (Entra ID token)
                    └─► Azure API Management  (MCP server + SAP OData API, AI gateway policies)
                          └─► SAP Gateway / S/4HANA OData  (private network, principal propagation)
```

1. Build and secure the SAP OData API in APIM first, with `templates/bicep/apim-sap-odata.bicep`, `templates/apim/sap-odata-csrf-policy.xml` and `examples/sap-odata-apim/`. The agent work starts only when that API passes its tests.
2. In APIM, create an MCP server from that REST API (**APIs → MCP servers → Expose an API as an MCP server**) and select only the operations the agent needs. Limits to state to the user:
   - APIM MCP servers built from REST APIs expose **tools only**, not MCP resources or prompts.
   - Only HTTP APIs can be exposed, and only in the tiers the feature supports (check Developer, Basic/Basic v2, Standard/Standard v2, Premium/Premium v2 on Microsoft Learn).
   - MCP servers can also be managed with Bicep, ARM, REST, the Azure CLI or Terraform; prefer IaC and verify the resource type and API version before writing it.
3. Add the MCP endpoint (or the OpenAPI document of the same API) as a tool:
   - **Foundry**: MCP tool or OpenAPI tool on the agent; prefer Microsoft Entra authentication when the server supports it. A Foundry **toolbox** can bundle tools behind one MCP-compatible endpoint (preview: check).
   - **Copilot Studio**: Tools → Add a tool → Model Context Protocol, or a custom connector.
4. An existing MCP server (Logic Apps, Functions, a partner server) can also be put behind APIM with **Expose an existing MCP server**, to get the same authentication, IP filtering and rate limits.

## 3. Identity and authorization

- **Who does SAP see?** Decide this before anything else.
  - Read-only, non-sensitive master data (materials, plants): a least-privilege technical user is acceptable.
  - Anything user-specific or any write: **principal propagation**, so SAP enforces the end user's own authorizations (see `azure-auth-entra`). An agent must never be able to do more than the user asking.
- Agent → APIM: Entra ID tokens validated with `validate-azure-ad-token` (audience + app roles). Prefer managed identity / agent identity over API keys or subscription keys alone.
- APIM → model (if APIM also fronts Azure OpenAI): managed identity, no keys.
- Separate app roles for read tools and write tools, so tenants can grant read-only agents.

## 4. Tool design for SAP

- **Narrow, intention-named tools** (`get_purchase_order_status`, `list_open_invoices_for_vendor`) instead of a generic "query any entity set". Each tool maps to one APIM operation with `$select` and a capped `$top`.
- **Read first.** Start with read-only tools. Add write tools (create a sales order, release a PO) only with **human approval**: an approval step in the agent (Foundry MCP approval setting, Copilot Studio confirmation, or an Adaptive Card in Teams) before APIM forwards the call.
- Writes go through the APIM CSRF policy and `If-Match` ETags; use `$batch` only behind a single tool that represents one business transaction.
- Escape user text in OData `$filter` literals (`'` → `''`) in the policy or backend, never in the prompt.
- Write tool descriptions for the model: what it does, required inputs, units, and what it must not be used for. Return compact JSON with the fields the agent needs, not the full OData payload.

## 5. Safety, cost and operations

- **Prompt injection from SAP data.** Free-text fields (order notes, material long texts, vendor names) are untrusted input. Tool results must not be able to trigger write tools without approval.
- **Data protection.** SAP data is business-sensitive: keep model deployments in the required region or data zone, use private endpoints for Foundry, APIM and SAP, and log tool calls (who, which tool, which SAP object) in Application Insights / Log Analytics. Don't log full payloads with personal data.
- **Cost and limits.** If Azure OpenAI or Foundry models sit behind APIM, use the AI gateway policies for per-consumer token limits, token metrics and backend load balancing; confirm the current policy names on Microsoft Learn before writing them. Apply normal `rate-limit-by-key` on the SAP tools to protect SAP Gateway work processes.
- **Evaluation.** Keep a small set of test questions with expected tool calls and answers; rerun them after changing tool descriptions, models or the APIM API.
- **Licensing.** SAP API policy and indirect/digital access apply to agent traffic exactly as to any integration; Joule features need SAP AI entitlements. Flag both to the user.

## 6. Checklist

- [ ] Pattern chosen (Joule, Copilot Studio, Foundry, ABAP SDK, Logic Apps agent, or grounded on replicated data) and the reason stated.
- [ ] SAP OData API in APIM works and is tested before any agent is attached.
- [ ] Identity decided: principal propagation for user-specific data and all writes; technical user only for read-only non-sensitive data.
- [ ] Only the needed operations exposed as tools; read and write tools separated by app role.
- [ ] Write tools require human approval.
- [ ] Private networking, region/data zone, logging and token/rate limits in place.
- [ ] Preview features, tiers, regions and model support verified on Microsoft Learn; SAP licensing flagged.
- [ ] Evaluation set created; templates not validated against a real SAP system yet: test in dev first.

## References (Microsoft Learn and vendors)

- SAP and Microsoft integration scenarios (Azure OpenAI, Copilot, AI SDK): https://learn.microsoft.com/azure/sap/workloads/integration-get-started
- Copilot Studio with SAP: https://learn.microsoft.com/azure/sap/microsoft-ai/copilot-studio/copilot-with-sap-overview
- Add an existing MCP server to a Copilot Studio agent: https://learn.microsoft.com/microsoft-copilot-studio/mcp-add-existing-server-to-agent
- SAP OData connector (Power Platform / Copilot Studio): https://learn.microsoft.com/connectors/sapodata
- Foundry Agent Service tools overview: https://learn.microsoft.com/azure/foundry/agents/concepts/tool-catalog
- Foundry toolbox (preview): https://learn.microsoft.com/azure/foundry/agents/how-to/tools/toolbox
- MCP servers in API Management: https://learn.microsoft.com/azure/api-management/mcp-server-overview
- Expose a REST API in API Management as an MCP server: https://learn.microsoft.com/azure/api-management/export-rest-mcp-server
- Expose and govern an existing MCP server: https://learn.microsoft.com/azure/api-management/expose-existing-mcp-server
- Microsoft AI SDK for SAP ABAP: https://microsoft.github.io/aisdkforsapabap/docs/intro
- ABAP SDK for Azure: https://github.com/microsoft/ABAP-SDK-for-Azure
- Joule and Microsoft 365 Copilot (SAP): https://www.sap.com/products/artificial-intelligence/joule-joule-and-microsoft-365-copilot.html
