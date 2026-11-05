using '../../../templates/bicep/apim-sap-odata.bicep'

// Option B — own S/4HANA dev system through SAP Gateway. No secrets here.
// APIM must reach the SAP Gateway privately (VNet integration/injection, VPN or peering).
param apimName = 'apim-sapodata-dev-<suffix>'
param publisherEmail = '<team-or-email-alias>'
param publisherName = 'SAP integration team'
param skuName = 'Developer'
param keyVaultName = '<key-vault-name>'
param authMode = 's4hana'
param sapServiceRoot = 'https://<sap-gateway-host>:<port>/sap/opu/odata/sap/API_BUSINESS_PARTNER'
param sapClient = '100'
param sapUser = '<sap-technical-user>'
param sapPasswordSecretName = 'sap-odata-password'
param entraApiAudience = 'api://sap-odata-apim-test'
param tags = {
  environment: 'dev'
  workload: 'sap-odata-apim-test'
}
