// Deploys an Azure Data Factory with a system-assigned managed identity,
// an ADLS Gen2 storage account and a Key Vault (RBAC mode), and grants the
// factory the roles it needs. No secrets are created here.

@description('Base name used for all resources (lowercase letters and numbers).')
param baseName string

@description('Azure region.')
param location string = resourceGroup().location

var factoryName = 'adf-${baseName}'
var storageName = take('st${baseName}${uniqueString(resourceGroup().id)}', 24)
var keyVaultName = take('kv-${baseName}-${uniqueString(resourceGroup().id)}', 24)

// Built-in role definition IDs
var storageBlobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var keyVaultSecretsUser = '4633458b-17de-408a-b874-0445c86b69e6'

resource factory 'Microsoft.DataFactory/factories@2018-06-01' = {
  name: factoryName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    isHnsEnabled: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource rawContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'raw'
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
  }
}

resource factoryStorageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, factory.id, storageBlobDataContributor)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributor)
    principalId: factory.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource factoryKeyVaultRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, factory.id, keyVaultSecretsUser)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUser)
    principalId: factory.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output factoryName string = factory.name
output storageAccountName string = storage.name
output keyVaultName string = keyVault.name
