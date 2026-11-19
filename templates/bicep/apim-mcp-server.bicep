// Exposes operations of a REST API that is already in API Management as a remote MCP server.
// Each selected operation becomes an MCP tool. Agents (Microsoft Foundry, Copilot Studio, GitHub Copilot,
// Claude, Codex) then call SAP through the same governed API: Entra ID, rate limits, logging.
//
// Requirements and limits (Microsoft Learn, "Manage MCP servers programmatically in API Management"
// and "Expose a REST API in API Management as an MCP server"):
//   - Pin API version 2025-09-01-preview or later for the MCP resources.
//   - Tiers: Developer, Basic, Basic v2, Standard, Standard v2, Premium, Premium v2. Not in workspaces.
//   - REST API-backed MCP servers expose tools only (no MCP resources or prompts).
//   - Tool operationId is the full ARM resource ID of the backing operation.
//   - If global diagnostics log the frontend response body, set its payload bytes to 0: logging or reading
//     the response body breaks MCP streaming. Never read context.Response.Body in MCP server policies.
//
// The MCP endpoint is <gateway>/<mcpServerId>/mcp; confirm it in the portal (APIs > MCP servers > Server URL).

@description('Existing API Management instance.')
param apimName string

@description('Resource name and URL path of the MCP server. Must be unique in the instance.')
param mcpServerId string

@description('Display name of the MCP server.')
param displayName string

@description('What the server does. Agents read it to decide when to use the tools: be specific.')
param mcpDescription string

@description('Resource name of the existing REST API whose operations become tools.')
param backingApiId string

@description('Tools to create: [{ name, operation, description }]. operation is the operation resource name in the backing API; description is what the model reads.')
param tools array

@description('Policy XML applied to every tool of the MCP server (format xml). Empty: no MCP-scope policy.')
param policyXml string = ''

@description('Require an APIM subscription key in addition to the policy checks. Agents usually authenticate with Entra ID instead.')
param subscriptionRequired bool = false

resource apim 'Microsoft.ApiManagement/service@2025-09-01-preview' existing = {
  name: apimName
}

resource mcpServer 'Microsoft.ApiManagement/service/apis@2025-09-01-preview' = {
  parent: apim
  name: mcpServerId
  properties: {
    type: 'mcp'
    displayName: displayName
    description: mcpDescription
    path: mcpServerId
    protocols: [
      'https'
    ]
    subscriptionRequired: subscriptionRequired
  }
}

resource mcpTools 'Microsoft.ApiManagement/service/apis/tools@2025-09-01-preview' = [for tool in tools: {
  parent: mcpServer
  name: tool.name
  properties: {
    displayName: tool.name
    description: tool.description
    operationId: resourceId('Microsoft.ApiManagement/service/apis/operations', apimName, backingApiId, tool.operation)
  }
}]

resource mcpPolicy 'Microsoft.ApiManagement/service/apis/policies@2025-09-01-preview' = if (!empty(policyXml)) {
  parent: mcpServer
  name: 'policy'
  properties: {
    format: 'xml'
    value: policyXml
  }
}

@description('MCP endpoint (streamable HTTP). Confirm it in the portal.')
output mcpServerUrl string = '${apim.properties.gatewayUrl}/${mcpServerId}/mcp'

@description('Names of the tools created, for allowed_tools in the agent.')
output toolNames array = [for tool in tools: tool.name]
