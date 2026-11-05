# Microsoft Fabric templates

| File | Purpose |
| --- | --- |
| `shortcut-adls-delta.json` | Request body for the Fabric REST API to create a OneLake shortcut in a lakehouse `Tables` folder pointing to a Delta table in ADLS Gen2 (for example, the output of the SAP CDC pipeline). |
| `../bicep/fabric-capacity.bicep` | Fabric capacity (F SKU) as an Azure resource. |

## Create the shortcut

Prerequisites: the lakehouse exists; a Fabric **cloud connection** to the storage account exists (preferably with **workspace identity** authentication, which needs *Storage Blob Data Reader* on the storage account); the caller has Contributor (or higher) on the workspace.

```bash
az rest --method post --resource https://api.fabric.microsoft.com --url "https://api.fabric.microsoft.com/v1/workspaces/<workspace-id>/items/<lakehouse-id>/shortcuts?shortcutConflictPolicy=CreateOrOverwrite" --body @templates/fabric/shortcut-adls-delta.json
```

- `path` must start with `Tables` (Delta tables, queryable from the SQL analytics endpoint and Direct Lake) or `Files` (raw files).
- `subpath` is `/<container>/<folder>` and must point to the folder that contains `_delta_log` for a table shortcut.
- One shortcut per Delta table in `Tables`.
