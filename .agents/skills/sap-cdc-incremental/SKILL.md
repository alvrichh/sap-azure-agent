---
name: sap-cdc-incremental
description: Build incremental (delta) replication from SAP S/4HANA, ECC, BW/BW4HANA or SLT into Azure Data Lake (Delta format) with the Azure Data Factory SAP CDC connector (ODP framework). Covers SAP prerequisites, ODP contexts, run modes, key columns, checkpoint keys, source partitioning, a metadata-driven pipeline and day-2 operations (ODQMON, re-initialization).
---

# SAP CDC incremental replication (ODP → Delta Lake)

Use with `adf-sap-pipeline` (connector choice) and `azure-auth-entra` (identities, Key Vault).
Verified against Microsoft Learn (Nov 2026). Re-check the "SAP CDC connector" pages with the `microsoft-learn` MCP server before production use.

## How it works

```
SAP (ODP framework / ODQ) ──RFC──► Self-hosted IR ──► Staging folder (ADLS Gen2) ──► Mapping data flow (Spark, Azure IR)
                                                                                     └──► Delta table (ADLS Gen2): MERGE inserts/updates/deletes
```

- The SAP CDC connector works **only as a source in mapping data flows** (not in the Copy activity).
- SAP's **Operational Delta Queue (ODQ)** tracks what each subscriber has already received. ADF registers as a subscriber (`subscriberName` on the linked service).
- ADF keeps its own state per **checkpoint key** (set on the Execute Data Flow activity), which enables automatic recovery after failures.
- Mapping data flows interpret the ODP change feed (change mode, ordering of multiple changes to the same key) so the sink receives correct inserts, updates and deletes.

## 1. SAP-side prerequisites (SAP Basis team)

- [ ] **ODP 2.0** available (SAP notes 1931427, 2481315). ABAP CDS **delta** extraction needs NetWeaver **7.50 SPS 05+** (full extraction: 7.40 SPS 08+).
- [ ] **Technical user** authorized for ODP API over RFC (SAP notes 2855052, 460089). Password goes into **Key Vault**.
- [ ] **Extractors (SAPI)**: DataSource active and released for ODP (SAP note 2232584).
- [ ] **CDS views (ABAP_CDS)**: delta-enabled view (`@Analytics.dataExtraction.enabled: true` with a delta annotation). Use the **SQL view name**.
- [ ] **Tables via SLT** (optional, only if raw tables are needed): SLT configured with an ODP target and a queue alias → context `SLT~<queue alias>`.
- [ ] Validate in SAP with program **RODPS_REPL_TEST** before touching Azure.
- [ ] Review known-issue SAP notes: 1660374, 2321589, 2636663, 3038236, 3076927.

## 2. Azure-side prerequisites

- [ ] Self-hosted integration runtime (Windows VM near SAP) with the **SAP .NET Connector** installed; sized for the extraction volume.
- [ ] ADLS Gen2 with containers for **staging** (internal to the connector — do not reuse it for anything else), **config** (control file) and target layers (e.g. `silver`).
- [ ] Data factory managed identity: *Storage Blob Data Contributor* on the storage account, *Key Vault Secrets User* on the vault (`templates/bicep/data-factory.bicep`).
- [ ] The **staging linked service must not use the self-hosted IR** (use Azure IR + managed identity: `templates/adf/linked-services/adls-gen2.json`).

## 3. Choose context, object, run mode and keys

| ODP context | Use for | Example object |
| --- | --- | --- |
| `ABAP_CDS` | S/4HANA CDS views (preferred for S/4HANA) | CDS SQL view name |
| `SAPI` | Extractors / DataSources (classic ECC, also S/4HANA) | `2LIS_11_VAITM` (sales order items) |
| `BW` | BW / BW/4HANA InfoProviders and InfoObjects | ADSO / InfoObject name |
| `HANA` | SAP HANA information views | view name |
| `SLT~<alias>` | Raw application tables replicated by SLT | `VBAP`, `MARA`… |

| Run mode (parameter value) | Behaviour |
| --- | --- |
| `fullAndIncrementalLoad` | First run: create ODP subscription + full snapshot. Then deltas only. **Default choice.** |
| `incrementalLoad` | Create subscription without the initial snapshot; deltas only. |
| `fullLoad` | Full snapshot every run, no subscription, no checkpoint key. |

- **Key columns are mandatory** for the incremental modes. Example for `VBAP`: `["VBELN","POSNR"]` (add `MANDT` if the client field is included).
- **Checkpoint key must be unique per source object** (and per environment). Convention used here: `SAPCDC_<SID><client>_<context>_<object>`.

## 4. Speed up the initial load: source partitioning

For full / first loads, split the extraction into several parallel SAP extraction processes using SAP selection options:

```json
[
  [{ "fieldName": "GJAHR", "sign": "I", "option": "BT", "low": "2015", "high": "2020" }],
  [{ "fieldName": "GJAHR", "sign": "I", "option": "BT", "low": "2021", "high": "2030" }]
]
```

