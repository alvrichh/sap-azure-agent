using '../../../templates/bicep/logicapp-standard-sap.bicep'

// Test case: Logic Apps Standard + SAP IDoc (dev). No secrets here.
param logicAppName = 'logic-sap-idoc-dev-<suffix>'
param integrationSubnetId = '<integration-subnet-resource-id>'
param keyVaultName = '<key-vault-name>'
param sapPasswordSecretName = 'sap-idoc-password'
param sapAppServerHost = '<sap-app-server-host>'
param sapSystemNumber = '<system-number>'
param sapClient = '100'
param sapUser = 'RFC_IDOC_LA'
param sapLanguage = 'EN'

// Stateful mode: the SAP trigger, "Respond to SAP server" and sendIDoc with a Transaction ID need VNet private ports.
param vnetPrivatePortsCount = 2

param additionalAppSettings = {
  // Registered server program (SAP -> Azure); must match SM59 and the SMGW ACL, case-sensitive
  SAP_GATEWAY_HOST: '<sap-gateway-host>'
  SAP_GATEWAY_SERVICE: '<sap-gateway-service>'
  SAP_PROGRAM_ID: 'LOGICAPP_IDOC_DEV'
  // Control record for IDocs sent to SAP (partner profile WE20 / ports WE21 / logical systems BD54)
  SAP_IDOC_SENDER_PORT: '<sender-port>'
  SAP_IDOC_SENDER_PARTNER: 'LOGICAPP'
  SAP_IDOC_RECEIVER_PORT: 'SAPS4P'
  SAP_IDOC_RECEIVER_PARTNER: '<sap-logical-system>'
  // Downstream API that receives the customer master data (called with the app's managed identity)
  CUSTOMER_API_URL: '<customer-api-url>'
  CUSTOMER_API_AUDIENCE: '<customer-api-app-id-uri>'
}

param tags = {
  environment: 'dev'
  workload: 'logicapps-sap-idoc-test'
}
