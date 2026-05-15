# Deployment guide

## Prerequisites

* Azure subscription with these resource providers registered: `Microsoft.App`, `Microsoft.CognitiveServices`, `Microsoft.DocumentDB`, `Microsoft.OperationalInsights`, `Microsoft.Insights`, `Microsoft.ContainerRegistry`, `Microsoft.ManagedIdentity`.
* Quota for **gpt-4o** (≥10K TPM) and **text-embedding-3-large** (≥120K TPM) in the chosen region.
* Local tools: `az` CLI ≥ 2.62, `bicep` ≥ 0.30, `docker`, `python` 3.11+, `node` 20+.

## One-shot deploy

```pwsh
./scripts/deploy.ps1 -Location eastus2 -EnvName ami-dev
```

This script will:

1. Run `az deployment sub create` against `infra/main.bicep`, creating `rg-<envName>` and all resources.
2. Build & push container images for `dashboard-api` and `dashboard-web` to the new ACR.
3. Re-deploy the Container Apps with the new images.
4. Write `outputs.json` with all endpoints and resource names.
5. Run `seed-foundry-agents.py` to register/update all eight agents in the Foundry project.

## Manual steps

### 1. Bicep deploy

```pwsh
az deployment sub create `
  --location eastus2 `
  --template-file infra/main.bicep `
  --parameters envName=ami-dev location=eastus2 `
  --query "properties.outputs" -o json > outputs.json
```

### 2. Build & push images

```pwsh
$acr = (Get-Content outputs.json | ConvertFrom-Json).acrLoginServer.value
az acr login --name $acr.Split('.')[0]
docker build -t "$acr/ami-dashboard-api:latest" apps/dashboard-api
docker build -t "$acr/ami-dashboard-web:latest" apps/dashboard-web
docker push "$acr/ami-dashboard-api:latest"
docker push "$acr/ami-dashboard-web:latest"
```

### 3. Update Container Apps

```pwsh
$rg = (Get-Content outputs.json | ConvertFrom-Json).resourceGroupName.value
az containerapp update -g $rg -n ami-dashboard-api --image "$acr/ami-dashboard-api:latest"
az containerapp update -g $rg -n ami-dashboard-web --image "$acr/ami-dashboard-web:latest"
```

### 4. Seed Foundry agents

```pwsh
pip install -r scripts/requirements.txt
python scripts/seed-foundry-agents.py --outputs outputs.json
```

## Pointing at an existing Foundry project

If you already have a Foundry project, set:

```pwsh
$env:FOUNDRY_PROJECT_ENDPOINT = "https://<account>.services.ai.azure.com/api/projects/<project>"
$env:AOAI_DEPLOYMENT_NAME = "gpt-4o"
python scripts/seed-foundry-agents.py --outputs outputs.json
```

You can also pass `-SkipFoundry` to `deploy.ps1` to skip provisioning a new Foundry account.

## Tear down

```pwsh
az group delete -n rg-ami-dev --yes --no-wait
```
