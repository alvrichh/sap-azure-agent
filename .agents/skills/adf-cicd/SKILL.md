---
name: adf-cicd
description: Set up continuous integration and delivery for Azure Data Factory — Git integration on the dev factory only, automated publish with the @microsoft/azure-data-factory-utilities npm package (validate + export ARM template), environment parameterization, trigger stop/start with the pre/post-deployment script, and deployment to test and production with GitHub Actions (OIDC) or Azure DevOps.
---

# CI/CD for Azure Data Factory

Use with `azure-data-factory` (authoring), `azure-bicep-iac` (the factory itself is infrastructure) and `azure-auth-entra` (OIDC identities). Verify current package and script behaviour on Microsoft Learn ("Automated publishing for CI/CD", "Sample pre- and post-deployment script").

## 1. Operating model

```
feature branch ──PR──► main (collaboration branch, dev factory connected to Git)
                          │ CI: npm validate + export ARM template  (no "Publish" button, no adf_publish)
                          ▼
                     artifact ──► deploy TEST ──(approval)──► deploy PROD
                                   stop triggers → ARM deployment → start triggers + cleanup
```

- **Only the dev factory is connected to Git.** Test and prod are changed exclusively by the pipeline.
- Work in feature branches; protect `main` (PR + review). Debug in the dev factory.
- Two layers, two pipelines: the **factory resource** (identity, networking, Key Vault access) is deployed with Bicep; the **factory content** (pipelines, datasets, linked services, triggers, data flows) with this ARM-template flow.

## 2. Build (CI)

- `build/package.json` (`templates/adf-cicd/package.json`) depends on `@microsoft/azure-data-factory-utilities`; use **Node.js 20**.
- `npm run build validate <rootFolder> <devFactoryId>` = "Validate all".
- `npm run build export <rootFolder> <devFactoryId> ArmTemplate` = validate + generate `ARMTemplateForFactory.json`, `ARMTemplateParametersForFactory.json` and the pre/post-deployment script. It does **not** publish to the live factory.
- Run validate on pull requests to block broken changes; export on `main`.

## 3. Parameterize environments

- Linked service endpoints, Key Vault base URLs, storage URLs, IR references and global parameters must differ per environment → make them ARM parameters.
- Control which properties are parameterized with `arm-template-parameters-definition.json` in the ADF root folder (ADF Studio → Manage → ARM template → Edit parameter configuration).
- Keep one ARM parameter file per environment (`adf/cicd/test.parameters.json`, `adf/cicd/prod.parameters.json`) — **values only, never secrets**: secrets stay in each environment's Key Vault and linked services reference them.
- Integration runtimes must have the **same name and type** in every environment; to share a self-hosted IR, use a dedicated factory and linked (shared) IRs.

## 4. Deploy (CD)

1. Stop triggers: run the exported script with `-predeployment $true -deleteDeployment $false` (prefer `PrePostDeploymentScript.Ver2.ps1`, which only stops triggers that changed). Use **PowerShell Core** and current Az modules.
2. ARM deployment of `ARMTemplateForFactory.json` with the environment parameter file and `factoryName` overridden, **Incremental** mode.
3. Restart triggers and delete resources removed from Git: same script with `-predeployment $false -deleteDeployment $true`.

GitHub Actions: `templates/github-actions/adf-cicd.yml` (build → test → production, OIDC login, `environment` protection for approvals). Setup and variables: `templates/adf-cicd/README.md`.
Azure DevOps: same npm commands in a build pipeline (`UseNode@1`, `Npm@1`, publish artifact) and the script in an Azure PowerShell task (pwsh).

## 5. Identities and permissions

- One OIDC identity per environment (federated subjects `repo:<org>/<repo>:environment:test` / `:environment:production`); no client secrets.
- Grant **Data Factory Contributor** on the target factory's resource group (deploys factory child resources and runs the trigger script); nothing at subscription scope.
- The factory's own managed identity keeps its data-plane roles (Storage, Key Vault) — deployed by Bicep, not by this pipeline.

## 6. Checklist

- [ ] Git only on dev; `main` protected; PRs run validate.
- [ ] Environment-specific values parameterized; no secrets in parameter files.
- [ ] Same IR names/types across environments.
- [ ] Triggers stopped/started by the script; deleted resources cleaned up.
- [ ] Production behind an approval gate; OIDC identities scoped per environment.
- [ ] First run tested end-to-end against test before enabling production.

## References (Microsoft Learn)

- CI/CD overview and best practices: https://learn.microsoft.com/azure/data-factory/continuous-integration-delivery
- Automated publishing (npm package): https://learn.microsoft.com/azure/data-factory/continuous-integration-delivery-improvements
- Pre/post-deployment script: https://learn.microsoft.com/azure/data-factory/continuous-integration-delivery-sample-script
- Custom parameters for the ARM template: https://learn.microsoft.com/azure/data-factory/continuous-integration-delivery-resource-manager-custom-parameters
