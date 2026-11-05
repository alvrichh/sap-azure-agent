# Getting started

This repository is an agent for Microsoft Azure and SAP integration, designed to be used with [Claude Code](https://code.claude.com).

## 1. Prerequisites

- Claude Code (CLI, desktop app, IDE extension or web).
- Node.js 20+ (used by the Azure MCP server through `npx`).
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli), logged in with your own account:

```bash
az login
```

- Optional, for SAP connectivity: a self-hosted integration runtime with network access to your SAP system.

## 2. Open the repository with Claude Code

```bash
git clone https://github.com/alvrichh/sap-azure-agent.git
```

```bash
cd sap-azure-agent && claude
```

Claude Code loads automatically:

- `CLAUDE.md` — the agent's instructions and rules.
- `.claude/skills/` — step-by-step skills (Azure Data Factory, SAP → Azure pipelines, SAP CDC incremental replication, Microsoft Entra ID authentication, Bicep infrastructure as code, Microsoft Fabric).
- `.claude/agents/` — specialized subagents (Azure architect, SAP integration expert).
- `.mcp.json` — MCP servers: **Microsoft Learn** (official docs search) and **Azure** (acts on your subscription with your `az login` credentials). Approve them when Claude Code asks.

## 3. Try it

- "Design an architecture to load SAP S/4HANA sales data into Fabric daily."
- "Create the ADF linked services and pipeline to copy table MARA to ADLS."
- "Preview and deploy `templates/bicep/params/data-factory.dev.bicepparam` into resource group rg-data-dev."
- "What changed in the SAP CDC connector? Check Microsoft Learn."

## 4. Security

- Never commit secrets. Store them in Azure Key Vault; templates reference Key Vault secrets and managed identities.
- The agent asks for confirmation before creating or deleting billable Azure resources.
