using '../../../templates/bicep/data-factory.bicep'

// Test case SAP -> Snowflake (dev): data factory, ADLS Gen2 (raw + staging) and Key Vault. No secrets here.
param baseName = 'sapsfdev'
param tags = {
  environment: 'dev'
  workload: 'adf-sap-to-snowflake-test'
  owner: '<team-or-email-alias>'
}
