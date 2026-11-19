# Test case: AI agent over SAP purchase orders (Microsoft Foundry + API Management MCP)

A complete, reproducible test of the `sap-ai-agents` pattern: a **Microsoft Foundry** prompt agent answers questions about SAP purchase orders through two **read-only MCP tools**. The tools are operations of a small facade API in **Azure API Management** over the standard SAP API **`API_PURCHASEORDER_PROCESS_SRV`** (OData v2), exposed by APIM as an **MCP server** and protected with **Microsoft Entra ID**. The same MCP server works in Copilot Studio, GitHub Copilot, Claude or Codex.

Skills involved: `sap-ai-agents`, `sap-api-integration`, `azure-auth-entra`, `azure-bicep-iac`.

| Option | Backend | What it tests | Needs |
| --- | --- | --- | --- |
| **A — sandbox** (`authMode = sandbox`) | SAP Business Accelerator Hub sandbox (`sandbox.api.sap.com`) | Entra ID, MCP server, tool calls, input validation, rate limits, agent evaluation | Free api.sap.com account (API key) — **no own SAP system** |
| **B — own S/4HANA** (`authMode = s4hana`) | Your S/4HANA dev system through SAP Gateway | Everything in A against your data and a display-only technical user | S/4HANA dev, `API_PURCHASEORDER_PROCESS_SRV` active, private network path from APIM |

> **Status:** static checks pass (`tests/validate_example.py`) and the runtime test script passes against a local mock of the APIM MCP endpoint (11 of 11). Nothing has run yet against a real APIM instance, Foundry project or SAP backend: record the results at the end when you do.

> **Before you build:** SAP has announced the deprecation of `API_PURCHASEORDER_PROCESS_SRV` in **S/4HANA Cloud Public Edition** (SAP Note / KBA 3502308). It remains the classic API on-premises and in private cloud. For public cloud, check the successor OData v4 purchase order API in the Business Accelerator Hub and adapt the facade policy's paths and `$select`.

## 1. Architecture

```
User ─► Foundry agent (prompt agent, model deployment)
          MCP tool: server_label sap-purchase-orders, allowed_tools = 2 tools,
                    require_approval {"never": [read-only tools]}, project connection (Entra ID)
        ─► Azure API Management
             MCP server "sap-po-mcp"  (templates/bicep/apim-mcp-server.bicep)
               policy: validate-azure-ad-token (role PurchaseOrder.Read) → rate limit per caller → trace
             tool → operation of REST API "sap-po-tools" (facade, OpenAPI 3.0, GET only)
               policy: token + role again → 405 for non-GET → validate inputs → rewrite to OData with
                       $select / $filter / $top ≤ 20 → drop client token → SAP auth (API key | technical user)
        ─► SAP OData API_PURCHASEORDER_PROCESS_SRV (TLS validated)
```

| Tool | Facade operation | OData request |
| --- | --- | --- |
| `get_purchase_order_status` | `GET /purchase-orders/{purchaseOrder}` | `A_PurchaseOrder('<po>')?$select=…` |
| `list_supplier_purchase_orders` | `GET /suppliers/{supplier}/purchase-orders?top=n` | `A_PurchaseOrder?$filter=Supplier eq '<s>'&$orderby=PurchaseOrderDate desc&$top=n&$select=…` |

Why a facade instead of exposing the generated OData API: narrow, well-described tools; inputs validated before SAP; no `anyOf`/`allOf` schemas (they cause "invalid tool schema" in Foundry); only the fields the agent needs.

## 2. Files

| File | Purpose |
| --- | --- |
| `config/settings.example.json` | Non-secret values. Copy to `settings.json` (ignored by Git). |
| `../../templates/bicep/apim-sap-odata.bicep` | APIM, Key Vault named values, SAP backend (from the `sap-odata-apim` test case). |
| `bicep/apim.sandbox.dev.bicepparam`, `bicep/apim.s4hana.dev.bicepparam` | Parameters for that template, pointing at `API_PURCHASEORDER_PROCESS_SRV`. |
| `bicep/po-tools.bicep` + `po-tools.*.dev.bicepparam` | Imports the facade API with its policy and creates the MCP server and tools. |
| `../../templates/bicep/apim-mcp-server.bicep` | Reusable: any APIM REST API → MCP server with selected operations as tools. |
| `../../templates/apim/mcp-server-policy.xml` | Reusable MCP-server-scope policy: Entra ID + app role, per-caller rate limit, trace. |
| `apim/po-tools.openapi.json` | The facade API (OpenAPI 3.0): tool names, descriptions and input schemas. |
| `apim/policy-po-tools-sandbox.xml`, `apim/policy-po-tools-s4hana.xml` | Facade API policies for options A and B. |
| `agent/instructions.md` | Agent instructions: read-only, never guess, SAP text is untrusted, refuse writes. |
| `src/po_agent/` | MCP tool definition and its safety rules, a minimal MCP client, evaluation scoring. |
| `scripts/run_agent.py` | Creates the Foundry agent, chats (`--ask`) or runs the evaluation set (`--eval`). |
| `eval/cases.json` | Evaluation set: expected tool calls and arguments, refusal and no-tool cases. |
| `tests/validate_example.py` | Static checks + unit tests (no Azure needed; runs in CI). |
| `tests/run_mcp_tests.py` | Runtime tests against the deployed MCP server (TC-01…TC-11). |

