# Azure Service Bus Test Environment Variables
#
# Usage: . .\set-test-env-vars.ps1

# ============================================
# CONFIGURE THESE VALUES
# ============================================
$SubscriptionId = "SUBSCRIPTION-ID"
$ResourceGroup = "RESOURCE-GROUP"
$NamespaceName = "NAMESPACE"
$SharedAccessKey = "SHARED-ACCESS-KEY"
$DomainName = "servicebus.windows.net"

# ============================================
# Test Mode
# ============================================
# Set to "true" to run live tests against actual Azure resources
# Remove or set to "false" to run in playback mode (uses recorded responses)
$env:AZURE_TEST_RUN_LIVE = "true"

# ============================================
# IMPORTANT: Enable Local Auth on Dynamic Namespaces
# ============================================
# The ServiceBusNamespacePreparer disables SAS key authentication when
# running locally (not in CI). Setting this env var makes it behave like CI.
# Without this, dynamically created namespaces will reject SAS key auth.
$env:AZURESUBSCRIPTION_SERVICE_CONNECTION_ID = "local-test"

# ============================================
# Azure Authentication
# ============================================
# Option 1: Use Azure CLI (recommended for local dev)
#   Just run 'az login' before running tests - no env vars needed
#   DefaultAzureCredential will use your CLI session

# Option 2: Service Principal (uncomment and fill in if needed)
# $env:AZURE_TENANT_ID = "your-tenant-id"
# $env:AZURE_CLIENT_ID = "your-client-id"
# $env:AZURE_CLIENT_SECRET = "your-client-secret"

$env:AZURE_SUBSCRIPTION_ID = $SubscriptionId

# ============================================
# Resource Group (skips creation if set)
# ============================================
$env:SERVICEBUS_RESOURCE_GROUP = $ResourceGroup

# ============================================
# Service Bus Namespace
# ============================================
$env:SERVICEBUS_CONNECTION_STR = "Endpoint=sb://$NamespaceName.$DomainName/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=$SharedAccessKey"
$env:SERVICEBUS_FULLY_QUALIFIED_NAMESPACE = "$NamespaceName.$DomainName"
$env:SERVICEBUS_ENDPOINT_SUFFIX = ".$DomainName"

# ============================================
# Optional: Resource Manager URL and Region
# ============================================
$env:SERVICEBUS_RESOURCE_MANAGER_URL = "https://management.azure.com/"
$env:RESOURCE_REGION = "southcentralus"

# ============================================
# Note: Queue, Topic, and Subscription entities
# are created dynamically by test preparers.
# No env vars needed for these resources.
# ============================================

Write-Host "Service Bus test environment variables set."