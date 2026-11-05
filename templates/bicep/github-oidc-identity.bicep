// User-assigned managed identity for GitHub Actions, trusted through workload
// identity federation (OIDC). No client secret is created.
// Deploy at resource-group scope; the identity gets the given role on that resource group.
// The deploying user needs permission to create role assignments (Owner, User Access
// Administrator or Role Based Access Control Administrator).

@description('Name of the user-assigned managed identity.')
param identityName string

@description('Azure region.')
param location string = resourceGroup().location

@description('GitHub organization or user that owns the repository.')
param githubOwner string

@description('GitHub repository name.')
param githubRepo string

@description('Federated subject suffix, e.g. "ref:refs/heads/main", "environment:production" or "pull_request".')
param subjectSuffix string = 'ref:refs/heads/main'

@description('Built-in role definition ID to grant on this resource group. Default: Contributor. Prefer a narrower role when possible.')
param roleDefinitionId string = 'b24988ac-6180-42a0-ab88-20f7382dd24c'

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
}

resource githubCredential 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: identity
  name: 'github-${uniqueString(subjectSuffix)}'
  properties: {
    issuer: 'https://token.actions.githubusercontent.com'
    subject: 'repo:${githubOwner}/${githubRepo}:${subjectSuffix}'
    audiences: [
      'api://AzureADTokenExchange'
    ]
  }
}

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, identity.id, roleDefinitionId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitionId)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Values to store as GitHub secrets/variables (identifiers, not credentials).
output AZURE_CLIENT_ID string = identity.properties.clientId
output AZURE_TENANT_ID string = identity.properties.tenantId
output AZURE_SUBSCRIPTION_ID string = subscription().subscriptionId
