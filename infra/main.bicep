// main.bicep — AMI Agentic Dashboard, subscription-scoped entry point.
// Usage:
//   az deployment sub create \
//     --location eastus2 \
//     --template-file infra/main.bicep \
//     --parameters envName=ami-dev location=eastus2

targetScope = 'subscription'

@description('Short environment name used as suffix for all resources.')
param envName string = 'ami-dev'

@description('Azure region for all resources.')
param location string = 'eastus2'

@description('Container image for dashboard-api. Defaults to quickstart placeholder; replaced after first ACR build.')
param dashboardApiImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('Container image for dashboard-web. Defaults to quickstart placeholder; replaced after first ACR build.')
param dashboardWebImage string = 'mcr.microsoft.com/k8se/quickstart-react:latest'

@description('When true, provision a new Foundry account. When false, set foundryProjectEndpointOverride.')
param provisionFoundry bool = true

@description('If provisionFoundry=false, the existing Foundry project endpoint to wire into the API container.')
param foundryProjectEndpointOverride string = ''

@description('Tags applied to every resource.')
param tags object = {
  project: 'ami-agentic-dashboard'
  env: envName
  managedBy: 'bicep'
  workload: 'utility-ami'
}

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${envName}'
  location: location
  tags: tags
}

module identity 'modules/identity.bicep' = {
  name: 'identity'
  scope: rg
  params: { location: location, envName: envName, tags: tags }
}

module monitor 'modules/monitor.bicep' = {
  name: 'monitor'
  scope: rg
  params: { location: location, envName: envName, tags: tags }
}

module acr 'modules/acr.bicep' = {
  name: 'acr'
  scope: rg
  params: {
    location: location
    envName: envName
    tags: tags
    uamiPrincipalId: identity.outputs.principalId
  }
}

module cosmos 'modules/cosmos.bicep' = {
  name: 'cosmos'
  scope: rg
  params: {
    location: location
    envName: envName
    tags: tags
    uamiPrincipalId: identity.outputs.principalId
  }
}

module foundry 'modules/foundry.bicep' = if (provisionFoundry) {
  name: 'foundry'
  scope: rg
  params: {
    location: location
    envName: envName
    tags: tags
    uamiId: identity.outputs.id
    uamiPrincipalId: identity.outputs.principalId
  }
}

var resolvedFoundryEndpoint = provisionFoundry ? foundry!.outputs.projectEndpoint : foundryProjectEndpointOverride
var resolvedAoaiDeployment = provisionFoundry ? foundry!.outputs.aoaiDeploymentName : 'gpt-4o'

module containerapps 'modules/containerapps.bicep' = {
  name: 'containerapps'
  scope: rg
  params: {
    location: location
    envName: envName
    tags: tags
    uamiId: identity.outputs.id
    uamiClientId: identity.outputs.clientId
    workspaceId: monitor.outputs.workspaceId
    workspaceCustomerId: monitor.outputs.workspaceCustomerId
    workspaceSharedKey: monitor.outputs.workspaceSharedKey
    appInsightsConnectionString: monitor.outputs.appInsightsConnectionString
    acrLoginServer: acr.outputs.loginServer
    cosmosEndpoint: cosmos.outputs.endpoint
    cosmosDatabaseName: cosmos.outputs.databaseName
    foundryProjectEndpoint: resolvedFoundryEndpoint
    aoaiDeploymentName: resolvedAoaiDeployment
    dashboardApiImage: dashboardApiImage
    dashboardWebImage: dashboardWebImage
  }
}

output resourceGroupName string  = rg.name
output dashboardWebUrl string    = 'https://${containerapps.outputs.webFqdn}'
output dashboardApiUrl string    = 'https://${containerapps.outputs.apiFqdn}'
output acrLoginServer string     = acr.outputs.loginServer
output cosmosEndpoint string     = cosmos.outputs.endpoint
output cosmosDatabaseName string = cosmos.outputs.databaseName
output foundryProjectEndpoint string = resolvedFoundryEndpoint
output aoaiDeploymentName string = resolvedAoaiDeployment
output uamiClientId string       = identity.outputs.clientId
output uamiPrincipalId string    = identity.outputs.principalId
