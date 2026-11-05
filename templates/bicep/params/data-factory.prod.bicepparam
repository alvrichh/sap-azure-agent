using '../data-factory.bicep'

// Production environment. No secrets here: secrets live in Key Vault.
param baseName = 'sapazprd'
param tags = {
  environment: 'prod'
  workload: 'sap-azure-integration'
  owner: '<team-or-email-alias>'
}
