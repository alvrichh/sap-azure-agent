# Microsoft Graph templates

| File | Purpose |
| --- | --- |
| `sites-selected-grant.json` | Body to grant an app (with `Sites.Selected`) access to one SharePoint site: `POST /v1.0/sites/{site-id}/permissions`. Roles: `read`, `write`, `manage`, `fullcontrol`. |
| `subscription-sharepoint-list.json` | Change-notification subscription for a SharePoint list (`POST /v1.0/subscriptions`). |
| `copilot-connector-connection.json` | Create a Microsoft 365 Copilot connector connection (`POST /v1.0/external/connections`). |
| `copilot-connector-schema.json` | Register its schema (`PATCH /v1.0/external/connections/{id}/schema`) for SAP material data. |

Call Graph with your own login through the Azure CLI (it requests the Graph token automatically for graph.microsoft.com URLs):

```bash
az rest --method post --url "https://graph.microsoft.com/v1.0/sites/<site-id>/permissions" --body @templates/graph/sites-selected-grant.json
```

Granting site permissions requires an admin or an app with `Sites.FullControl.All`; the target app itself only needs `Sites.Selected`.
