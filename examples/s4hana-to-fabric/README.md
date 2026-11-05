# Test case: SAP S/4HANA → Microsoft Fabric (end to end)

A complete, reproducible test of the agent's main path: incremental extraction of sales data from an on-premises **SAP S/4HANA** into **Delta tables in ADLS Gen2** with the Azure Data Factory **SAP CDC** connector, exposed in **Microsoft Fabric** through OneLake shortcuts, with a gold layer ready for Power BI.

Skills involved: `sap-cdc-incremental`, `adf-sap-pipeline`, `azure-data-factory`, `microsoft-fabric`, `azure-bicep-iac`, `azure-auth-entra`.

> **Status:** configuration and static checks are complete and pass (`tests/validate_example.py`). The runtime test cases (TC-01…TC-14) have **not been executed yet** against a real SAP system and Azure subscription; record the results in the table at the end when you run them.

## 1. Scenario

| Item | Value |
| --- | --- |
| SAP system | S/4HANA on-premises, SID `S4P`, client `100` (use a **dev/QA** system for the test) |
| Objects (ODP context `SAPI`) | `2LIS_11_VAHDR` sales header, `2LIS_11_VAITM` sales items, `2LIS_13_VDITM` billing items, `0CUSTOMER_ATTR` customers, `0MATERIAL_ATTR` materials |
| Load | Full on first run, then deltas (`fullAndIncrementalLoad`); initial load of sales items split into 2 partitions |
| Azure | Resource group `rg-s4fabric-dev`, data factory, ADLS Gen2, Key Vault (Bicep), self-hosted IR `shir-s4p` |
| Fabric | Capacity `fabs4fdev` (F2), workspace `ws-sap-sales-dev`, lakehouse `lh_sap_silver`, schema `gold` with views |

```
S/4HANA (ODP/ODQ) ─RFC─► shir-s4p ─► ADF data flow (SAP CDC) ─► ADLS Gen2  silver/sap/<entity>  (Delta, MERGE)
                                                                         │
                                               OneLake shortcuts (Tables) ┘──► lh_sap_silver ──► gold views ──► Direct Lake / Power BI
```

## 2. Files

| File | Purpose |
| --- | --- |
| `config/settings.example.json` | All site-specific values (non-secret). Copy to `settings.json` and fill in. |
| `bicep/data-factory.s4fabric.dev.bicepparam` | Data factory + ADLS Gen2 + Key Vault for the test (uses `templates/bicep/data-factory.bicep`). |
| `bicep/fabric-capacity.s4fabric.dev.bicepparam` | Fabric F2 capacity (uses `templates/bicep/fabric-capacity.bicep`). |
| `adf/LS_SapCdc.json` | SAP CDC linked service for S4P/100 (password from Key Vault). |
| `adf/sap-cdc-objects.json` | Control file with the five objects, keys, partitions and targets. |
| `fabric/shortcuts/*.json` | One OneLake shortcut per Delta table. |
| `sql/01-validation.sql` | Data quality and reconciliation queries (TC-05…TC-11). |
| `sql/02-gold-views.sql` | Gold dimension/fact views and a business query (TC-12). |
| `tests/validate_example.py` | Static checks (no SAP/Azure needed). |

Reused from `templates/`: `adf/linked-services/key-vault.json`, `adf/linked-services/adls-gen2.json`, `adf/datasets/adls-json.json`, `adf/pipelines/sap-cdc-incremental-to-delta.json`.

## 3. Run the static checks first

```bash
python3 examples/s4hana-to-fabric/tests/validate_example.py
```

Before deploying, fill in every placeholder and run in strict mode (fails if any `<placeholder>` remains):

```bash
python3 examples/s4hana-to-fabric/tests/validate_example.py --strict --verbose
```

