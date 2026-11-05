---
name: adf-sap-pipeline
description: Build data pipelines that extract data from SAP systems (S/4HANA, ECC, BW, BW/4HANA, HANA) into Azure (Data Lake Storage, Synapse, Fabric, SQL) using Azure Data Factory or Fabric Data Factory. Use when the user wants to connect SAP to Azure for analytics, replication or integration.
---

# SAP → Azure pipelines with Data Factory

Use together with the `azure-data-factory` skill. Always confirm connector support and prerequisites on Microsoft Learn ("SAP connectors overview" for Data Factory) via the `microsoft-learn` MCP server — they change between releases.

## 1. Classify the SAP source

| Question | Why it matters |
| --- | --- |
| Which product? S/4HANA, ECC, BW, BW/4HANA, standalone HANA | Determines the connector. |
| Deployment? On-premises, RISE with SAP / private cloud, S/4HANA Cloud public edition | Public cloud editions usually expose only APIs (OData), not RFC or database access. |
| Full or incremental? | Incremental loads favor SAP CDC (ODP-based) connectors. |
| What objects? Tables, CDS views, extractors, BW InfoProviders | Determines connector and SAP-side setup. |
| Network path from Azure to SAP? | Almost always requires a self-hosted integration runtime. |

## 2. Choose the connector (verify on Microsoft Learn)

| Need | Typical connector |
| --- | --- |
| Incremental / delta extraction from S/4HANA or ECC (CDS views, extractors, SLT) | **SAP CDC** (ODP framework, used in mapping data flows) → `sap-cdc-incremental` skill, `templates/adf/linked-services/sap-cdc.json` |
| Full extraction of tables or views via RFC | **SAP Table** → `templates/adf/linked-services/sap-table.json` |
| Data from SAP BW via Open Hub destinations | **SAP BW Open Hub** |
| BW queries / InfoCubes | **SAP BW (MDX)** |
| Direct read from a HANA database | **SAP HANA** |
| Data exposed via OData services (e.g. SAP Gateway, S/4HANA Cloud APIs) | **SAP ECC** / generic **OData** connector → `templates/adf/linked-services/sap-ecc-odata.json` (works with the Azure IR for public endpoints) |

## 3. Prerequisites

- **Self-hosted integration runtime** on a Windows machine with network access to the SAP system (or to SAP Router / Cloud Connector setups as applicable).
- **SAP client libraries** on the IR machine as required by the connector (for example SAP .NET Connector for RFC-based connectors, the HANA ODBC driver for SAP HANA). Check the exact versions in the connector docs.
- **SAP technical user** with the minimum authorizations required by the connector (RFC, ODP, table read). Ask the SAP Basis team; document the roles granted.
- **Secrets in Azure Key Vault** (RBAC mode); the ADF managed identity needs the *Key Vault Secrets User* role (granted by `templates/bicep/data-factory.bicep`).
- **Fabric Data Factory** uses the **on-premises data gateway** instead of a self-hosted IR (see `microsoft-fabric`).

## 4. Reference architecture

```
SAP S/4HANA ──RFC/ODP──► Self-hosted IR ──► ADF / Fabric Data Factory ──► ADLS Gen2 (raw, Parquet)
                                                                      └──► Transform (data flows / Spark / Databricks)
                                                                             └──► Synapse / Fabric Lakehouse / SQL ──► Power BI
```

Land raw data unchanged first (bronze), then curate (silver/gold). Partition by load date.

## 5. Build it

1. Deploy the factory and storage: `templates/bicep/data-factory.bicep`.
2. Register the self-hosted IR and install SAP prerequisites on it.
3. Create linked services from:
   - `templates/adf/linked-services/key-vault.json` (first: the other linked services resolve their secrets through it)
   - `templates/adf/linked-services/sap-table.json`
   - `templates/adf/linked-services/adls-gen2.json`
4. Create datasets from `templates/adf/datasets/`.
5. Create the pipeline from `templates/adf/pipelines/copy-sap-table-to-adls.json` and parameterize the table name.
6. For incremental loads, follow the `sap-cdc-incremental` skill (SAP CDC connector, metadata-driven pipeline to Delta).
7. Test with a small table first (e.g. `T001`, company codes), then scale up with partitioning options.

### Target: Snowflake

When the destination is Snowflake instead of Azure storage or Fabric (worked example: `examples/adf-sap-to-snowflake/`):

- Use the **Snowflake V2** connector (`SnowflakeV2`; V1 is removed) with **key-pair authentication**; keep the private key and passphrase in Key Vault (`templates/adf/linked-services/snowflake-v2.json`).
- Land SAP data in ADLS as Parquet first, then load Snowflake with a **staged copy** (`enableStaging`) and a Snowflake **storage integration** in `importSettings`: the staging container is read by Snowflake's own Entra ID app (*Storage Blob Data Reader* on that container), so no SAS token is needed (`templates/adf/pipelines/copy-adls-parquet-to-snowflake.json`).
- The Snowflake user needs `USAGE` on database and schema, read/write on the tables and `CREATE STAGE` on the session schema.
- Load a landing table (truncate + copy), reconcile row counts, then `MERGE` into the core table with a Script activity. On connector version 1.0 a script block holds one statement and has no script parameters; version 1.1 adds both.
- Snowflake V2 Lookup/Script return `NUMBER` as a string and timestamps as `DateTimeOffset`: convert with `int()`/`float()`/`formatDateTime()` in expressions.

## 6. Common pitfalls

- Missing or wrong SAP client libraries on the IR machine → connection failures.
- Large tables without partitioning → timeouts and RFC memory issues; use the connector's partition options.
- Running the IR on an undersized VM → slow throughput; scale up or add nodes.
- Extracting with a dialog user instead of a technical user, or with excessive authorizations.
- Licensing: confirm with SAP that the chosen extraction method is permitted under the customer's SAP license (especially direct database access and RFC table reads).

## Related skills

- `sap-cdc-incremental` — delta replication with ODP into Delta tables.
- `microsoft-fabric` — landing SAP data in Fabric (shortcuts, connectors, Mirroring via SAP Datasphere).
- `sap-api-integration` — transactional access (OData, RFC/BAPI/IDoc) instead of bulk extraction.
- `azure-auth-entra`, `azure-bicep-iac`, `adf-cicd` — identities, infrastructure and release.
