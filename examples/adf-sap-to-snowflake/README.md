# Test case: SAP to Snowflake with Azure Data Factory

A complete, reproducible test of the agent's Snowflake path. **Azure Data Factory** reads three SAP tables (customers `KNA1`, materials `MARA` and sales order headers `VBAK`) and lands them as Parquet in ADLS Gen2. It then loads them into **Snowflake** with a staged `COPY INTO` through a **storage integration**, so no SAS token is needed. It checks that the row counts in SAP and Snowflake match, and only then merges into the core tables. There are no passwords: Snowflake uses **key-pair authentication** with the key in **Key Vault**, and Azure storage uses **managed identities**.

Skills involved: `adf-sap-pipeline`, `azure-data-factory`, `azure-auth-entra`, `azure-bicep-iac`.

> **Status:** 12 unit tests and 13 static checks pass (`tests/validate_example.py`), and the validator caught all ten faults deliberately injected into a copy. The generated `MERGE` statements **run for real** in DuckDB against the generated DDL. A three-construct dialect shim stands in for Snowflake (date parsing, `CURRENT_TIMESTAMP()`, qualified `SET` targets). The runtime tests (TC-01…TC-12) have **not yet run** against real SAP, Azure and Snowflake. Five details come from Snowflake's documentation or aren't published, and must be confirmed in the first run (section 4).

## 1. Scenario

| Item | Value |
| --- | --- |
| SAP | S/4HANA or ECC, SID `S4P`, client `100`, RFC user for the SAP Table connector (self-hosted integration runtime with SAP NCo) |
| Objects | `KNA1` (key `KUNNR`), `MARA` (key `MATNR`), `VBAK` (key `VBELN`, filtered `ERDAT GE '20260101'` in SAP) |
| Azure | Data factory with managed identity, ADLS Gen2 (`raw`, `config`, `snowflake-staging`), Key Vault |
| Snowflake | Database `SAP_DB`, schemas `SAP_LANDING` (reloaded every run) and `SAP_CORE` (merged), warehouse `ADF_SAP_WH` (XS, auto-suspend 60 s), role `ADF_SAP_LOADER`, service user `ADF_SAP_SVC` (key pair), storage integration `ADF_SAP_AZURE_INT` |

```
adf/objects.json ──tools/generate.py──► adf/sap-snowflake-objects.json (control file: fields, filter, COUNT and MERGE SQL)
                                    └─► snowflake/02-tables.sql (landing + core DDL)

PL_Sap_To_Snowflake (concurrency 1)
  LookupObjects (control file in ADLS config/)
  ForEach object (3 in parallel)
    1. CopySapToAdls           SAP Table (RFC_READ_TABLE, declared fields + filter) → raw/sap/<table>/load_date=…/run=<RunId>/ Parquet
    2. CopyAdlsToSnowflakeLanding   preCopyScript TRUNCATE SAP_LANDING.<table>; staged COPY INTO via ADF_SAP_AZURE_INT
                                    (staging: snowflake-staging container, factory managed identity; Snowflake app: Blob Data Reader)
    3. CountLandingRows        SELECT COUNT(*) FROM SAP_LANDING.<table>
    4. IfRowCountsMatch        SAP rowsCopied = landing ROW_COUNT ?
         yes → MergeIntoCore   MERGE (dedup by key, DATS → DATE, '00000000' → NULL, _LOADED_AT, _ADF_RUN_ID)
         no  → Fail ROWCOUNT_MISMATCH (core table untouched)
```

## 2. Files

