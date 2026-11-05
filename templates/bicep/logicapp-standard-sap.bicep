// Logic App Standard (single-tenant) prepared for the SAP built-in connector.
// - Workflow Standard plan (WS1), 64-bit worker (matches the x64 SAP NCo 3.1 libraries).
// - Regional VNet integration on a subnet with line of sight to SAP (dispatcher/gateway ports); all traffic routed through the VNet.
// - SAP password as a Key Vault reference resolved by the app's system-assigned identity (Key Vault Secrets User).
// - SAP NCo DLLs (rscp4n.dll, sapnco.dll, sapnco_utils.dll) are NOT deployed here: SAP licenses them; upload them as
//   "Client/SDK Assembly (.NET Framework)" or deploy them in lib/builtinOperationSdks/net472 with the project.
// - Optional VNet private ports (stateful mode): required by the SAP trigger "When a message is received",
//   "Respond to SAP server" and actions that use a Transaction ID (e.g. sending IDocs with an explicit TID).
// - Optional extra app settings (non-secret values such as SAP gateway, program ID, IDoc partners, downstream URLs).
// The deployer needs permission to create role assignments on the Key Vault.

@description('Logic app name (globally unique).')
param logicAppName string

@description('Azure region.')
param location string = resourceGroup().location

@description('Resource ID of the integration subnet (delegated to Microsoft.Web/serverFarms) that can reach SAP.')
param integrationSubnetId string

@description('Existing Key Vault (RBAC mode) holding the SAP password.')
param keyVaultName string

@description('Key Vault secret name with the SAP technical user password.')
param sapPasswordSecretName string = 'sap-rfc-password'

@description('SAP application server host.')
param sapAppServerHost string

@description('SAP system number (00-99).')
param sapSystemNumber string

@description('SAP client (mandant).')
param sapClient string

@description('SAP technical RFC user (not a secret).')
param sapUser string

@description('SAP logon language.')
param sapLanguage string = 'EN'

@description('VNet private ports for stateful mode of the SAP built-in connector (0 = off; 2 when using the SAP trigger, Respond to SAP server or Transaction IDs). NSGs must allow ports 20000-30000 inside the subnet.')
@minValue(0)
@maxValue(2)
param vnetPrivatePortsCount int = 0

@description('Extra non-secret app settings as { NAME: value }. Secrets go in Key Vault, never here.')
param additionalAppSettings object = {}

@description('Tags applied to all resources.')
param tags object = {}

var keyVaultSecretsUser = '4633458b-17de-408a-b874-0445c86b69e6'
var storageName = take('st${toLower(replace(logicAppName, '-', ''))}${uniqueString(resourceGroup().id)}', 24)
var contentShare = toLower(take(logicAppName, 63))

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: 'asp-${logicAppName}'
  location: location
  tags: tags
  sku: {
    name: 'WS1'
    tier: 'WorkflowStandard'
  }
  properties: {
    elasticScaleEnabled: false
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

var extraSettings = map(items(additionalAppSettings), s => { name: s.key, value: string(s.value) })

var storageConnection = 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'

resource logicApp 'Microsoft.Web/sites@2023-12-01' = {
  name: logicAppName
  location: location
  tags: tags
  kind: 'functionapp,workflowapp'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    virtualNetworkSubnetId: integrationSubnetId
    siteConfig: {
      use32BitWorkerProcess: false
      netFrameworkVersion: 'v6.0'
      vnetRouteAllEnabled: true
      vnetPrivatePortsCount: vnetPrivatePortsCount
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: concat([
        { name: 'APP_KIND', value: 'workflowApp' }
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'dotnet' }
        { name: 'AzureWebJobsStorage', value: storageConnection }
        { name: 'WEBSITE_CONTENTAZUREFILECONNECTIONSTRING', value: storageConnection }
        { name: 'WEBSITE_CONTENTSHARE', value: contentShare }
        { name: 'SAP_APPSERVER_HOST', value: sapAppServerHost }
        { name: 'SAP_SYSTEM_NUMBER', value: sapSystemNumber }
        { name: 'SAP_CLIENT', value: sapClient }
        { name: 'SAP_USER', value: sapUser }
        { name: 'SAP_LANGUAGE', value: sapLanguage }
        { name: 'SAP_PASSWORD', value: '@Microsoft.KeyVault(VaultName=${keyVaultName};SecretName=${sapPasswordSecretName})' }
      ], extraSettings)
    }
  }
}

resource kvRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, logicApp.id, keyVaultSecretsUser)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUser)
    principalId: logicApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

@description('Default host name of the logic app.')
output defaultHostName string = logicApp.properties.defaultHostName

@description('Principal ID of the logic app system-assigned identity.')
output principalId string = logicApp.identity.principalId
