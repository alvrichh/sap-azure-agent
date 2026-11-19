using 'po-tools.bicep'

// Facade API + MCP server, option A (SAP sandbox).
param apimName = 'apim-sappo-dev-<suffix>'
param authMode = 'sandbox'
param appRole = 'PurchaseOrder.Read'
