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
| SAP itself (ABAP) must call a model, e.g. summarise a document in a Fiori app or classify a free-text field | **Microsoft AI SDK for SAP ABAP** / ABAP SDK for Azure calling Azure OpenAI | Runs in the SAP system. The AI SDK targets **Azure OpenAI only** and documents old API versions (`2022-12-01`, `2023-03-15-preview`); confirm it works with current deployments, or call the current Azure OpenAI REST API through the ABAP SDK for Azure. Prefer Entra ID over keys; keep any secret in the SAP secure store, never in code. SAP release support isn't documented on the intro page: check before promising it. |
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
2. In APIM, create an MCP server from that REST API and select only the operations the agent needs: `templates/bicep/apim-mcp-server.bicep` (API version `2025-09-01-preview`, one `apis/tools` resource per operation) with the MCP-scope policy `templates/apim/mcp-server-policy.xml`, or in the portal **APIs → MCP servers → Expose an API as an MCP server**. Prefer a small **read-only facade API** with narrow, well-described operations over the generated OData API. Worked example with tests: `examples/foundry-sap-po-agent/`. Limits to state to the user:
   - APIM MCP servers built from REST APIs expose **tools only**, not MCP resources or prompts.
   - Only HTTP APIs can be exposed; tiers: Developer, Basic, Basic v2, Standard, Standard v2, Premium, Premium v2; not in workspaces.
   - If global diagnostics log the frontend response body, set its payload bytes to 0, and never read `context.Response.Body` in MCP policies: both break MCP streaming.
3. Add the MCP endpoint (or the OpenAPI document of the same API) as a tool:
   - **Foundry** (`mcp` tool with `server_label` and `server_url`; remote endpoints only):
     - Store credentials in a **project connection**, never in code. Auth types: `none`, `custom-keys`, `agentic-identity` (the agent's Entra identity), `project-managed-identity`, `oauth2`, and `user-entra-token` (the caller's Entra token passed through). For SAP data use `user-entra-token` or OAuth identity passthrough, so APIM can apply principal propagation.
     - `require_approval` defaults to `always`. Keep it on for write tools, for example `{"never": ["get_purchase_order_status"]}` to skip approval only for named read tools. The client answers each `mcp_approval_request` with an `mcp_approval_response` in the same conversation.
     - **Always set `allowed_tools`**: omitting it or passing `[]` allows every tool the server exposes.
     - Private MCP endpoints need the Standard agent setup with private networking (BYO VNet); Basic setup supports public endpoints only.
     - Non-streaming MCP calls time out after 100 seconds: SAP calls that can take longer need background mode (preview) or an asynchronous pattern.
     - "Invalid tool schema" errors often come from `anyOf`/`allOf` or multi-type parameters, which generated OData → OpenAPI schemas often contain. Simplify the operation schemas in APIM before exposing them.
     - A Foundry **toolbox** can bundle tools behind one MCP-compatible endpoint (preview).
   - **Copilot Studio**: Tools → Add a tool → New tool → **Model Context Protocol** (wizard), or a custom connector imported from OpenAPI with `x-ms-agentic-protocol: mcp-streamable-1.0`.
     - Transport: **streamable HTTP only**; SSE isn't supported.
     - Auth: none, API key (header or query), or OAuth 2.0 (dynamic discovery, dynamic, or manual with the Entra app registration). Use OAuth 2.0 with Entra ID against APIM.
     - The server description decides when the orchestrator calls it: write it carefully.
     - Power Platform **data policies (DLP)** on connectors also govern MCP servers: put the SAP MCP connector in the right group.
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
- **Cost and limits.** If Azure OpenAI or Foundry models sit behind APIM, use the AI gateway: `llm-token-limit` (tokens per minute or quota per consumer), `llm-emit-token-metric` (token usage by app or agent), `llm-semantic-cache-lookup` / `llm-semantic-cache-store` (needs Azure Managed Redis or another RediSearch-compatible cache), `llm-content-safety` (Azure AI Content Safety), and backends with load balancing and circuit breaker. Tier support varies per policy: check the policy reference. Apply normal `rate-limit-by-key` on the SAP tools to protect SAP Gateway work processes.
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
- Connect a Foundry agent to an MCP server: https://learn.microsoft.com/azure/foundry/agents/how-to/tools/model-context-protocol
- AI gateway in API Management: https://learn.microsoft.com/azure/api-management/genai-gateway-capabilities
- MCP servers in API Management: https://learn.microsoft.com/azure/api-management/mcp-server-overview
- Expose a REST API in API Management as an MCP server: https://learn.microsoft.com/azure/api-management/export-rest-mcp-server
- Expose and govern an existing MCP server: https://learn.microsoft.com/azure/api-management/expose-existing-mcp-server
- Microsoft AI SDK for SAP ABAP: https://microsoft.github.io/aisdkforsapabap/docs/intro
- ABAP SDK for Azure: https://github.com/microsoft/ABAP-SDK-for-Azure
- Joule and Microsoft 365 Copilot (SAP): https://www.sap.com/products/artificial-intelligence/joule-joule-and-microsoft-365-copilot.html
