# Templates

Reusable, parameterized starting points used by the agent's skills. Every file is listed below, grouped by area, with the skill that explains how to use it.

## Rules

- Replace every `<placeholder>` before use. Local values come from `.env` (copy [`../.env.example`](../.env.example)).
- **No secrets** in any file: passwords and keys live in Azure Key Vault and are referenced (ADF `AzureKeyVaultSecret`, APIM Key Vault-backed named values); prefer managed identities and OIDC.
- Templates are validated for syntax (JSON, XML, YAML) but **not yet deployed end to end** against a real SAP system or Azure subscription: test in dev first.
- Deploy Azure resources with a what-if preview first (see `azure-bicep-iac`).

## Infrastructure — Bicep (`bicep/`)

Skill: [`azure-bicep-iac`](../.agents/skills/azure-bicep-iac/SKILL.md)

| File | What it is | Related skill |
| --- | --- | --- |
| [`bicep/data-factory.bicep`](bicep/data-factory.bicep) | Data factory with system-assigned identity, ADLS Gen2 (`raw` container), Key Vault in RBAC mode, role assignments (Storage Blob Data Contributor, Key Vault Secrets User), tags. | `azure-data-factory` |
| [`bicep/params/data-factory.dev.bicepparam`](bicep/params/data-factory.dev.bicepparam), [`bicep/params/data-factory.prod.bicepparam`](bicep/params/data-factory.prod.bicepparam) | Parameters per environment for `data-factory.bicep`. | `azure-bicep-iac` |
| [`bicep/fabric-capacity.bicep`](bicep/fabric-capacity.bicep) | Microsoft Fabric capacity (F2–F2048) with administrators and tags. | `microsoft-fabric` |
| [`bicep/params/fabric-capacity.dev.bicepparam`](bicep/params/fabric-capacity.dev.bicepparam) | Dev parameters for the Fabric capacity (F2). | `microsoft-fabric` |
| [`bicep/apim-sap-odata.bicep`](bicep/apim-sap-odata.bicep) | API Management for SAP OData: system identity with Key Vault access, named values (Entra ID, SAP, Key Vault-backed secrets), SAP backend with TLS validation; `sandbox` or `s4hana` mode. | `sap-api-integration` |
| [`bicep/github-oidc-identity.bicep`](bicep/github-oidc-identity.bicep) | User-assigned managed identity with a GitHub Actions federated credential (no secrets) and a role on the resource group. | `azure-auth-entra` |
| [`bicep/bicepconfig.json`](bicep/bicepconfig.json) | Linter rules; security rules (hardcoded URLs, secure defaults, secrets in outputs) fail the build. | `azure-bicep-iac` |

```bash
az deployment group what-if --resource-group <resource-group> --parameters templates/bicep/params/data-factory.dev.bicepparam
```

```bash
az deployment group create --resource-group <resource-group> --parameters templates/bicep/params/data-factory.dev.bicepparam
```

## Data Factory — content (`adf/`)

Skills: [`azure-data-factory`](../.agents/skills/azure-data-factory/SKILL.md), [`adf-sap-pipeline`](../.agents/skills/adf-sap-pipeline/SKILL.md), [`sap-cdc-incremental`](../.agents/skills/sap-cdc-incremental/SKILL.md), [`sap-api-integration`](../.agents/skills/sap-api-integration/SKILL.md)

### Linked services

| File | Connector | Notes |
| --- | --- | --- |
| [`adf/linked-services/key-vault.json`](adf/linked-services/key-vault.json) | `AzureKeyVault` | Create first: the other linked services resolve their secrets through it. |
| [`adf/linked-services/adls-gen2.json`](adf/linked-services/adls-gen2.json) | `AzureBlobFS` | ADLS Gen2 with the factory's managed identity. |
| [`adf/linked-services/sap-table.json`](adf/linked-services/sap-table.json) | `SapTable` | RFC table reads through a self-hosted IR (SAP .NET Connector). |
| [`adf/linked-services/sap-cdc.json`](adf/linked-services/sap-cdc.json) | `SapOdp` | SAP CDC / ODP; `subscriberName` uppercase, unique, max 32 characters. |
| [`adf/linked-services/sap-ecc-odata.json`](adf/linked-services/sap-ecc-odata.json) | `SapEcc` | Any SAP Gateway OData service (copy and lookup). |
| [`adf/linked-services/snowflake-v2.json`](adf/linked-services/snowflake-v2.json) | `SnowflakeV2` | Key-pair authentication; private key and passphrase from Key Vault. User needs `USAGE` on the database, read/write on the schema, `CREATE STAGE`. |
| [`adf/linked-services/azure-blob-staging.json`](adf/linked-services/azure-blob-staging.json) | `AzureBlobStorage` | Staging for Snowflake `COPY` with the factory's managed identity; Snowflake reads it through its storage integration (no SAS). |

