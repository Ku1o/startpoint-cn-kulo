param([string]$DataDirectory, [string]$LanHost)
$ErrorActionPreference = 'Stop'
$loginRepo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
if (-not $DataDirectory) {
    $DataDirectory = [IO.Path]::GetFullPath((Join-Path $loginRepo '../work/player-login-20260910/server-data'))
}
if (-not $LanHost) {
    $loginConfig = Get-Content -LiteralPath (Join-Path $loginRepo 'outputs/android-build-local.json') -Raw | ConvertFrom-Json
    $LanHost = $loginConfig.lan_host -replace ':\d+$', ''
}
if (-not $LanHost -or $LanHost -match '[/\s:]') { throw 'Provide the LAN host without scheme or port.' }
if (Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in 8002,8013 }) {
    throw 'Test port 8002 or 8013 is already in use. Reuse the running test service or stop that service first.'
}
$loginEnvironment = @{
    DATA_DIR=[IO.Path]::GetFullPath($DataDirectory)
    CN_LISTEN_HOST='0.0.0.0'; CN_LISTEN_PORT='8002'
    SESSION_HOST='0.0.0.0'; SESSION_PORT='8013'
    SESSION_PUBLIC_HOST=$LanHost; CN_PUBLIC_HOST=$LanHost
    CN_LOCAL_CLIENT_PLATFORM='android'; LOG_LEVEL='warn'
}
# This credential belongs only to this isolated local trial. Preserve an explicit process override.
$loginCredentialPath = [IO.Path]::GetFullPath((Join-Path $loginRepo '../.codex/secrets/player-login-lan-trial.credential.xml'))
if (-not $env:ADMIN_PANEL_PASSWORD -and (Test-Path -LiteralPath $loginCredentialPath)) {
    $loginCredential = Import-Clixml -LiteralPath $loginCredentialPath
    $loginEnvironment.ADMIN_PANEL_PASSWORD = $loginCredential.GetNetworkCredential().Password
    $loginCredential = $null
}
$loginPrior = @{}
foreach ($loginKey in $loginEnvironment.Keys) {
    $loginPrior[$loginKey] = [Environment]::GetEnvironmentVariable($loginKey, 'Process')
    [Environment]::SetEnvironmentVariable($loginKey, $loginEnvironment[$loginKey], 'Process')
}
Push-Location $loginRepo
try {
    Write-Host "Player login trial: http://${LanHost}:8002 / TCP 8013"
    Write-Host "Isolated test data: $($loginEnvironment.DATA_DIR)"
    Write-Host 'Use Ctrl+C to stop. Management login uses the process override or the local trial credential.'
    & node -r ts-node/register/transpile-only src/cn-server.ts
    if ($LASTEXITCODE -ne 0) { throw "Test service exited with code $LASTEXITCODE" }
} finally {
    Pop-Location
    foreach ($loginKey in $loginEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($loginKey, $loginPrior[$loginKey], 'Process')
    }
    $loginEnvironment.Clear()
}
