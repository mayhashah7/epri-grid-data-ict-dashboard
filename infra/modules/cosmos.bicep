param location string
param envName string
param tags object
param uamiPrincipalId string

var accountName = toLower('cosmos-ami-${envName}')
var databaseName = 'ami'

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-08-15' = {
  name: accountName
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [ { locationName: location, failoverPriority: 0, isZoneRedundant: false } ]
    capabilities: [ { name: 'EnableServerless' } ]
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
    enableAutomaticFailover: false
  }
}

resource db 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-08-15' = {
  parent: cosmos
  name: databaseName
  properties: { resource: { id: databaseName } }
}

var containers = [
  { name: 'meters',  pk: '/substation_id', ttl: -1 }
  { name: 'reads',   pk: '/meter_id',      ttl: 604800 }
  { name: 'events',  pk: '/substation_id', ttl: 2592000 }
  { name: 'cases',   pk: '/case_id',       ttl: -1 }
  { name: 'traces',  pk: '/case_id',       ttl: 2592000 }
]

resource cosmosContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-08-15' = [for c in containers: {
  parent: db
  name: c.name
  properties: {
    resource: {
      id: c.name
      partitionKey: { paths: [ c.pk ], kind: 'Hash' }
      defaultTtl: c.ttl
    }
  }
}]

// Built-in Cosmos DB Data Contributor role
var cosmosDataContributorRoleId = '00000000-0000-0000-0000-000000000002'
resource uamiDataRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-08-15' = {
  parent: cosmos
  name: guid(cosmos.id, uamiPrincipalId, cosmosDataContributorRoleId)
  properties: {
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/${cosmosDataContributorRoleId}'
    principalId: uamiPrincipalId
    scope: cosmos.id
  }
}

output endpoint string = cosmos.properties.documentEndpoint
output name string = cosmos.name
output databaseName string = databaseName
