// Event Hubs namespace + hub to receive Microsoft Graph change notifications without secrets.
// - Local (SAS) authentication disabled: Entra ID RBAC only.
// - Microsoft Graph Change Tracking (appId 0bf30f3b-4a52-48df-9a82-234910c4a086) gets "Azure Event Hubs Data Sender".
// - The consumer (your app, managed identity or test user) gets "Azure Event Hubs Data Receiver".
// Look up the Change Tracking service principal object ID in your tenant with:
//   az ad sp show --id 0bf30f3b-4a52-48df-9a82-234910c4a086 --query id -o tsv
// The deployer needs permission to create role assignments.

@description('Event Hubs namespace name (globally unique, 6-50 characters).')
@minLength(6)
@maxLength(50)
param namespaceName string

@description('Event hub name used in the Graph notificationUrl.')
param eventHubName string = 'graph-notifications'

@description('Azure region.')
param location string = resourceGroup().location

@description('Object ID of the "Microsoft Graph Change Tracking" service principal in this tenant.')
param graphChangeTrackingPrincipalId string

@description('Object ID of the identity that reads the notifications (managed identity, app or test user).')
param consumerPrincipalId string

@description('Principal type of the consumer.')
@allowed([
  'ServicePrincipal'
  'User'
  'Group'
])
param consumerPrincipalType string = 'ServicePrincipal'

@description('Tags applied to the namespace.')
param tags object = {}

var eventHubsDataSender = '2b629674-e913-4c01-ae53-ef4638d8f975'
var eventHubsDataReceiver = 'a638d3c7-ab3a-418d-83e6-5f17a39d4fde'

resource namespace 'Microsoft.EventHub/namespaces@2021-11-01' = {
  name: namespaceName
  location: location
  tags: tags
  sku: {
    name: 'Standard'
    tier: 'Standard'
    capacity: 1
  }
  properties: {
    disableLocalAuth: true
    minimumTlsVersion: '1.2'
  }
}

resource hub 'Microsoft.EventHub/namespaces/eventhubs@2021-11-01' = {
  parent: namespace
  name: eventHubName
  properties: {
    partitionCount: 2
    messageRetentionInDays: 1
  }
}

resource consumerGroup 'Microsoft.EventHub/namespaces/eventhubs/consumergroups@2021-11-01' = {
  parent: hub
  name: 'sap-approvals'
}

resource graphSender 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(hub.id, graphChangeTrackingPrincipalId, eventHubsDataSender)
  scope: hub
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', eventHubsDataSender)
    principalId: graphChangeTrackingPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource consumerReceiver 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(hub.id, consumerPrincipalId, eventHubsDataReceiver)
  scope: hub
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', eventHubsDataReceiver)
    principalId: consumerPrincipalId
    principalType: consumerPrincipalType
  }
}

@description('Fully qualified namespace, e.g. <name>.servicebus.windows.net')
output fullyQualifiedNamespace string = '${namespace.name}.servicebus.windows.net'

@description('Value for the Graph subscription notificationUrl (append ?tenantId=<primary-domain>).')
output graphNotificationUrlPrefix string = 'EventHub:https://${namespace.name}.servicebus.windows.net/eventhubname/${hub.name}'
