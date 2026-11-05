using '../data-factory.bicep'

// Development environment. No secrets here: secrets live in Key Vault.
param baseName = 'sapazdev'
param tags = {
  environment: 'dev'
  workload: 'sap-azure-integration'
  owner: '<team-or-email-alias>'
}
