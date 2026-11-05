# Getting started

This repository is an agent for Microsoft Azure, Microsoft 365 and SAP integration. It works with [Claude Code](https://code.claude.com) and [OpenAI Codex](https://developers.openai.com/codex): both read the same instructions (`AGENTS.md`), the same skills (`.agents/skills/`) and the same MCP servers.

## 1. Prerequisites

| Requirement | Why |
| --- | --- |
| Claude Code **or** OpenAI Codex (CLI, app or IDE extension) | Runs the agent |
| Node.js 20+ | Starts the Azure MCP server (`npx`) and builds Data Factory ARM templates |
| [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), signed in with your own account | The agent acts on Azure with your identity only |
| Access to an Azure subscription / resource group | Deployments and previews (what-if) |
| Optional: network path to SAP (self-hosted IR, on-premises data gateway, VPN/ExpressRoute or VNet peering) | Needed only when you connect a real SAP system |

```bash
az login
```

## 2. Clone the repository

```bash
git clone https://github.com/alvrichh/sap-azure-agent.git
```

```bash
cd sap-azure-agent
```

**Windows:** `.claude/skills` is a symbolic link to `.agents/skills`. Enable symlinks before cloning (Developer Mode plus `git config --global core.symlinks true`); otherwise Claude Code won't find the skills.

## 3. Open it with your agent

### Claude Code

```bash
claude
```

Claude Code loads automatically:

- `CLAUDE.md` → imports `AGENTS.md`: instructions, security rules and conventions.
- `.claude/skills/` (→ `.agents/skills/`): the nine skills listed below.
- `.claude/agents/`: subagents `azure-architect` and `sap-integration-expert`.
- `.mcp.json`: MCP servers `microsoft-learn` and `azure`. Approve them when asked.

### OpenAI Codex

```bash
codex
```

Codex loads automatically:

- `AGENTS.md`: the same instructions.
- `.agents/skills/`: the same skills.
- `.codex/config.toml`: the same MCP servers, **only if you trust the project** when Codex asks.

If your Codex version doesn't load project MCP servers, add them once:

```bash
codex mcp add microsoft-learn --url https://learn.microsoft.com/api/mcp
```

```bash
codex mcp add azure -- npx -y @azure/mcp@latest server start
```

The specialist roles in `.claude/agents/` are plain Markdown: in Codex, ask it to "act as the azure-architect role" and it follows that file.

### Check that everything loaded

Ask the agent:

- "Which skills do you have in this repository?" → it should list the nine skills below.
- "Search Microsoft Learn for the SAP CDC connector." → confirms the `microsoft-learn` MCP server.
- "List my Azure resource groups." → confirms the `azure` MCP server and your `az login`.

## 4. Skills and what to ask

You don't need to name a skill: describe the outcome and the agent picks it. The prompts below are examples.

### Data integration

| Skill | What it does | Try asking |
| --- | --- | --- |
| [`azure-data-factory`](../.agents/skills/azure-data-factory/SKILL.md) | Designs and builds ADF pipelines, datasets, linked services, integration runtimes, triggers and data flows. | "Build a parameterized ADF pipeline that copies daily files from SFTP to ADLS with retries and alerts." |
| [`adf-sap-pipeline`](../.agents/skills/adf-sap-pipeline/SKILL.md) | Chooses the SAP connector (SAP Table, SAP CDC, BW Open Hub, HANA, OData), lists prerequisites and builds SAP → Azure pipelines. | "Our S/4HANA is on-premises: what do we need to copy table MARA to the data lake, and create the ADF JSON." |
| [`sap-cdc-incremental`](../.agents/skills/sap-cdc-incremental/SKILL.md) | Delta replication via ODP into Delta tables: contexts, run modes, keys, checkpoint keys, partitioning, ODQMON operations. | "Replicate extractor 2LIS_11_VAITM and two CDS views incrementally into Delta, full load first." |
| [`adf-cicd`](../.agents/skills/adf-cicd/SKILL.md) | CI/CD for Data Factory: validate/export with the ADF npm package, environment parameters, trigger handling, test → prod deployment. | "Set up GitHub Actions to deploy our dev Data Factory to test and production with approval." |

### Analytics

| Skill | What it does | Try asking |
| --- | --- | --- |
| [`microsoft-fabric`](../.agents/skills/microsoft-fabric/SKILL.md) | Chooses the SAP → Fabric path (ADF + OneLake shortcuts, Fabric connectors, Mirroring via SAP Datasphere, partners), capacity, workspaces, lakehouses, Direct Lake. | "We have SAP Datasphere: compare mirroring with our ADF SAP CDC pipeline for Fabric, and set up the winner." |

### Applications and Microsoft 365

| Skill | What it does | Try asking |
| --- | --- | --- |
| [`sap-api-integration`](../.agents/skills/sap-api-integration/SKILL.md) | SAP OData behind API Management, RFC/BAPI/IDoc with Logic Apps, Power Platform, SAP BTP / Integration Suite, connectivity options. | "Expose API_BUSINESS_PARTNER through API Management with Entra ID and CSRF handling." |
| [`microsoft-graph`](../.agents/skills/microsoft-graph/SKILL.md) | Teams, Outlook, SharePoint and OneDrive via Graph, change notifications, least-privilege permissions, Copilot connectors for SAP data. | "Make SAP material master data searchable in Microsoft 365 Copilot, respecting SAP authorizations." |

### Platform foundations

| Skill | What it does | Try asking |
| --- | --- | --- |
| [`azure-auth-entra`](../.agents/skills/azure-auth-entra/SKILL.md) | Managed identities, OIDC for CI/CD, RBAC, Key Vault access, Entra ID ↔ SAP SSO, provisioning, principal propagation. | "Let GitHub Actions deploy to rg-data-dev without any client secret." |
| [`azure-bicep-iac`](../.agents/skills/azure-bicep-iac/SKILL.md) | Bicep authoring, parameter files per environment, linter, what-if, deployment stacks, CI/CD. | "Preview and deploy templates/bicep/params/data-factory.dev.bicepparam into rg-data-dev." |

### Specialist roles

| Role | Ask for it when | Try asking |
| --- | --- | --- |
| [`azure-architect`](../.claude/agents/azure-architect.md) | You need a design before building | "As the azure-architect, design SAP-to-Fabric analytics for 2 TB/day with private networking." |
| [`sap-integration-expert`](../.claude/agents/sap-integration-expert.md) | You need the SAP-side prerequisites or trade-offs | "As the sap-integration-expert, list what our Basis team must prepare for ODP extraction." |

## 5. A typical end-to-end journey

1. **Design**: "Design an architecture to bring S/4HANA sales and finance data into Fabric hourly" (`azure-architect`, `microsoft-fabric`).
2. **Identity**: "Create the identities and roles for the factory and for GitHub Actions" (`azure-auth-entra`).
3. **Infrastructure**: "Preview and deploy the data factory, storage and Key Vault for dev" (`azure-bicep-iac`).
4. **SAP prerequisites**: "What does SAP Basis need to set up for ODP and the technical user?" (`sap-integration-expert`, `sap-cdc-incremental`).
5. **Pipelines**: "Create the SAP CDC pipeline and control file for these objects" (`sap-cdc-incremental`).
6. **Analytics**: "Create the OneLake shortcuts and a Direct Lake model" (`microsoft-fabric`).
7. **Release**: "Set up CI/CD from dev to test and production" (`adf-cicd`).
8. **Extend**: "Post an approval card in Teams for large purchase orders" (`sap-api-integration`, `microsoft-graph`).

## 6. Templates

Every skill points to ready-to-adapt templates under `templates/` (Bicep, ADF JSON, Fabric, API Management, Graph, GitHub Actions). Replace each `<placeholder>`; none of them contains secrets. Index: [templates/README.md](../templates/README.md).

## 7. Security

- Never commit secrets. Store them in Azure Key Vault; templates reference Key Vault secrets and managed identities.
- The agent uses only your own Azure login, previews changes with what-if, and asks for confirmation before creating, changing or deleting billable resources.
- Production changes go through CI/CD with approvals, not from a laptop.

## 8. Troubleshooting

| Symptom | Fix |
| --- | --- |
| Claude Code doesn't list the skills | Check that `.claude/skills` is a symlink (Windows: enable symlinks and re-clone). |
| Codex doesn't see the MCP servers | Trust the project, or add them with `codex mcp add` (section 3). |
| Azure MCP tools fail with auth errors | Run `az login` again and check the active subscription with `az account show`. |
| Microsoft Learn answers seem outdated | Ask the agent to fetch the specific Learn page instead of relying on search results. |
