# Getting started

This repository is an agent for Microsoft Azure and SAP integration. It works with [Claude Code](https://code.claude.com) and [OpenAI Codex](https://developers.openai.com/codex).

## 1. Prerequisites

- Claude Code or OpenAI Codex (CLI, app or IDE extension).
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
cd sap-azure-agent
```

### With Claude Code

```bash
claude
```

Claude Code loads automatically:

- `CLAUDE.md` → imports `AGENTS.md` — the agent's instructions and rules.
- `.claude/skills/` (symlink to `.agents/skills/`) — step-by-step skills (Azure Data Factory, SAP → Azure pipelines, SAP CDC incremental replication, Microsoft Entra ID authentication, Bicep infrastructure as code, Microsoft Fabric, SAP API integration, Microsoft Graph, Data Factory CI/CD).
- `.claude/agents/` — specialized subagents (Azure architect, SAP integration expert).
- `.mcp.json` — MCP servers: **Microsoft Learn** (official docs search) and **Azure** (acts on your subscription with your `az login` credentials). Approve them when Claude Code asks.

### With OpenAI Codex

```bash
codex
```

Codex loads automatically:

- `AGENTS.md` — the same instructions and rules.
- `.agents/skills/` — the same skills (Agent Skills format).
- `.codex/config.toml` — the same MCP servers. Codex only reads project configuration for **trusted** projects: trust the folder when Codex asks. If your Codex version does not load project MCP servers, add them to `~/.codex/config.toml` or run:

```bash
codex mcp add microsoft-learn --url https://learn.microsoft.com/api/mcp
```

```bash
codex mcp add azure -- npx -y @azure/mcp@latest server start
```

The specialist roles in `.claude/agents/` are plain Markdown: in Codex, ask it to "act as the azure-architect role" and it follows that file.

### Windows note

`.claude/skills` is a symbolic link. On Windows, enable symlinks before cloning (Developer Mode plus `git config --global core.symlinks true`); otherwise Claude Code will not find the skills.

## 3. Try it

- "Design an architecture to load SAP S/4HANA sales data into Fabric daily."
- "Create the ADF linked services and pipeline to copy table MARA to ADLS."
- "Preview and deploy `templates/bicep/params/data-factory.dev.bicepparam` into resource group rg-data-dev."
- "What changed in the SAP CDC connector? Check Microsoft Learn."

## 4. Security

- Never commit secrets. Store them in Azure Key Vault; templates reference Key Vault secrets and managed identities.
- The agent asks for confirmation before creating or deleting billable Azure resources.
