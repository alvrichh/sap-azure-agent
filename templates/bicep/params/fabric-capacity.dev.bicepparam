using '../fabric-capacity.bicep'

param capacityName = 'fabsapazdev'
param skuName = 'F2'
param adminMembers = [
  '<admin-upn@contoso.com>'
]
param tags = {
  environment: 'dev'
  workload: 'sap-azure-integration'
  owner: '<team-or-email-alias>'
}
