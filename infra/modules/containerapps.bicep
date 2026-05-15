param location string
param envName string
param tags object
param uamiId string
param uamiClientId string
#disable-next-line no-unused-params
param workspaceId string
param workspaceCustomerId string
@secure()
param workspaceSharedKey string
@secure()
param appInsightsConnectionString string
param acrLoginServer string
param cosmosEndpoint string
param cosmosDatabaseName string
param foundryProjectEndpoint string
param aoaiDeploymentName string
param dashboardApiImage string
param dashboardWebImage string

var envResourceName = 'cae-ami-${envName}'
var apiAppName = 'ami-dashboard-api'
var webAppName = 'ami-dashboard-web'

resource cae 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envResourceName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspaceCustomerId
        sharedKey: workspaceSharedKey
      }
    }
    workloadProfiles: [
      { name: 'Consumption', workloadProfileType: 'Consumption' }
    ]
    zoneRedundant: false
  }
}

resource apiApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: apiAppName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uamiId}': {} }
  }
  properties: {
    managedEnvironmentId: cae.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
        corsPolicy: {
          allowedOrigins: [ '*' ]
          allowedMethods: [ 'GET', 'POST', 'OPTIONS' ]
          allowedHeaders: [ '*' ]
        }
      }
      registries: [
        { server: acrLoginServer, identity: uamiId }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: dashboardApiImage
          resources: { cpu: json('1.0'), memory: '2Gi' }
          env: [
            { name: 'AZURE_CLIENT_ID', value: uamiClientId }
            { name: 'COSMOS_ENDPOINT', value: cosmosEndpoint }
            { name: 'COSMOS_DATABASE', value: cosmosDatabaseName }
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryProjectEndpoint }
            { name: 'AOAI_DEPLOYMENT_NAME', value: aoaiDeploymentName }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
            { name: 'AMI_METER_COUNT', value: '50000' }
            { name: 'AMI_SUBSTATION_COUNT', value: '12' }
            { name: 'ENABLE_SIMULATOR', value: 'true' }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

resource webApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: webAppName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uamiId}': {} }
  }
  properties: {
    managedEnvironmentId: cae.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 80
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        { server: acrLoginServer, identity: uamiId }
      ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: dashboardWebImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'API_BASE_URL', value: 'https://${apiApp.properties.configuration.ingress.fqdn}' }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
}

output apiFqdn string = apiApp.properties.configuration.ingress.fqdn
output webFqdn string = webApp.properties.configuration.ingress.fqdn
output environmentName string = cae.name
