// Azure API Management in front of an SAP OData service.
// Creates: APIM (system-assigned identity), Key Vault Secrets User role for APIM on an existing vault,
// named values (Entra ID settings, SAP settings, Key Vault-backed secrets) and the SAP backend with TLS validation.
// The API itself is imported afterwards from an OpenAPI file (az apim api import), then the policy is applied.
//
// authMode:
//   'sandbox' -> SAP Business Accelerator Hub sandbox (read-only, API key header). Secret: sap-apikey.
//   's4hana'  -> own S/4HANA / SAP Gateway with a technical user. Secret: sap-password.
// Secrets must already exist in the Key Vault; they are never passed to this template.
// The deployer needs permission to create role assignments on the Key Vault.
// APIM provisioning can take 30+ minutes (Developer tier). If a Key Vault named value fails because the
// role assignment hasn't propagated yet, rerun the deployment.

@description('API Management instance name (globally unique).')
param apimName string

@description('Azure region.')
param location string = resourceGroup().location

@description('Publisher e-mail shown in the developer portal.')
param publisherEmail string

@description('Publisher name.')
param publisherName string

@description('APIM tier. Developer has no SLA: use it for tests only.')
@allowed([
  'Developer'
  'BasicV2'
  'StandardV2'
  'Premium'
])
param skuName string = 'Developer'

@description('Existing Key Vault (RBAC mode) that holds the SAP secret.')
param keyVaultName string

@description('Backend authentication mode.')
@allowed([
  'sandbox'
  's4hana'
])
param authMode string

@description('OData service root, e.g. https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap/API_BUSINESS_PARTNER or https://<host>:<port>/sap/opu/odata/sap/API_BUSINESS_PARTNER')
param sapServiceRoot string

@description('SAP client (s4hana mode).')
param sapClient string = '100'

@description('SAP technical user (s4hana mode). Not a secret.')
param sapUser string = ''

@description('Key Vault secret name holding the SAP password (s4hana mode).')
param sapPasswordSecretName string = 'sap-odata-password'

@description('Key Vault secret name holding the SAP Business Accelerator Hub API key (sandbox mode).')
param sapApiKeySecretName string = 'sap-sandbox-apikey'

@description('Microsoft Entra tenant that issues tokens for the API.')
param entraTenantId string = tenant().tenantId

@description('Expected token audience: the Application ID URI or client ID of the API app registration.')
param entraApiAudience string

@description('Tags applied to the APIM instance.')
param tags object = {}

var keyVaultSecretsUser = '4633458b-17de-408a-b874-0445c86b69e6'
var isS4 = authMode == 's4hana'

resource apim 'Microsoft.ApiManagement/service@2022-08-01' = {
  name: apimName
  location: location
  tags: tags
  sku: {
    name: skuName
    capacity: 1
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource apimKeyVaultRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, apim.id, keyVaultSecretsUser)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUser)
    principalId: apim.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource nvTenant 'Microsoft.ApiManagement/service/namedValues@2022-08-01' = {
  parent: apim
  name: 'entra-tenant-id'
  properties: {
    displayName: 'entra-tenant-id'
    value: entraTenantId
  }
}

resource nvAudience 'Microsoft.ApiManagement/service/namedValues@2022-08-01' = {
  parent: apim
  name: 'entra-api-audience'
  properties: {
    displayName: 'entra-api-audience'
    value: entraApiAudience
  }
}

resource nvServiceRoot 'Microsoft.ApiManagement/service/namedValues@2022-08-01' = {
  parent: apim
  name: 'sap-odata-service-root'
  properties: {
    displayName: 'sap-odata-service-root'
    value: sapServiceRoot
  }
}

resource nvSapClient 'Microsoft.ApiManagement/service/namedValues@2022-08-01' = if (isS4) {
  parent: apim
  name: 'sap-client'
  properties: {
    displayName: 'sap-client'
    value: sapClient
  }
}

resource nvSapUser 'Microsoft.ApiManagement/service/namedValues@2022-08-01' = if (isS4) {
  parent: apim
  name: 'sap-user'
  properties: {
    displayName: 'sap-user'
    value: empty(sapUser) ? 'not-set' : sapUser
  }
}

resource nvSapPassword 'Microsoft.ApiManagement/service/namedValues@2022-08-01' = if (isS4) {
  parent: apim
  name: 'sap-password'
  properties: {
    displayName: 'sap-password'
    secret: true
    keyVault: {
      secretIdentifier: '${keyVault.properties.vaultUri}secrets/${sapPasswordSecretName}'
    }
  }
  dependsOn: [
    apimKeyVaultRole
  ]
}

resource nvSapApiKey 'Microsoft.ApiManagement/service/namedValues@2022-08-01' = if (!isS4) {
  parent: apim
  name: 'sap-apikey'
  properties: {
    displayName: 'sap-apikey'
    secret: true
    keyVault: {
      secretIdentifier: '${keyVault.properties.vaultUri}secrets/${sapApiKeySecretName}'
    }
  }
  dependsOn: [
    apimKeyVaultRole
  ]
}

resource sapBackend 'Microsoft.ApiManagement/service/backends@2022-08-01' = {
  parent: apim
  name: 'sap-odata-backend'
  properties: {
    url: sapServiceRoot
    protocol: 'http'
    description: 'SAP OData service (${authMode})'
    tls: {
      validateCertificateChain: true
      validateCertificateName: true
    }
  }
}

@description('Gateway URL of the API Management instance.')
output gatewayUrl string = apim.properties.gatewayUrl

@description('Principal ID of the APIM system-assigned identity.')
output apimPrincipalId string = apim.identity.principalId
