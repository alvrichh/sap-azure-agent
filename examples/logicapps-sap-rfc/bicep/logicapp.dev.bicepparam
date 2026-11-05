using '../../../templates/bicep/logicapp-standard-sap.bicep'

// Test case: Logic Apps Standard + SAP RFC (dev). No secrets here.
param logicAppName = 'logic-sap-rfc-dev-<suffix>'
param integrationSubnetId = '<integration-subnet-resource-id>'
param keyVaultName = '<key-vault-name>'
param sapPasswordSecretName = 'sap-rfc-password'
param sapAppServerHost = '<sap-app-server-host>'
param sapSystemNumber = '<system-number>'
param sapClient = '100'
param sapUser = 'RFC_LOGICAPP'
param sapLanguage = 'EN'
param tags = {
  environment: 'dev'
  workload: 'logicapps-sap-rfc-test'
}
