// SAP purchase order tools for an AI agent:
//   1. imports the read-only facade API "sap-po-tools" from ../apim/po-tools.openapi.json and applies its policy;
//   2. exposes its two operations as an MCP server with templates/bicep/apim-mcp-server.bicep.
// Run after templates/bicep/apim-sap-odata.bicep (APIM, Key Vault named values, SAP backend), deployed with
// sapServiceRoot pointing at API_PURCHASEORDER_PROCESS_SRV (see ./apim.*.dev.bicepparam).
// OpenAPI import names each operation after its operationId; the tools reference those names.

@description('API Management instance created by apim-sap-odata.bicep.')
param apimName string

@description('Backend authentication mode; selects the API policy.')
@allowed([
  'sandbox'
  's4hana'
])
param authMode string

@description('Resource name and path of the facade REST API.')
param apiId string = 'sap-po-tools'

@description('Resource name and path of the MCP server.')
param mcpServerId string = 'sap-po-mcp'

@description('App role that agents and users need to call the tools.')
param appRole string = 'PurchaseOrder.Read'

var apiPolicyXml = authMode == 's4hana' ? loadTextContent('../apim/policy-po-tools-s4hana.xml') : loadTextContent('../apim/policy-po-tools-sandbox.xml')
var mcpPolicyXml = replace(loadTextContent('../../../templates/apim/mcp-server-policy.xml'), '__APP_ROLE__', appRole)

resource apim 'Microsoft.ApiManagement/service@2024-05-01' existing = {
  name: apimName
}

resource api 'Microsoft.ApiManagement/service/apis@2024-05-01' = {
  parent: apim
  name: apiId
  properties: {
    displayName: 'SAP purchase order tools'
    description: 'Read-only facade over API_PURCHASEORDER_PROCESS_SRV for AI agents.'
    path: apiId
    protocols: [
      'https'
    ]
    subscriptionRequired: false
    format: 'openapi+json'
    value: loadTextContent('../apim/po-tools.openapi.json')
  }
}

resource apiPolicy 'Microsoft.ApiManagement/service/apis/policies@2024-05-01' = {
  parent: api
  name: 'policy'
  properties: {
    format: 'xml'
    value: apiPolicyXml
  }
}

module mcp '../../../templates/bicep/apim-mcp-server.bicep' = {
  name: 'sap-po-mcp-server'
  params: {
    apimName: apimName
    mcpServerId: mcpServerId
    displayName: 'SAP purchase orders'
    mcpDescription: 'Read-only SAP S/4HANA purchase order data: status of one purchase order, or the latest purchase orders of a supplier. Use only for SAP purchasing questions.'
    backingApiId: api.name
    tools: [
      {
        name: 'get_purchase_order_status'
        operation: 'get-purchase-order-status'
        description: 'Get the header and status of one SAP purchase order by its number (digits only, up to 10). Returns supplier, company code, type, date, currency, processing status and whether release is still pending. Read-only.'
      }
      {
        name: 'list_supplier_purchase_orders'
        operation: 'list-supplier-purchase-orders'
        description: 'List the latest purchase orders of one SAP supplier (supplier number, letters and digits, up to 10), newest first, with their status. Optional top: 1 to 20, default 10. Read-only.'
      }
    ]
    policyXml: mcpPolicyXml
  }
  dependsOn: [
    apiPolicy
  ]
}

@description('MCP endpoint to register in Foundry or Copilot Studio.')
output mcpServerUrl string = mcp.outputs.mcpServerUrl

@description('Tool names for allowed_tools.')
output toolNames array = mcp.outputs.toolNames
