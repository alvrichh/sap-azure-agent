using '../../../templates/bicep/apim-sap-odata.bicep'

// Option A — SAP Business Accelerator Hub sandbox (read-only). No secrets here.
param apimName = 'apim-sapodata-dev-<suffix>'
param publisherEmail = '<team-or-email-alias>'
param publisherName = 'SAP integration team'
param skuName = 'Developer'
param keyVaultName = '<key-vault-name>'
param authMode = 'sandbox'
param sapServiceRoot = 'https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap/API_BUSINESS_PARTNER'
param sapApiKeySecretName = 'sap-sandbox-apikey'
param entraApiAudience = 'api://sap-odata-apim-test'
param tags = {
  environment: 'dev'
  workload: 'sap-odata-apim-test'
}
