using '../../../templates/bicep/data-factory.bicep'

// Test case S/4HANA -> Fabric (dev). No secrets here.
param baseName = 's4fdev'
param tags = {
  environment: 'dev'
  workload: 's4hana-to-fabric-test'
  owner: '<team-or-email-alias>'
}