| ID | Static check |
| --- | --- |
| ST-01 | All JSON files parse |
| ST-02 / ST-03 | Control file complete; valid ODP contexts and run modes |
| ST-04 / ST-05 | Checkpoint keys unique and traceable to the object |
| ST-06 / ST-07 | Key columns defined, source and sink keys match, one target folder per object |
| ST-08 | Source partitions well formed and non-overlapping |
| ST-09 | Subscriber name uppercase, ≤ 32 characters |
| ST-10 / ST-11 | Password from Key Vault; linked service on the right self-hosted IR |
| ST-12 / ST-13 | One `Tables` shortcut per Delta folder; SQL only uses existing tables |
| ST-14 | Parameter files reference existing Bicep templates |
| ST-15 | No secrets or inline credentials anywhere |
| ST-16 | Pipeline template passes all object parameters and a per-object checkpoint key |

## 4. Runbook

### Phase 0 — SAP preparation (SAP Basis / SD team)

1. Confirm ODP 2.0 is available (SAP notes 1931427, 2481315).
2. Create the technical RFC user with ODP authorizations (SAP notes 2855052, 460089); give the password to the Azure team **only through Key Vault**.
3. Activate the DataSources if needed (RSA5 → RSA6) and confirm they are released for ODP (SAP note 2232584).
4. LO extractors (`2LIS_*`): activate them in the LO cockpit (LBWE) and fill the setup tables (sales orders: OLI7BW; billing: OLI9BW) in a period without postings, or with the documents locked, so the initial load is consistent.
5. Test each object with **RODPS_REPL_TEST** (and RSA3).
6. **Note the reference counts** for reconciliation: number of sales documents and items in the test range (for example SE16N on VBAK/VBAP), billing items (VBRP), customers (KNA1) and materials (MARA).

### Phase 1 — Azure foundations (`azure-bicep-iac`, `azure-auth-entra`)

```bash
az login
```

```bash
az group create --name rg-s4fabric-dev --location westeurope
```

```bash
az deployment group what-if --resource-group rg-s4fabric-dev --parameters examples/s4hana-to-fabric/bicep/data-factory.s4fabric.dev.bicepparam
```

```bash
az deployment group create --resource-group rg-s4fabric-dev --parameters examples/s4hana-to-fabric/bicep/data-factory.s4fabric.dev.bicepparam
```

Store the SAP password (you'll be prompted; it isn't written to disk or history):

```bash
az keyvault secret set --vault-name <key-vault-name> --name sap-s4p-100-password --value "$(read -rsp 'SAP password: ' p; echo "$p")"
```

Create containers `silver`, `config` and `staging` in the storage account (the Bicep creates `raw`).

### Phase 2 — Self-hosted integration runtime

1. Create the self-hosted IR `shir-s4p` in the factory and install it on a Windows VM with network access to S4P (RFC ports).
2. Install the **SAP .NET Connector** on that VM (version per the SAP CDC docs).
3. Size the VM for the initial load (CPU/RAM drive throughput).

### Phase 3 — Data Factory content (`sap-cdc-incremental`)

1. Linked services: `templates/adf/linked-services/key-vault.json` → `adls-gen2.json` → `examples/s4hana-to-fabric/adf/LS_SapCdc.json`. Test the SAP connection.
2. Dataset `templates/adf/datasets/adls-json.json`.
3. Upload `adf/sap-cdc-objects.json` to `config/sap-cdc-objects.json`.
4. Create the data flow `DF_SapCdc_To_Delta` from the ADF gallery template *"Replicate multiple tables from SAP ODP to Azure Data Lake Storage Gen2 in Delta format"* and align its parameters with the pipeline (see the `sap-cdc-incremental` skill).
5. Import `templates/adf/pipelines/sap-cdc-incremental-to-delta.json`, **publish**, and run it with a **trigger** (not debug).

### Phase 4 — Fabric (`microsoft-fabric`)

```bash
az deployment group create --resource-group rg-s4fabric-dev --parameters examples/s4hana-to-fabric/bicep/fabric-capacity.s4fabric.dev.bicepparam
```

