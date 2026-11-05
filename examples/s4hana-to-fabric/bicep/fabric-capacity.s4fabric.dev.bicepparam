using '../../../templates/bicep/fabric-capacity.bicep'

// F2 is enough for the test volume. Pause it when the test is finished.
param capacityName = 'fabs4fdev'
param skuName = 'F2'
param adminMembers = [
  '<admin-upn@contoso.com>'
]
param tags = {
  environment: 'dev'
  workload: 's4hana-to-fabric-test'
  owner: '<team-or-email-alias>'
}
