// foundry.bicep — Azure AI Foundry (CognitiveServices-based, no Hub)
// Provisions an AIServices account with a Foundry project, gpt-4o, and embeddings.

param location string
param envName string
param tags object
param uamiId string
param uamiPrincipalId string

var aiServicesName = toLower('ais-ami-${envName}')
var projectName = 'proj-ami-${envName}'
var subDomain = toLower(replace('ais-ami-${envName}', '-', ''))

resource aiServices 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: aiServicesName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uamiId}': {} }
  }
  properties: {
    customSubDomainName: subDomain
    publicNetworkAccess: 'Enabled'
    allowProjectManagement: true
    disableLocalAuth: false
  }
}

resource gpt4o 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aiServices
  name: 'gpt-4o'
  sku: { name: 'GlobalStandard', capacity: 30 }
  properties: {
    model: { format: 'OpenAI', name: 'gpt-4o', version: '2024-11-20' }
  }
}

resource embeddings 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aiServices
  name: 'text-embedding-3-large'
  sku: { name: 'Standard', capacity: 50 }
  properties: {
    model: { format: 'OpenAI', name: 'text-embedding-3-large', version: '1' }
  }
  dependsOn: [ gpt4o ]
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: aiServices
  name: projectName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uamiId}': {} }
  }
  properties: {}
}

// Cognitive Services OpenAI Contributor on the account
var csOpenAIContribRoleId = 'a001fd3d-188f-4b5d-821b-7da978bf7442'
resource uamiAccountRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: aiServices
  name: guid(aiServices.id, uamiId, csOpenAIContribRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', csOpenAIContribRoleId)
    principalId: uamiPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Azure AI Developer on the project
var aiDeveloperRoleId = '64702f94-c441-49e6-a78b-ef80e0188fee'
resource uamiProjectRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: project
  name: guid(project.id, uamiId, aiDeveloperRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', aiDeveloperRoleId)
    principalId: uamiPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output projectName string = project.name
output aiServicesName string = aiServices.name
output aoaiEndpoint string = aiServices.properties.endpoint
output aoaiDeploymentName string = gpt4o.name
output embeddingsDeploymentName string = embeddings.name
output projectEndpoint string = 'https://${subDomain}.services.ai.azure.com/api/projects/${project.name}'