1. Create workspace `ws-sap-sales-dev` on capacity `fabs4fdev` and lakehouse `lh_sap_silver`.
2. Create the workspace identity; grant it **Storage Blob Data Reader** on the storage account.
3. Create a cloud connection to `https://<storage-account-name>.dfs.core.windows.net` with workspace identity; note its ID.
4. Create the five shortcuts:

```bash
for f in examples/s4hana-to-fabric/fabric/shortcuts/*.json; do az rest --method post --resource https://api.fabric.microsoft.com --url "https://api.fabric.microsoft.com/v1/workspaces/<workspace-id>/items/<lakehouse-id>/shortcuts?shortcutConflictPolicy=CreateOrOverwrite" --body @"$f"; done
```

5. On the lakehouse SQL analytics endpoint run `sql/01-validation.sql`, then `sql/02-gold-views.sql`.
6. Optional: create a Direct Lake semantic model on the tables and build a report.

## 5. Runtime test cases

| ID | Test | Steps | Expected result |
| --- | --- | --- | --- |
| TC-01 | SAP connectivity | Test connection on `LS_SapCdc` | Succeeds through `shir-s4p` |
| TC-02 | Key Vault resolution | Check the linked service doesn't hold a password | Password resolved from `sap-s4p-100-password`; no secret visible in ADF |
| TC-03 | Initial load | Trigger the pipeline (first run) | 5 data flow runs succeed; ODQMON shows 5 subscriptions for `ADFS4FDEV_S4P100` |
| TC-04 | Partitioned extraction | Inspect the `2LIS_11_VAITM` run | 2 extraction requests in ODQMON (one per partition) |
| TC-05 | Data landed | `sql/01-validation.sql` block TC-05 | 5 tables, all with rows |
| TC-06 | No duplicates | Block TC-06 | All queries return 0 rows |
| TC-07 | Referential integrity | Block TC-07 | 0, or a small number explained by test data |
| TC-08 | Reconciliation | Block TC-08 vs counts from Phase 0 step 6 | Counts match the SAP reference |
| TC-09 | Delta — insert | Create a sales order in SAP (VA01), run pipeline | New order and items appear; other rows unchanged |
| TC-10 | Delta — update | Change quantity of that order (VA02), run pipeline | Row updated in place (no duplicate key) |
| TC-11 | Delta — deletion/rejection | Delete or reject an item (VA02), run pipeline | Item removed or flagged as the extractor reports it; record observed behaviour |
| TC-12 | Gold layer | `sql/02-gold-views.sql` final query | Top customers by net sales returned |
| TC-13 | Idempotent rerun | Run the pipeline with no SAP changes | Succeeds; row counts unchanged |
| TC-14 | Recovery | Stop the IR mid-run, restart it, rerun | Run recovers via checkpoint; no data loss or duplicates (repeat TC-06/TC-08) |

**Acceptance:** ST-01…ST-16 pass in strict mode and TC-01…TC-14 pass.

## 6. Cost control and cleanup

- Pause the Fabric capacity when not testing:

```bash
az fabric capacity suspend --resource-group rg-s4fabric-dev --capacity-name fabs4fdev
```

- Data flows bill per run on the Azure IR: keep the trigger off between test sessions.
- Remove the ODP subscriptions in SAP (ODQMON) after the test so SAP doesn't keep collecting deltas for `ADFS4FDEV_S4P100`.
- Delete the test resource group only when you're sure nothing else lives in it (irreversible):

```bash
az group delete --name rg-s4fabric-dev
```

## 7. Results log

| ID | Date | Result | Notes |
| --- | --- | --- | --- |
| ST-01…ST-16 | 2026-11-05 | Pass | Static checks, design mode (placeholders pending) |
| TC-01…TC-14 | | Not run | Requires SAP dev/QA system and Azure subscription |
