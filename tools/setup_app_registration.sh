#!/usr/bin/env bash
# One-time: app registration + service principal for the KI-Register automation. Run after `az login`.
# Prints the APPLICATION (client) ID and TENANT ID; the secret is printed ONCE by Azure CLI: copy it into .env, never into chat.
set -euo pipefail
NAME="ki-register-automation"
APP_ID=$(az ad app list --display-name "$NAME" --query "[0].appId" -o tsv)
if [ -z "$APP_ID" ]; then
  APP_ID=$(az ad app create --display-name "$NAME" --sign-in-audience AzureADMyOrg --query appId -o tsv)
  az ad sp create --id "$APP_ID" >/dev/null
fi
echo "TENANT_ID=$(az account show --query tenantId -o tsv)"
echo "CLIENT_ID=$APP_ID"
echo "Secret (einmalig, danach in .env eintragen):"
az ad app credential reset --id "$APP_ID" --display-name "kiregister $(date +%Y-%m)" --years 1 --query password -o tsv