| File | Purpose |
| --- | --- |
| `adf/objects.json` | **Source of truth**: tables, keys, columns, Snowflake types, SAP filter. |
| `tools/generate.py` | Validates identifiers and filters, then writes the control file and the DDL (`--check` fails if they're stale). |
| `adf/sap-snowflake-objects.json` | Generated control file, uploaded to `config/` in ADLS. |
| `adf/PL_Sap_To_Snowflake.json` | The pipeline. |
| `adf/LS_SnowflakeV2.json`, `adf/LS_BlobStaging.json` | Linked services for this test (key pair from Key Vault; staging with managed identity). |
| `../../templates/adf/...` | Reused: `LS_KeyVault`, `LS_SapTable`, `LS_AdlsGen2`, `DS_SapTable`, `DS_AdlsParquet`, `DS_AdlsJson`, `DS_SnowflakeV2Table`. |
| `snowflake/01-setup.sql` | Role, warehouse, database, schemas, least-privilege grants, storage integration, key-pair service user. |
| `snowflake/02-tables.sql` | Generated landing and core tables. |
| `snowflake/03-validation.sql` | Reconciliation and quality queries for the runtime tests. |
| `bicep/data-factory.snowflake.dev.bicepparam` | Data factory, ADLS and Key Vault from `templates/bicep/data-factory.bicep`. |
| `bicep/snowflake-staging.bicep` (+ `.dev.bicepparam`) | Staging container and *Storage Blob Data Reader* for the Snowflake app on that container only. |
| `tests/` | Unit tests (DuckDB), static validator, sample activity outputs. |

## 3. Offline checks

```bash
pip install duckdb
```

```bash
python3 examples/adf-sap-to-snowflake/tests/validate_example.py
```

| ID | Static check |
| --- | --- |
| ST-01 / ST-02 | JSON parses; control file and DDL regenerated from `objects.json` and identical (identifiers and SAP filters validated) |
| ST-03 | Every dataset and linked service the pipeline uses exists, with the parameters it passes |
| ST-04 | Snowflake linked service: key pair from Key Vault; database, warehouse, role, user and schema exist in `01-setup.sql`; session schema has `CREATE STAGE` |
| ST-05 | Same storage integration and staging container in the pipeline, Snowflake and Bicep |
| ST-06 | Staging with managed identity (no key, no SAS); Snowflake gets read-only access to the staging container only |
| ST-07 | Loader role has narrow grants (no `ALL`, `OWNERSHIP`, `DELETE`; `TRUNCATE` only on landing); service user has no password |
| ST-08 | One run at a time, retries on both copies, `MERGE` only when row counts match, otherwise `Fail` |
| ST-09 | Single-statement script blocks without script parameters (works on Snowflake V2 1.0 and 1.1) |
| ST-10 | The SAP source reads exactly the declared fields with the declared filter |
| ST-11 / ST-12 | Parameter files → templates; no secrets anywhere |
| ST-13 | Unit tests pass |

| ID | Unit test |
| --- | --- |
| UT-01 | Generated DDL creates every landing and core table |
| UT-02 | First load: duplicate landing rows collapse to one, `20260105` → `2026-01-05`, `00000000` → `NULL`, run ID stored |
| UT-03 | Second load: changed rows updated, new rows inserted, run ID updated |
| UT-04 | Rows missing from a load stay in core (no deletes) |
| UT-05 | Key columns never in the `UPDATE SET` |
| UT-06 | Reconciliation condition with real output shapes (Lookup returns `NUMBER` as a string): match, mismatch, empty |
| UT-07 / UT-08 / UT-09 | Step order; `TRUNCATE` only on landing; the same run-specific folder written and read |
| UT-10 | Count query returns the landing row count |
| UT-11 | Generator rejects SQL in table, column, type, filter (`OR`, quote escape), key, schema and non-DATS dates |
| UT-12 | Generated files up to date |

## 4. To confirm in the first run

| ID | What | How |
| --- | --- | --- |
| UV-01 | `01-setup.sql` syntax (storage integration, `TYPE = SERVICE`, `TRUNCATE` grant) follows Snowflake's documentation, not Microsoft Learn | Run it in a dev account |
| UV-02 | Lookup on Snowflake V2 with only `query` in the source | TC-03 (debug run) |
| UV-03 | SAP Table connector writes `DATS` as `YYYYMMDD` strings and packed numbers as decimals in Parquet | Inspect the Parquet schema after TC-02 |
| UV-04 | Empty `rfcTableOptions` means no filter | TC-02 row counts for `KNA1`/`MARA` |
| UV-05 | The connector's temporary stage reads `snowflake-staging` through `ADF_SAP_AZURE_INT` | TC-03; `COPY_HISTORY` (V-06) |

## 5. Runbook

### Phase 0 — SAP (Basis team)

1. RFC user (type *System*) with `S_RFC` for the function group of `/SAPDS/RFC_READ_TABLE2` (install the SAP note for it if missing) or `RFC_READ_TABLE`, and `S_TABU_NAM` display for `KNA1`, `MARA` and `VBAK` only.
2. Note the row counts in **SE16N** (VBAK with `ERDAT ≥ 01.01.2026`) for TC-02.

### Phase 1 — Azure

1. Deploy the data factory, ADLS and Key Vault:

```bash
az deployment group create --resource-group rg-sapsf-dev --parameters examples/adf-sap-to-snowflake/bicep/data-factory.snowflake.dev.bicepparam
```

2. Install a self-hosted integration runtime with the SAP .NET Connector on a VM that reaches SAP (see `adf-sap-pipeline`).
3. Store the SAP password in Key Vault (prompted, not saved to history):

```bash
az keyvault secret set --vault-name <key-vault-name> --name sap-rfc-password --value "$(read -rsp 'SAP password: ' p; echo "$p")"
```

### Phase 2 — Snowflake

1. Create a key pair outside the repository (encrypted PKCS#8):

```bash
openssl genrsa 2048 | openssl pkcs8 -topk8 -v2 aes-256-cbc -inform PEM -out ~/.snowflake/adf_sap_svc.p8
```

```bash
openssl rsa -in ~/.snowflake/adf_sap_svc.p8 -pubout -out ~/.snowflake/adf_sap_svc.pub
```

2. Fill `<tenant-id>`, `<storage-account-name>` and `<rsa-public-key-body>` (the public key without its header lines) in `snowflake/01-setup.sql`, run it, then run `snowflake/02-tables.sql` as `SYSADMIN`.
3. Open `AZURE_CONSENT_URL` from `DESC STORAGE INTEGRATION` as an Entra ID admin and accept. Then get the app's object ID:

```bash
az ad sp list --display-name '<azure-multi-tenant-app-name-prefix>' --query '[].id' -o tsv
```

4. Grant it read access to the staging container (and create the container):

```bash
az deployment group create --resource-group rg-sapsf-dev --parameters examples/adf-sap-to-snowflake/bicep/snowflake-staging.dev.bicepparam
```

5. Store the private key and its passphrase in Key Vault:

```bash
az keyvault secret set --vault-name <key-vault-name> --name snowflake-private-key --file ~/.snowflake/adf_sap_svc.p8
```

```bash
az keyvault secret set --vault-name <key-vault-name> --name snowflake-private-key-passphrase --value "$(read -rsp 'Key passphrase: ' p; echo "$p")"
```

### Phase 3 — Data Factory content

1. Create the `config` container and upload the control file:

```bash
az storage container create --auth-mode login --account-name <storage-account-name> --name config
```


```bash
az storage blob upload --auth-mode login --account-name <storage-account-name> --container-name config --name sap-snowflake-objects.json --file examples/adf-sap-to-snowflake/adf/sap-snowflake-objects.json
```

2. Create the linked services and datasets in this order (portal JSON editor, or the factory's Git repository with `adf-cicd`): `LS_KeyVault`, `LS_SapTable`, `LS_AdlsGen2` (from `templates/adf/linked-services/`), then `LS_SnowflakeV2` and `LS_BlobStaging` (from `adf/`), then the datasets `DS_SapTable`, `DS_AdlsParquet`, `DS_AdlsJson` and `DS_SnowflakeV2Table`, and finally `PL_Sap_To_Snowflake`.
3. *Test connection* on `LS_SnowflakeV2`. If the key is rejected, check that the Key Vault secret contains the PEM text with its line breaks.

To add a table, edit `adf/objects.json`, run `python3 examples/adf-sap-to-snowflake/tools/generate.py`, apply the new DDL, upload the control file again and rerun the validator.

## 6. Runtime test cases

| ID | Test | Expected result |
| --- | --- | --- |
| TC-01 | Test connection of every linked service | All succeed; Snowflake login history shows `ADF_SAP_SVC` with key-pair auth |
| TC-02 | Debug run of the pipeline | Succeeded; 3 iterations; `rowsCopied` per table = SE16N counts |
| TC-03 | Snowflake after TC-02 (`03-validation.sql` V-01…V-06) | Core counts = SAP counts; no duplicate keys; dates converted; no `VBAK` before 2026; `COPY_HISTORY` loaded |
| TC-04 | Run again without changes in SAP | Same counts; `_ADF_RUN_ID` = new run on all rows; no duplicates |
| TC-05 | Change a customer name and create a sales order in SAP, run | Name updated, order inserted, other rows unchanged except load metadata |
| TC-06 | Insert an extra row into `SAP_LANDING.KNA1` during the run (between copy and count; or test with a debug breakpoint) | `Fail` with `ROWCOUNT_MISMATCH`; `SAP_CORE.KNA1` unchanged |
| TC-07 | Remove the Snowflake app's role on the staging container | Copy to Snowflake fails with an access error; restore |
| TC-08 | Revoke `USAGE ON INTEGRATION` from the loader role | Copy fails with an integration privilege error; restore |
| TC-09 | Disable the Key Vault secret `snowflake-private-key` | Linked service fails to authenticate; enable it again |
| TC-10 | Start two runs at once | The second waits (concurrency 1) |
| TC-11 | Snowflake query history for `ADF_SAP_LOADER` | Only `TRUNCATE`, `COPY`, `SELECT COUNT`, `MERGE` and the connector's temporary stage statements |
| TC-12 | Warehouse after the run | Suspended after 60 s; credits used visible in `WAREHOUSE_METERING_HISTORY` |

**Acceptance:** ST-01…ST-13 pass in strict mode, UV-01…UV-05 confirmed, TC-01…TC-12 pass.

## 7. Production notes

- Prefer **SAP CDC (ODP)** for large or frequently changing tables (`sap-cdc-incremental`), and land it in the same way; `RFC_READ_TABLE` suits small and medium tables.
- Restrict Snowflake with a **network policy** for the integration runtime's egress IPs, or use private connectivity.
- Use a **managed virtual network** in Data Factory and **private endpoints** for storage and Key Vault.
- Add a schedule trigger and alerts on failed runs; keep `concurrency` at 1 because the landing tables are shared between runs.
- Rotate the key pair with Snowflake's second key slot (`RSA_PUBLIC_KEY_2`), then update the Key Vault secret.

## 8. Cleanup

```bash
az group delete --name rg-sapsf-dev
```

(Only if nothing else lives in the resource group; deletion is irreversible.) In Snowflake, drop `SAP_DB`, `ADF_SAP_WH`, `ADF_SAP_AZURE_INT`, `ADF_SAP_SVC` and `ADF_SAP_LOADER`; in Entra ID, remove the consented Snowflake app if nothing else uses it.

## 9. Results log

| ID | Date | Result | Notes |
| --- | --- | --- | --- |
| UT-01…UT-12 | 2026-11-05 | Pass | Offline; MERGE executed in DuckDB with the dialect shim |
| ST-01…ST-13 | 2026-11-05 | Pass | 10/10 injected faults detected |
| UV-01…UV-05 | | To confirm | First run against real systems |
| TC-01…TC-12 | | Not run | Requires SAP, Azure subscription and Snowflake account |