### Datasets

| File | Type | Parameters |
| --- | --- | --- |
| [`adf/datasets/sap-table.json`](adf/datasets/sap-table.json) | `SapTableResource` | `tableName` |
| [`adf/datasets/sap-cdc.json`](adf/datasets/sap-cdc.json) | `SapOdpResource` | `context`, `objectName` (optional; for previewing objects) |
| [`adf/datasets/sap-ecc-odata.json`](adf/datasets/sap-ecc-odata.json) | `SapEccResource` | `entitySet` |
| [`adf/datasets/adls-parquet.json`](adf/datasets/adls-parquet.json) | `Parquet` | `fileSystem`, `folderPath` |
| [`adf/datasets/adls-json.json`](adf/datasets/adls-json.json) | `Json` | `fileSystem`, `fileName` (control files) |
| [`adf/datasets/snowflake-v2-table.json`](adf/datasets/snowflake-v2-table.json) | `SnowflakeV2Table` | `schema`, `table` (case-sensitive) |

### Pipelines and control files

| File | What it does |
| --- | --- |
| [`adf/pipelines/copy-sap-table-to-adls.json`](adf/pipelines/copy-sap-table-to-adls.json) | Full copy of one SAP table to Parquet in ADLS, partitioned by load date, with retries. |
| [`adf/pipelines/sap-cdc-incremental-to-delta.json`](adf/pipelines/sap-cdc-incremental-to-delta.json) | Metadata-driven SAP CDC: Lookup control file → ForEach → Execute Data Flow per object, with a checkpoint key per object. Requires the data flow `DF_SapCdc_To_Delta` (build it from the ADF gallery template as described in `sap-cdc-incremental`). |
| [`adf/pipelines/copy-adls-parquet-to-snowflake.json`](adf/pipelines/copy-adls-parquet-to-snowflake.json) | Load Parquet from ADLS (e.g. SAP extracts) into a Snowflake table: staged `COPY INTO` through a storage integration, with retries. |
| [`adf/control-files/sap-cdc-objects.json`](adf/control-files/sap-cdc-objects.json) | Example list of SAP objects to replicate: context, object, run mode, keys, partitions, Delta target. |

## Data Factory — CI/CD (`adf-cicd/`, `github-actions/adf-cicd.yml`)

Skill: [`adf-cicd`](../.agents/skills/adf-cicd/SKILL.md) · Setup: [`adf-cicd/README.md`](adf-cicd/README.md)

| File | What it is |
| --- | --- |
| [`adf-cicd/package.json`](adf-cicd/package.json) | Build dependency on `@microsoft/azure-data-factory-utilities` (validate + export ARM template). |
| [`github-actions/adf-cicd.yml`](github-actions/adf-cicd.yml) | Build on PR/main, deploy to test, then production (approval), stopping and restarting triggers. |

## GitHub Actions (`github-actions/`)

Skills: [`azure-bicep-iac`](../.agents/skills/azure-bicep-iac/SKILL.md), [`azure-auth-entra`](../.agents/skills/azure-auth-entra/SKILL.md)

| File | What it is |
| --- | --- |
| [`github-actions/azure-login-oidc.yml`](github-actions/azure-login-oidc.yml) | Minimal example: Azure login with OIDC and a Bicep deployment. |
| [`github-actions/bicep-ci.yml`](github-actions/bicep-ci.yml) | Lint, build and what-if on pull requests; deploy on merge to `main` through a protected environment. |
| [`github-actions/adf-cicd.yml`](github-actions/adf-cicd.yml) | Data Factory CI/CD (see above). |

All workflows use OIDC: store `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` (identifiers, not credentials) and create the identity with `bicep/github-oidc-identity.bicep`.

## Microsoft Fabric (`fabric/`)