## 3. Static checks

```bash
python3 examples/foundry-sap-po-agent/tests/validate_example.py --verbose
```

| ID | Check |
| --- | --- |
| ST-01 | Facade policies and the MCP policy are valid XML |
| ST-02 / ST-03 | Token validation first (audience + app role) and per-caller rate limit, on both the MCP server and the facade API |
| ST-04 | Facade API is read-only (non-GET → 405) |
| ST-05 / ST-06 | Policy validates the same input patterns as the OpenAPI schema; `top` limited to 1…20 |
| ST-07 | Every operation rewritten to OData with `$select`, client query parameters not copied |
| ST-08 | Client token never sent to SAP; SAP session headers removed; MCP policy keeps the token for the backing API |
| ST-09 | No policy on the MCP path reads the response body (it breaks MCP streaming) |
| ST-10 | Named values and backend exist in `apim-sap-odata.bicep` for each mode |
| ST-11 | OpenAPI 3.0, GET only, described operations and parameters, no `anyOf`/`allOf`/`oneOf` or multi-type parameters |
| ST-12 | Tools map to OpenAPI operations; names match settings and runtime tests; descriptions are specific |
| ST-13 | MCP resources use API version ≥ `2025-09-01-preview`, `type: 'mcp'`, tool `operationId` as a resource ID |
| ST-14 | Foundry MCP tool definition is safe: explicit `allowed_tools`, approval skipped only for read-only tools, project connection |
| ST-15 | Instructions and evaluation set cover read-only behaviour, untrusted data, refusals and no-tool questions |
| ST-16 | Parameter files and loaded files exist; the APIM backend points at the purchase order service |
| ST-17 | Python compiles; runtime script covers TC-01…TC-11 |
| ST-18 | JSON parses; no secrets or tokens |
| ST-19 | (`--strict`) no unfilled `<placeholders>` in settings and parameter files |
| UT | Unit tests, including the runtime script against a local MCP mock |

## 4. Runbook

### Phase 0 — prerequisites

- **Option A:** sign in at api.sap.com, open the purchase order API (`API_PURCHASEORDER_PROCESS_SRV`), copy your **API key**, and note a purchase order and a supplier number that exist in the sandbox (use *Try out*).
- **Option B (SAP Basis):** activate `API_PURCHASEORDER_PROCESS_SRV` in `/IWFND/MAINT_SERVICE`; create a technical user with **display-only** purchase order authorizations for the test company code; test with `/IWFND/GW_CLIENT`. Network: APIM must reach SAP Gateway privately.
- **Foundry:** a Foundry project with a model deployment that supports the MCP tool in your region (check *Best practices for using tools* on Microsoft Learn), and the Python packages `azure-ai-projects`, `azure-identity` and `openai` (latest).
- Copy `config/settings.example.json` to `config/settings.json` and fill it in.

### Phase 1 — Entra ID (`azure-auth-entra`)

1. App registration **`sap-po-agent`** (the API): Application ID URI `api://sap-po-agent`; app role **`PurchaseOrder.Read`** (members: users/groups and applications).
2. *Expose an API*: add the Azure CLI (`04b07795-8ddb-461a-bbee-02f9e1bf7b46`) as an authorized client so testers can get tokens with `az`.
3. Assign `PurchaseOrder.Read` to the reader test user; keep one test user without the role (TC-02).

### Phase 2 — Key Vault secret

```bash
az keyvault secret set --vault-name <key-vault-name> --name sap-sandbox-apikey --value "<paste interactively>"   # option A
az keyvault secret set --vault-name <key-vault-name> --name sap-odata-password --value "<paste interactively>"   # option B
```

Prefer entering the value from a prompt or a file you delete afterwards, so it doesn't stay in shell history.

### Phase 3 — APIM and SAP backend

Preview first, then deploy (Developer tier can take 30+ minutes):

```bash
az deployment group what-if --resource-group rg-sappo-dev --parameters examples/foundry-sap-po-agent/bicep/apim.sandbox.dev.bicepparam
az deployment group create  --resource-group rg-sappo-dev --parameters examples/foundry-sap-po-agent/bicep/apim.sandbox.dev.bicepparam
```

### Phase 4 — facade API and MCP server

```bash
az deployment group what-if --resource-group rg-sappo-dev --parameters examples/foundry-sap-po-agent/bicep/po-tools.sandbox.dev.bicepparam
az deployment group create  --resource-group rg-sappo-dev --parameters examples/foundry-sap-po-agent/bicep/po-tools.sandbox.dev.bicepparam \
  --query properties.outputs
```

