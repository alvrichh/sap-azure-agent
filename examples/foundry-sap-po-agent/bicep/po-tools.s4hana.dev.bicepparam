using 'po-tools.bicep'

// Facade API + MCP server, option B (own S/4HANA).
param apimName = 'apim-sappo-dev-<suffix>'
param authMode = 's4hana'
param appRole = 'PurchaseOrder.Read'
