// Microsoft Fabric capacity (F SKU). Billed while running: pause it when not in use
// (az fabric capacity suspend / resume, or the Azure portal).

@description('Capacity name: 3-63 characters, lowercase letters and numbers, starting with a letter.')
@minLength(3)
@maxLength(63)
param capacityName string

@description('Azure region. Keep it in the same region as the data (ADLS Gen2) to avoid egress and latency.')
param location string = resourceGroup().location

@description('Fabric SKU, e.g. F2 (dev/test) up to F2048. Size it with the Fabric capacity estimator.')
@allowed([
  'F2'
  'F4'
  'F8'
  'F16'
  'F32'
  'F64'
  'F128'
  'F256'
  'F512'
  'F1024'
  'F2048'
])
param skuName string = 'F2'

@description('Capacity administrators (user principal names, e.g. admin@contoso.com).')
@minLength(1)
param adminMembers array

@description('Tags applied to the capacity.')
param tags object = {}

resource capacity 'Microsoft.Fabric/capacities@2023-11-01' = {
  name: capacityName
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: 'Fabric'
  }
  properties: {
    administration: {
      members: adminMembers
    }
  }
}

@description('Resource ID of the Fabric capacity.')
output capacityId string = capacity.id

@description('Name of the Fabric capacity (use it when assigning workspaces).')
output capacityName string = capacity.name
