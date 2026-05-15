<#
.SYNOPSIS
  One-shot deploy: Bicep → ACR build/push → Container Apps update → seed Foundry agents.
.PARAMETER Location
  Azure region. Default: eastus2.
.PARAMETER EnvName
  Short env suffix used in resource names. Default: ami-dev.
.PARAMETER SkipBuild
  Skip docker build/push (use placeholder images).
.PARAMETER SkipFoundry
  Don't provision a new Foundry account; expects FoundryEndpoint param.
.PARAMETER FoundryEndpoint
  Existing Foundry project endpoint, e.g. https://<a>.services.ai.azure.com/api/projects/<p>
#>
param(
  [string]$Location = "eastus2",
  [string]$EnvName  = "ami-dev",
  [switch]$SkipBuild,
  [switch]$SkipFoundry,
  [string]$FoundryEndpoint = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent

Write-Host "▶ Deploy infra: $EnvName / $Location" -ForegroundColor Cyan
$bicepArgs = @(
  "deployment", "sub", "create",
  "--location", $Location,
  "--template-file", "$RepoRoot/infra/main.bicep",
  "--parameters", "envName=$EnvName", "location=$Location"
)
if ($SkipFoundry) {
  if (-not $FoundryEndpoint) { throw "When -SkipFoundry, pass -FoundryEndpoint." }
  $bicepArgs += "provisionFoundry=false"
  $bicepArgs += "foundryProjectEndpointOverride=$FoundryEndpoint"
}
$bicepArgs += "--query", "properties.outputs", "-o", "json"

$outputs = az @bicepArgs | ConvertFrom-Json
if (-not $outputs) { throw "Bicep deploy returned no outputs." }
$outputs | ConvertTo-Json -Depth 6 | Set-Content -Path "$RepoRoot/outputs.json"
Write-Host "✓ outputs.json written" -ForegroundColor Green

$Acr      = $outputs.acrLoginServer.value
$RG       = $outputs.resourceGroupName.value
$ApiUrl   = $outputs.dashboardApiUrl.value
$WebUrl   = $outputs.dashboardWebUrl.value
$Foundry  = $outputs.foundryProjectEndpoint.value

if (-not $SkipBuild) {
  Write-Host "▶ Build & push images to $Acr" -ForegroundColor Cyan
  az acr login -n $Acr.Split('.')[0]
  Push-Location $RepoRoot
  docker build -t "$Acr/ami-dashboard-api:latest" -f apps/dashboard-api/Dockerfile .
  docker build -t "$Acr/ami-dashboard-web:latest" -f apps/dashboard-web/Dockerfile .
  docker push "$Acr/ami-dashboard-api:latest"
  docker push "$Acr/ami-dashboard-web:latest"
  Pop-Location
  Write-Host "▶ Update Container Apps to new images" -ForegroundColor Cyan
  az containerapp update -g $RG -n ami-dashboard-api --image "$Acr/ami-dashboard-api:latest" --output none
  az containerapp update -g $RG -n ami-dashboard-web --image "$Acr/ami-dashboard-web:latest" --output none
}

Write-Host "▶ Seed Foundry agents" -ForegroundColor Cyan
python -m pip install -q -r "$RepoRoot/scripts/requirements.txt"
python -m pip install -q -e "$RepoRoot/agents/tools"
python "$RepoRoot/scripts/seed-foundry-agents.py" --outputs "$RepoRoot/outputs.json"

Write-Host ""
Write-Host "─────────────────────────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host "  ✓ Dashboard:  $WebUrl"   -ForegroundColor Green
Write-Host "  ✓ API:        $ApiUrl"   -ForegroundColor Green
Write-Host "  ✓ Foundry:    $Foundry"  -ForegroundColor Green
Write-Host "─────────────────────────────────────────────────────────────" -ForegroundColor DarkGray
