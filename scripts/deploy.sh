#!/usr/bin/env bash
# Bash mirror of deploy.ps1
set -euo pipefail

LOCATION="${1:-eastus2}"
ENV_NAME="${2:-ami-dev}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "▶ Deploy infra: $ENV_NAME / $LOCATION"
az deployment sub create \
  --location "$LOCATION" \
  --template-file "$REPO_ROOT/infra/main.bicep" \
  --parameters envName="$ENV_NAME" location="$LOCATION" \
  --query "properties.outputs" -o json > "$REPO_ROOT/outputs.json"

ACR=$(jq -r '.acrLoginServer.value' "$REPO_ROOT/outputs.json")
RG=$(jq -r '.resourceGroupName.value' "$REPO_ROOT/outputs.json")
WEB=$(jq -r '.dashboardWebUrl.value' "$REPO_ROOT/outputs.json")

echo "▶ Build & push images"
az acr login -n "${ACR%%.*}"
docker build -t "$ACR/ami-dashboard-api:latest" -f "$REPO_ROOT/apps/dashboard-api/Dockerfile" "$REPO_ROOT"
docker build -t "$ACR/ami-dashboard-web:latest" -f "$REPO_ROOT/apps/dashboard-web/Dockerfile" "$REPO_ROOT"
docker push "$ACR/ami-dashboard-api:latest"
docker push "$ACR/ami-dashboard-web:latest"

echo "▶ Update Container Apps"
az containerapp update -g "$RG" -n ami-dashboard-api --image "$ACR/ami-dashboard-api:latest" -o none
az containerapp update -g "$RG" -n ami-dashboard-web --image "$ACR/ami-dashboard-web:latest" -o none

echo "▶ Seed Foundry agents"
python -m pip install -q -r "$REPO_ROOT/scripts/requirements.txt"
python -m pip install -q -e "$REPO_ROOT/agents/tools"
python "$REPO_ROOT/scripts/seed-foundry-agents.py" --outputs "$REPO_ROOT/outputs.json"

echo ""
echo "✓ Dashboard: $WEB"