- Copy `mcpServerUrl` from the outputs into `settings.json` (`mcp.serverUrl`) and compare it with the **Server URL** in the portal (*APIs → MCP servers*).
- If global diagnostics log the frontend response body, set *Number of payload bytes to log* for Frontend Response to **0**; otherwise MCP streaming breaks.
- Run the runtime tests (section 5) before attaching any agent.

### Phase 5 — Foundry project connection and agent

1. In the Foundry project, create a **project connection** for the MCP server (name = `foundry.mcpConnectionName`). Use **`user-entra-token`** (the caller's Entra token is passed through) so APIM sees the real user. The token's audience must be `api://sap-po-agent`; check the connection settings on Microsoft Learn (*MCP server authentication*, *user delegation*).
2. Chat once, then run the evaluation set:

```bash
python3 examples/foundry-sap-po-agent/scripts/run_agent.py --ask "What is the status of purchase order <po>?"
python3 examples/foundry-sap-po-agent/scripts/run_agent.py --eval
```

The script creates an agent version and deletes it at the end (`--keep` to keep it). Read-only tools skip approval; any other tool request is denied in `--eval` and asked interactively in `--ask`.

3. Optional: publish the agent to Microsoft 365 Copilot and Teams from Foundry, or add the same MCP server to a Copilot Studio agent (*Tools → Add a tool → New tool → Model Context Protocol*, OAuth 2.0 with Entra ID; streamable transport only). Power Platform data policies also govern that MCP connector.

## 5. Runtime test cases

```bash
export TOKEN_READER=$(az account get-access-token --resource api://sap-po-agent --query accessToken -o tsv)
export TOKEN_NOROLE=<token of the test user without the role>
python3 examples/foundry-sap-po-agent/tests/run_mcp_tests.py --rate-limit
```

| ID | Test | Expected |
| --- | --- | --- |
| TC-01 | MCP `initialize` without a token | 401 |
| TC-02 | Token without `PurchaseOrder.Read` | 401 (or 403) |
| TC-03 | `initialize` with the reader token | 200, session established |
| TC-04 | `tools/list` | Exactly `get_purchase_order_status` and `list_supplier_purchase_orders` |
| TC-05 | Status of the test purchase order | Result contains the purchase order number |
| TC-06 | Injection-like purchase order number (`45' or 1 eq 1`) | Rejected (400 from the facade policy) |
| TC-07 | Supplier list with `top = 3` | At most 3 rows |
| TC-08 | `top = 50` | Rejected (maximum 20) |
| TC-09 | Unknown tool `delete_purchase_order` | Error |
| TC-10 | `POST` on the facade API | 405 (or 404) |
| TC-11 | 35 calls in a burst | 429 seen |

Also check: APIM traces show `caller-oid` and `caller-app`; SAP Gateway logs (option B) show only GET requests from the technical user; Foundry run steps show the MCP calls.

**Open point to verify on the first real run:** whether a tool call through the MCP server forwards the caller's `Authorization` header to the facade API, whose policy validates it again. If tool calls fail with 401 while TC-03 passes, follow *Expose a REST API in API Management as an MCP server → Troubleshooting* on Microsoft Learn and record the fix here.

**Acceptance:** ST and UT checks pass in strict mode, TC-01…TC-11 pass, and `run_agent.py --eval` passes EV-01…EV-06.

## 6. Production notes

- Replace the technical user with **SAP principal propagation** so each user sees only what their SAP authorizations allow (`azure-auth-entra`); the agent must never see more than the user asking.
- Write tools (for example, releasing a purchase order) go in a **separate** facade API and MCP server, with their own app role, CSRF handling (`templates/apim/sap-odata-csrf-policy.xml`) and **human approval** (`require_approval` stays `always` for them).
- Private networking: APIM in a VNet, Foundry Standard agent setup with private networking if the MCP endpoint is private.
- Production APIM tier with SLA; Defender for APIs; keep the evaluation set in CI for prompt and model changes.

## 7. Cost control and cleanup

- The APIM Developer tier and model deployments are billed while they exist; delete them after the test.
- `run_agent.py` deletes the agent version unless you pass `--keep`.
- Delete the test resource group only when nothing else lives in it (irreversible): `az group delete --name rg-sappo-dev`.

## 8. Results log

| ID | Date | Result | Notes |
| --- | --- | --- | --- |
| ST-01…ST-18, UT | 2026-11-19 | Pass | Static checks and 11 unit tests, design mode (placeholders pending) |
| Runtime script vs mock | 2026-11-19 | 11 pass | Local mock of the APIM MCP endpoint; validates the test script, not APIM |
| Bicep compile | 2026-11-19 | Pass | `po-tools.bicep`, MCP template and parameter files, Bicep CLI 0.49.2, no warnings |
| TC-01…TC-11 | | Not run | Requires APIM, Entra ID app registration and SAP sandbox or S/4HANA |
| EV-01…EV-06 | | Not run | Requires a Foundry project and model deployment |