- Each inner array is one partition. Same-field "I" conditions are OR-ed, different fields AND-ed, "E" conditions AND NOT.
- Use SAP internal formats: leading zeros (`"0000001000"`), dates as `YYYYMMDD`.
- ADF does **not** check for overlaps — overlapping partitions duplicate data.
- Partitions only help if SAP, the self-hosted IR VM and the Azure IR all have spare capacity.

## 5. Build it (metadata-driven)

Templates:

| File | Purpose |
| --- | --- |
| `templates/adf/linked-services/sap-cdc.json` | `SapOdp` linked service, password from Key Vault, `subscriberName` |
| `templates/adf/datasets/sap-cdc.json` | Optional `SapOdpResource` dataset for previewing objects |
| `templates/adf/datasets/adls-json.json` | Reads the control file |
| `templates/adf/control-files/sap-cdc-objects.json` | One entry per SAP object (context, object, run mode, keys, partitions, target) |
| `templates/adf/pipelines/sap-cdc-incremental-to-delta.json` | Lookup control file → ForEach → Execute Data Flow with per-object checkpoint key |

Steps:

1. Create linked services `LS_KeyVault`, `LS_AdlsGen2`, `LS_SapCdc`. In `subscriberName` use **UPPERCASE**, unique per linked service, **≤ 32 characters** (e.g. `ADFPRD_SAPCDC_S4P`).
2. Upload the control file to `config/sap-cdc-objects.json`.
3. Create the mapping data flow **`DF_SapCdc_To_Delta`**. Fastest path: in ADF Studio, open the template gallery → **"Replicate multiple tables from SAP ODP to Azure Data Lake Storage Gen2 in Delta format"**, then align its data flow parameters with the ones passed by the pipeline:

   | Data flow parameter | Type | Used in |
   | --- | --- | --- |
   | `sapContext` | string | Source options → ODP context |
   | `sapObjectName` | string | Source options → ODP name |
   | `sapRunMode` | string | Source options → Run mode |
   | `sapKeyColumns` | string[] | Source options → Key columns |
   | `sapPartitions` | string | Optimize → Partition type *Source* → Partition conditions |
   | `deltaContainer`, `deltaFolder` | string | Sink (inline **Delta**) → file system / folder path |
   | `deltaKeyColumns` | string[] | Sink → key columns for upsert/delete |
   | `deltaPartition` | string | Sink → Optimize → key partitioning column |

   Source: **inline**, type SAP CDC, linked service `LS_SapCdc`, allow schema drift. Sink: **inline Delta** on `LS_AdlsGen2`, update method **allow insert, update/upsert and delete**.
4. Import the pipeline and **publish**. Debug runs use a different SAP subscriber process than triggered runs and live only for the browser session — always validate with **triggered** runs.
5. Schedule with a trigger (e.g. every 15–60 minutes). Keep `ForEach.batchCount` modest (4 by default) so SAP is not overloaded.

## 6. Operate it (day 2)

- **Monitor in SAP**: transaction **ODQMON** (queues, subscriptions, requests) — filter by your subscriber name.
- **Monitor in Azure**: data flow activity output, Azure Monitor alerts on failed runs.
- **Re-initialize** an object: reset/delete the subscription in **ODQMON** (ADF cannot do it), then run with a **new checkpoint key** or let `fullAndIncrementalLoad` re-init.
- **Never reuse a checkpoint key** for a different object or environment; never share a subscriber name between factories.
- SAP hierarchies are **not supported** by the connector.
- Troubleshooting: send self-hosted IR logs to Microsoft (ADF docs: "Debug issues with the SAP CDC connector").

## 7. Checklist

- [ ] RODPS_REPL_TEST succeeds for every object.
- [ ] Unique subscriber name per linked service; unique checkpoint key per object.
- [ ] Key columns defined for every incremental object.
- [ ] Staging folder dedicated to the connector, Azure IR only.
- [ ] Pipeline published and validated with triggered runs over several days.
- [ ] Alerts on failure; ODQMON access for the support team.
- [ ] SAP licensing for the extraction approach confirmed with SAP.

## References (Microsoft Learn)

- SAP CDC connector: https://learn.microsoft.com/azure/data-factory/connector-sap-change-data-capture
- Prerequisites and SAP setup: https://learn.microsoft.com/azure/data-factory/sap-change-data-capture-prerequisites-configuration
- Linked service and dataset: https://learn.microsoft.com/azure/data-factory/sap-change-data-capture-prepare-linked-service-source-dataset
- Advanced topics (parameters, partitions, checkpoint keys, debugging): https://learn.microsoft.com/azure/data-factory/sap-change-data-capture-advanced-topics
- Solution template (multiple objects to Delta): https://learn.microsoft.com/azure/data-factory/solution-template-replicate-multiple-objects-sap-cdc
