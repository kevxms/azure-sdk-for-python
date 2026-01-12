# Azure Event Hubs Test Environment Variables
#
# Usage: . .\set-test-env-vars.ps1

# Existing namespace details
$SubscriptionId = "<MY_SUBSCRIPTION_ID>"
$ResourceGroup = "<MY_RESOURCE_GROUP>"
$NamespaceName = "<MY_EVENTHUB_NAMESPACE>"
$SharedAccessKey = "<MY_SHARED_ACCESS_KEY>"

# Optional: Resource Manager URL and Region
$env:EVENTHUB_RESOURCE_MANAGER_URL = "https://management.azure.com/"
$env:RESOURCE_REGION = "swedencentral"
$DomainName = "servicebus.windows.net"

# ============================================
# Direct REST Client (bypasses ARM)
# Set these to use direct RP endpoint instead of ARM
# e.g. $env:EVENTHUB_RP_HOST = "swedencentral03.int.messaging.azure-int.net:44300"
# e.g. $env:EVENTHUB_RP_CERT_KEYVAULT_URI = "https://servicebustestkeyvault.vault.azure.net/certificates/AcisClientAuthCertForInt"
# ============================================
# $env:EVENTHUB_RP_HOST = "<your-rp-host:port>"
# $env:EVENTHUB_RP_CERT_KEYVAULT_URI = "<your-keyvault-certificate-uri>"
Remove-Item Env:EVENTHUB_RP_HOST -ErrorAction SilentlyContinue
Remove-Item Env:EVENTHUB_RP_CERT_KEYVAULT_URI -ErrorAction SilentlyContinue

# Azure Authentication Option 1: Use Azure CLI
#   Just run 'az login' before running tests. No env vars needed
#   DefaultAzureCredential will use your CLI session

# Azure Authentication Option 2: Service Principal
$env:AZURE_TENANT_ID = "<MY_TENANT_ID>"
$env:AZURE_CLIENT_ID = "<MY_CLIENT_ID>"
$env:AZURE_CLIENT_CERTIFICATE_PATH = "<PATH_TO_MY_CERTIFICATE.PFX>"
$env:AZURE_CLIENT_SEND_CERTIFICATE_CHAIN = "true"

# Set to "true" to run live tests against actual Azure resources
# Remove or set to "false" to run in playback mode (uses recorded responses)
$env:AZURE_TEST_RUN_LIVE = "true"

# Existing namespace
$env:AZURE_SUBSCRIPTION_ID = $SubscriptionId
$env:EVENTHUB_RESOURCE_GROUP = $ResourceGroup
$env:EVENT_HUB_NAMESPACE = $NamespaceName
$env:EVENT_HUB_CONN_STR = "Endpoint=sb://$NamespaceName.$DomainName/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=$SharedAccessKey"
$env:EVENT_HUB_HOSTNAME = "$NamespaceName.$DomainName"
$env:EVENT_HUB_ENDPOINT_SUFFIX = ".$DomainName"

# Optional: Storage Account for Checkpoint Store
# $env:AZURE_STORAGE_ACCOUNT = "your-storage-account-name"