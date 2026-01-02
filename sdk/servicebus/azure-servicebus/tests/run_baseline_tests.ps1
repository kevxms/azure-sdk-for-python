# Usage: . .\set-test-env-vars.ps1; .\run_baseline_tests.ps1 -v 2>&1 | Tee-Object -FilePath out_baseline_tests_int.log

Push-Location $PSScriptRoot

Write-Host "========== Environment Variables ==========" -ForegroundColor Cyan
$envVars = @(
    "AZURE_CLIENT_CERTIFICATE_PATH",
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SEND_CERTIFICATE_CHAIN",
    "AZURE_SUBSCRIPTION_ID",
    "AZURE_TENANT_ID",
    "AZURE_TEST_RUN_LIVE",
    "AZURESUBSCRIPTION_SERVICE_CONNECTION_ID",
    "OVERRIDE_AUTH_AAD_TO_SAS",
    "RESOURCE_REGION",
    "SERVICEBUS_CONNECTION_STR",
    "SERVICEBUS_ENDPOINT_SUFFIX",
    "SERVICEBUS_FULLY_QUALIFIED_NAMESPACE",
    "SERVICEBUS_RESOURCE_GROUP",
    "SERVICEBUS_RESOURCE_MANAGER_URL",
    "SERVICEBUS_RP_CERT_KEYVAULT_URI",
    "SERVICEBUS_RP_HOST"
)
foreach ($var in $envVars) {
    $val = [Environment]::GetEnvironmentVariable($var)
    if ($val) {
        # Mask connection string and certificate path for security
        if ($var -match "CONNECTION_STR|CERTIFICATE_PATH") {
            $val = $val.Substring(0, [Math]::Min(40, $val.Length)) + "..."
        }
        Write-Host "$var = $val"
    } else {
        Write-Host "$var = (not set)" -ForegroundColor DarkGray
    }
}
Write-Host "==========================================`n" -ForegroundColor Cyan

$tests = Get-Content baseline_tests_int.txt | Where-Object { $_.Trim() -ne "" }
$total = $tests.Count
$i = 0

foreach ($test in $tests) {
    $i++
    Write-Host "`n[$i/$total] $test" -ForegroundColor Cyan
    python -m pytest $test @args
}

Pop-Location