---
name: azure-bicep-iac
description: Author, validate and deploy Azure infrastructure as code with Bicep — file structure, parameters files (.bicepparam), modules and Azure Verified Modules, linter configuration, what-if previews, deployment stacks, and CI/CD with GitHub Actions using OIDC. Use whenever Azure resources must be created or changed.
---

# Azure infrastructure as code with Bicep

Rule: **every Azure resource this agent creates is described in Bicep**, previewed with what-if, and deployed with the user's own identity (or CI/CD via OIDC). Use the `microsoft-learn` MCP server to confirm resource API versions and property names; use the `azure` MCP server (`bicepschema`) to inspect resource schemas.

## 1. Repository layout

```
templates/bicep/
├── bicepconfig.json              # linter rules (security rules set to error)
├── <workload>.bicep              # entry points, resource-group scope by default
├── modules/<name>.bicep          # reusable local modules (when an entry point grows)
└── params/<workload>.<env>.bicepparam   # one parameters file per environment
```

- One entry point per workload (e.g. `data-factory.bicep`), one `.bicepparam` per environment (`dev`, `prod`).
- `.bicepparam` files start with `using '../<workload>.bicep'` and contain **no secrets**.

## 2. Authoring rules

- **Parameters**: `@description` on every param; `@allowed`, `@minLength`/`@maxLength` where useful; sensible defaults only for non-environment values (`location = resourceGroup().location`).
- **Secrets**: never as defaults or outputs. If a template must receive one, use `@secure()` and pass it from Key Vault (`getSecret()` in `.bicepparam` or `az keyvault secret show` in CI). Prefer managed identities so no secret is needed at all.
- **Names**: deterministic and globally unique where required: `take('st${baseName}${uniqueString(resourceGroup().id)}', 24)`.
- **Tags**: a `tags` object param applied to every resource (environment, workload, owner, cost center).
- **Security defaults**: TLS 1.2+, no public blob access, HTTPS only, Key Vault in RBAC mode with soft delete; private endpoints / managed VNets for production SAP data.
- **RBAC in templates**: role assignments with `guid(scope, principal, role)` names, `principalType: 'ServicePrincipal'` for managed identities, narrowest data-plane role. The deployer then needs *Owner*, *User Access Administrator* or *Role Based Access Control Administrator* — say so to the user.
- **References**: use symbolic references (`storage.id`, `parent:`) instead of `resourceId()` strings; `existing` for resources owned elsewhere.
- **Outputs**: names and IDs only, each with `@description`.
- **Modules**: extract when a block is reused or a file passes ~200 lines. For common resources consider **Azure Verified Modules** from the public registry (`br/public:avm/res/<provider>/<resource>:<version>`); pin the version and let the `use-recent-module-versions` linter rule flag old ones.

## 3. Validate locally

```bash
az bicep lint --file templates/bicep/data-factory.bicep
```

```bash
az bicep build --file templates/bicep/data-factory.bicep --stdout > /dev/null
```

```bash
az bicep build-params --file templates/bicep/params/data-factory.dev.bicepparam --stdout > /dev/null
```

`templates/bicep/bicepconfig.json` turns security rules (hardcoded URLs, secure defaults, secrets in outputs) into **errors**, so the build fails on them.

## 4. Preview, then deploy (always in this order)

Preview with what-if — shows creates, modifies and deletes without changing anything (some properties may appear as "noise"):

```bash
az deployment group what-if --resource-group <resource-group> --parameters templates/bicep/params/data-factory.dev.bicepparam
```

Deploy (with a `.bicepparam`, do **not** also pass `--template-file`):

```bash
az deployment group create --resource-group <resource-group> --parameters templates/bicep/params/data-factory.dev.bicepparam --confirm-with-what-if
```

Before running either against a user's subscription: show the what-if summary, state the billable resources being created, and get explicit confirmation.

## 5. Lifecycle with deployment stacks (recommended for shared environments)

A deployment stack tracks the resources a template manages, can clean up resources removed from the template, and can block out-of-band changes:

```bash
az stack group create --name <stack-name> --resource-group <resource-group> --parameters templates/bicep/params/data-factory.prod.bicepparam --action-on-unmanage detachAll --deny-settings-mode denyDelete
```

- `--action-on-unmanage`: `detachAll` (safe default), `deleteResources`, or `deleteAll` (also deletes managed resource groups — use with great care).
- `--deny-settings-mode`: `none`, `denyDelete` or `denyWriteAndDelete`. Exclusions: max **five** principals (use groups).
- Never use `--bypass-stack-out-of-sync-error` by default.

## 6. CI/CD with GitHub Actions

`templates/github-actions/bicep-ci.yml`:

- **Pull request** → lint, build, build-params, **what-if** (OIDC identity with *Reader* on the resource group).
- **Merge to main** → deploy through a protected `production` environment (required reviewers).
- Identities and federated credentials: `templates/bicep/github-oidc-identity.bicep` (see the `azure-auth-entra` skill). Subjects needed: `repo:<org>/<repo>:pull_request` and `repo:<org>/<repo>:environment:production`.

## 7. Checklist

- [ ] Linter clean; security rules at error level.
- [ ] One `.bicepparam` per environment; no secrets in any file.
- [ ] Tags on every resource.
- [ ] Least-privilege role assignments; deployer permissions stated.
- [ ] What-if reviewed and confirmed before every deployment.
- [ ] Production deployed through CI/CD with approvals, not from a laptop.

## Templates in this repository

| File | Purpose |
| --- | --- |
| `templates/bicep/bicepconfig.json` | Linter configuration |
| `templates/bicep/data-factory.bicep` | Data factory, ADLS Gen2, Key Vault, role assignments, tags |
| `templates/bicep/params/data-factory.dev.bicepparam` / `.prod.bicepparam` | Environment parameters |
| `templates/bicep/github-oidc-identity.bicep` | CI/CD identity with GitHub OIDC trust |
| `templates/github-actions/bicep-ci.yml` | Lint / what-if / deploy workflow |

## References (Microsoft Learn)

- Bicep parameters files: https://learn.microsoft.com/azure/azure-resource-manager/bicep/parameter-files
- What-if: https://learn.microsoft.com/azure/azure-resource-manager/bicep/deploy-what-if
- Deployment stacks: https://learn.microsoft.com/azure/azure-resource-manager/bicep/deployment-stacks
- Linter and bicepconfig.json: https://learn.microsoft.com/azure/azure-resource-manager/bicep/bicep-config-linter
- Modules and public registry: https://learn.microsoft.com/azure/azure-resource-manager/bicep/modules