Skill: [`microsoft-fabric`](../.agents/skills/microsoft-fabric/SKILL.md) · Usage: [`fabric/README.md`](fabric/README.md)

| File | What it is |
| --- | --- |
| [`fabric/shortcut-adls-delta.json`](fabric/shortcut-adls-delta.json) | Fabric REST body: OneLake shortcut in a lakehouse `Tables` folder pointing to a Delta table in ADLS Gen2 (e.g. SAP CDC output). |

## API Management (`apim/`)

Skill: [`sap-api-integration`](../.agents/skills/sap-api-integration/SKILL.md)

| File | What it is |
| --- | --- |
| [`apim/sap-odata-csrf-policy.xml`](apim/sap-odata-csrf-policy.xml) | Policy for SAP OData APIs: `sap-client`, Key Vault-backed technical user (or swap in principal propagation), X-CSRF-Token fetch before writes. Import with policy format `xml`. |

## Microsoft Graph (`graph/`)

Skill: [`microsoft-graph`](../.agents/skills/microsoft-graph/SKILL.md) · Usage: [`graph/README.md`](graph/README.md)

| File | What it is |
| --- | --- |
| [`graph/sites-selected-grant.json`](graph/sites-selected-grant.json) | Grant an app with `Sites.Selected` access to one SharePoint site. |
| [`graph/subscription-sharepoint-list.json`](graph/subscription-sharepoint-list.json) | Change-notification subscription for a SharePoint list, with lifecycle notifications. |
| [`graph/copilot-connector-connection.json`](graph/copilot-connector-connection.json) | Microsoft 365 Copilot connector connection for SAP material data. |
| [`graph/copilot-connector-schema.json`](graph/copilot-connector-schema.json) | Its schema, with the semantic labels Copilot requires (`title`, `url`, `iconUrl`). |
| [`bicep/logicapp-standard-sap.bicep`](bicep/logicapp-standard-sap.bicep) | Logic App Standard for the SAP built-in connector: WS1, 64-bit, VNet integration, SAP app settings with the password as a Key Vault reference; optional VNet private ports (stateful mode for the SAP trigger and transaction IDs) and extra app settings. Worked examples: `examples/logicapps-sap-rfc/`, `examples/logicapps-sap-idoc/`. |
| [`bicep/eventhubs-graph-notifications.bicep`](bicep/eventhubs-graph-notifications.bicep) | Event Hubs for Graph change notifications without SAS: Graph Change Tracking as Data Sender, consumer as Data Receiver. Worked example: `examples/graph-teams-approvals/`. |

## Typical combinations

| Goal | Templates, in order |
| --- | --- |
| SAP table → data lake (full load) | `bicep/data-factory.bicep` → `adf/linked-services/key-vault.json`, `adls-gen2.json`, `sap-table.json` → `adf/datasets/sap-table.json`, `adls-parquet.json` → `adf/pipelines/copy-sap-table-to-adls.json` |
| SAP delta → Delta tables → Fabric | `bicep/data-factory.bicep` → `adf/linked-services/key-vault.json`, `adls-gen2.json`, `sap-cdc.json` → `adf/datasets/adls-json.json` → `adf/control-files/sap-cdc-objects.json` → `adf/pipelines/sap-cdc-incremental-to-delta.json` → `bicep/fabric-capacity.bicep` → `fabric/shortcut-adls-delta.json` |
| SAP OData as a secure API | `bicep/apim-sap-odata.bicep` → import OpenAPI → `apim/sap-odata-csrf-policy.xml` (+ identity setup from `azure-auth-entra`); worked example in `examples/sap-odata-apim/` |
| SAP data → Snowflake | `bicep/data-factory.bicep` → `adf/linked-services/key-vault.json`, `adls-gen2.json`, `sap-table.json` or `sap-cdc.json` → SAP extract to Parquet → `azure-blob-staging.json`, `snowflake-v2.json` → `adf/datasets/snowflake-v2-table.json` → `adf/pipelines/copy-adls-parquet-to-snowflake.json` |
| IDocs to and from SAP | `bicep/logicapp-standard-sap.bicep` (`vnetPrivatePortsCount = 2`) → worked example `examples/logicapps-sap-idoc/` |
| Everything deployed by pipelines | `bicep/github-oidc-identity.bicep` → `github-actions/bicep-ci.yml` → `adf-cicd/package.json` + `github-actions/adf-cicd.yml` |
