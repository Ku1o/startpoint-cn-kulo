param(
    [ValidateRange(1, 3650)]
    [int]$RetentionDays = 30,
    [switch]$Foreground
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
if (Test-Path -LiteralPath (Join-Path $projectRoot ".storage-maintenance\active.lock")) {
    throw "Storage maintenance is still active. Inspect .storage-maintenance/active.lock. For time-content-deployment use scripts/migrate-time-content.ps1 -Mode Recover; other storage maintenance uses maintain-cn-recover.bat."
}
$envFilePath = Join-Path $projectRoot ".env"
if (!(Test-Path -LiteralPath $envFilePath -PathType Leaf)) { throw "Missing server configuration: $envFilePath" }
if (!(Test-Path -LiteralPath (Join-Path $projectRoot 'out/cn-server.js') -PathType Leaf)) {
    throw "Missing out/cn-server.js. Build the server before starting it."
}

# Both entry points use the same runtime selection. A broken explicit override
# is an error, rather than an instruction to silently choose another runtime.
if ($env:STARPOINT_NODE24) {
    $nodeExecutable = Join-Path $env:STARPOINT_NODE24 'node.exe'
} elseif (Test-Path -LiteralPath (Join-Path $projectRoot 'tools/node24/node.exe') -PathType Leaf) {
    $nodeExecutable = Join-Path $projectRoot 'tools/node24/node.exe'
} else {
    $nodeExecutable = (Get-Command node -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
}
if (!(Test-Path -LiteralPath $nodeExecutable -PathType Leaf)) { throw "Node.js runtime not found: $nodeExecutable" }
$nodeIdentity = & $nodeExecutable -p "process.versions.node + ':' + process.versions.modules"
if ($LASTEXITCODE -ne 0 -or $nodeIdentity -notmatch '^24\.\d+\.\d+:137$') {
    throw "Node.js 24 with ABI 137 is required by the installed SQLite module. Selected: $nodeExecutable ($nodeIdentity)"
}

$tempDirectory = & (Join-Path $PSScriptRoot "set-cn-temp.ps1") -ProjectRoot $projectRoot
$logDirectory = Join-Path $projectRoot ".logs"
$configuredPortText = & $nodeExecutable "--env-file=$envFilePath" -e "process.stdout.write(process.env.CN_LISTEN_PORT || '8001')"
if ($LASTEXITCODE -ne 0 -or $configuredPortText -notmatch '^\d+$') { throw "Cannot read CN_LISTEN_PORT from server configuration." }
$configuredPort = [int]$configuredPortText
if ($configuredPort -lt 1 -or $configuredPort -gt 65535) { throw "CN_LISTEN_PORT is out of range." }
$listener = Get-NetTCPConnection -LocalPort $configuredPort -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($listener) {
    throw "Port $configuredPort is already in use by PID $($listener.OwningProcess)."
}

# A program-file overlay is not a database migration. Refuse a partial deployment.
Push-Location -LiteralPath $projectRoot
try {
    & $nodeExecutable "--env-file=$envFilePath" "scripts/time-content-deployment.cjs" verify --project $projectRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Time/content deployment is incomplete. Follow docs/systems/time-content-deployment.md for the matching release plan. Do not replay the original initialization over an existing server."
    }
} finally { Pop-Location }

if ($Foreground) {
    Write-Host "CN StarPoint foreground console. Node: $nodeExecutable"
    Write-Host "Closing this window stops the server."
    Push-Location -LiteralPath $projectRoot
    try {
        & $nodeExecutable "--env-file=$envFilePath" 'out/cn-server.js'
        $serverExitCode = $LASTEXITCODE
    } finally { Pop-Location }
    exit $serverExitCode
}

$process = Start-Process `
    -FilePath $nodeExecutable `
    -ArgumentList "--env-file=.env", "scripts/run-cn-logged.cjs", "--retention-days", "$RetentionDays" `
    -WorkingDirectory $projectRoot `
    -WindowStyle Hidden `
    -PassThru

# The receipt contains the game PID, not the logger PID, for maintenance tools.
$receiptPath = Join-Path $logDirectory "cn-server-current.json"
$currentLogInfo = $null
$deadline = (Get-Date).AddSeconds(10)
while ((Get-Date) -lt $deadline) {
    if ($process.HasExited) { throw "Log collector exited before server startup. Check .logs." }
    if (Test-Path -LiteralPath $receiptPath) {
        try {
            $candidate = Get-Content -Raw -LiteralPath $receiptPath | ConvertFrom-Json
            if ($candidate.loggerPid -eq $process.Id -and $candidate.pid) {
                $currentLogInfo = $candidate
                break
            }
        } catch {
            # Retry a transient read while the receipt is replaced atomically.
        }
    }
    Start-Sleep -Milliseconds 100
}
if (!$currentLogInfo) { throw "No startup receipt within 10 seconds; inspect logger PID $($process.Id) before retrying." }

Write-Output "CN StarPoint launched. PID=$($currentLogInfo.pid) loggerPID=$($process.Id)"
Write-Output "temp: $tempDirectory"
Write-Output "log: $($currentLogInfo.log)"
Write-Output "Rotation: every 4 hours at 00/04/08/12/16/20 (UTC+08:00)."
