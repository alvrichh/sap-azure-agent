using '../../../templates/bicep/eventhubs-graph-notifications.bicep'

param namespaceName = 'evhns-sapteams-dev-<suffix>'
param eventHubName = 'graph-notifications'
// az ad sp show --id 0bf30f3b-4a52-48df-9a82-234910c4a086 --query id -o tsv
param graphChangeTrackingPrincipalId = '<graph-change-tracking-sp-object-id>'
// The tester's object ID for the test (az ad signed-in-user show --query id -o tsv)
param consumerPrincipalId = '<tester-object-id>'
param consumerPrincipalType = 'User'
param tags = {
  environment: 'dev'
  workload: 'sap-teams-approvals-test'
}
