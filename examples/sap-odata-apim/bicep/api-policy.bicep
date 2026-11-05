// Applies the test-case policy to the imported API (run after `az apim api import`).

@description('API Management instance name.')
param apimName string

@description('API identifier used at import time.')
param apiId string = 'sap-business-partner'

@description('Which policy to apply.')
@allowed([
  'sandbox'
  's4hana'
])
param authMode string

var policyXml = authMode == 's4hana' ? loadTextContent('../apim/policy-s4hana.xml') : loadTextContent('../apim/policy-sandbox.xml')

resource apim 'Microsoft.ApiManagement/service@2022-08-01' existing = {
  name: apimName
}

resource api 'Microsoft.ApiManagement/service/apis@2022-08-01' existing = {
  parent: apim
  name: apiId
}

resource policy 'Microsoft.ApiManagement/service/apis/policies@2022-08-01' = {
  parent: api
  name: 'policy'
  properties: {
    format: 'xml'
    value: policyXml
  }
}
