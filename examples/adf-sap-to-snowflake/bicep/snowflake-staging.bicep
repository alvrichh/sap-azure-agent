// Staging container for Snowflake COPY INTO and read access for Snowflake's storage integration app.
// Deploy into the resource group of the data factory's storage account (templates/bicep/data-factory.bicep),
// whose managed identity already has Storage Blob Data Contributor on the account.
// Look up the Snowflake app's service principal after the tenant admin has consented (AZURE_CONSENT_URL):
//   az ad sp list --display-name '<azure-multi-tenant-app-name-prefix>' --query '[].id' -o tsv

@description('Existing storage account (from data-factory.bicep).')
param storageAccountName string

@description('Object ID of the Snowflake storage integration service principal in this tenant.')
param snowflakePrincipalId string

@description('Container used as staging for Snowflake COPY INTO.')
param stagingContainerName string = 'snowflake-staging'

var storageBlobDataReader = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' existing = {
  parent: storage
  name: 'default'
}

resource staging 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: stagingContainerName
  properties: {
    publicAccess: 'None'
  }
}

// Read-only, scoped to the staging container only
resource snowflakeReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(staging.id, snowflakePrincipalId, storageBlobDataReader)
  scope: staging
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataReader)
    principalId: snowflakePrincipalId
    principalType: 'ServicePrincipal'
  }
}

@description('Value for STORAGE_ALLOWED_LOCATIONS in the Snowflake storage integration.')
output snowflakeAllowedLocation string = 'azure://${storage.name}.blob.${environment().suffixes.storage}/${staging.name}/'
