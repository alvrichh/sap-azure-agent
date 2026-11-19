using '../../../templates/bicep/apim-sap-odata.bicep'

// Option A — SAP Business Accelerator Hub sandbox, purchase order API (read-only). No secrets here.
param apimName = 'apim-sappo-dev-<suffix>'
param publisherEmail = '<team-or-email-alias>'
param publisherName = 'SAP integration team'
param skuName = 'Developer'
param keyVaultName = '<key-vault-name>'
param authMode = 'sandbox'
param sapServiceRoot = 'https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV'
param sapApiKeySecretName = 'sap-sandbox-apikey'
param entraApiAudience = 'api://sap-po-agent'
param tags = {
  environment: 'dev'
  workload: 'foundry-sap-po-agent'
}
