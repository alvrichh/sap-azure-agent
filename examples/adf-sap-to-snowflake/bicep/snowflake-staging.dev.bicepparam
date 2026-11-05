using 'snowflake-staging.bicep'

// Test case: SAP -> Snowflake (dev). No secrets here.
param storageAccountName = '<storage-account-name>'
param snowflakePrincipalId = '<snowflake-integration-principal-id>'
param stagingContainerName = 'snowflake-staging'
