using '../../../templates/bicep/apim-sap-odata.bicep'

// Option B — own S/4HANA dev system, purchase order API through SAP Gateway. No secrets here:
// the SAP password stays in Key Vault (secret sap-odata-password).
param apimName = 'apim-sappo-dev-<suffix>'
param publisherEmail = '<team-or-email-alias>'
param publisherName = 'SAP integration team'
param skuName = 'Developer'
param keyVaultName = '<key-vault-name>'
param authMode = 's4hana'
param sapServiceRoot = 'https://<sap-gateway-host>:<https-port>/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV'
param sapClient = '<sap-client>'
param sapUser = '<display-only-technical-user>'
param sapPasswordSecretName = 'sap-odata-password'
param entraApiAudience = 'api://sap-po-agent'
param tags = {
  environment: 'dev'
  workload: 'foundry-sap-po-agent'
}
