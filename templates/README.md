# Templates

Reusable, parameterized templates. Replace every `<placeholder>`; never put secrets in these files.

| Path | What it is |
| --- | --- |
| `bicep/data-factory.bicep` | Data factory (managed identity), ADLS Gen2 with a `raw` container, Key Vault (RBAC), and role assignments. |
| `bicep/github-oidc-identity.bicep` | User-assigned managed identity with a GitHub Actions federated credential (OIDC, no secrets) and a role assignment. |
| `github-actions/azure-login-oidc.yml` | Example workflow: Azure login with OIDC and Bicep deployment. |
| `adf/linked-services/key-vault.json` | Key Vault linked service used to resolve all secrets. |
| `adf/linked-services/sap-table.json` | SAP Table (RFC) connection through a self-hosted integration runtime. |
| `adf/linked-services/adls-gen2.json` | ADLS Gen2 connection with managed identity. |
| `adf/datasets/sap-table.json` | Parameterized SAP table dataset. |
| `adf/datasets/adls-parquet.json` | Parameterized Parquet dataset in ADLS Gen2. |
| `adf/pipelines/copy-sap-table-to-adls.json` | Full copy of one SAP table to ADLS, partitioned by load date. |

Deploy the Bicep template:

```bash
az deployment group create --resource-group <resource-group> --template-file templates/bicep/data-factory.bicep --parameters baseName=<name>
```
