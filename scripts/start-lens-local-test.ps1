$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (Test-Path -LiteralPath (Join-Path $projectRoot '.storage-maintenance\active.lock')) {
    throw 'Storage maintenance is still active.'
}
$nodeExecutable = (Get-Command node -ErrorAction Stop).Source
$envFilePath = Join-Path $projectRoot '.env'
$port = & $nodeExecutable "--env-file=$envFilePath" -e "process.stdout.write(process.env.CN_LISTEN_PORT || '8001')"
if ($LASTEXITCODE -ne 0 -or $port -notmatch '^\d+$') { throw 'Cannot read server port.' }
if (Get-NetTCPConnection -LocalPort ([int]$port) -State Listen -ErrorAction SilentlyContinue) {
    throw "Server port $port is already in use; refusing to launch a second instance."
}
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logDirectory = Join-Path $projectRoot '.logs'
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$stdout = Join-Path $logDirectory "lens-local-$timestamp.stdout.log"
$stderr = Join-Path $logDirectory "lens-local-$timestamp.stderr.log"
$priorPlatform = $env:CN_LOCAL_CLIENT_PLATFORM
try {
    $env:CN_LOCAL_CLIENT_PLATFORM = 'android'
    $process = Start-Process -FilePath $nodeExecutable -ArgumentList '--env-file=.env','out/cn-server.js' -WorkingDirectory $projectRoot -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
} finally {
    $env:CN_LOCAL_CLIENT_PLATFORM = $priorPlatform
}
$info = [ordered]@{pid=$process.Id;startedAt=(Get-Date).ToString('o');stdout=$stdout;stderr=$stderr;platform='android'}
$info | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logDirectory 'cn-server-current.json') -Encoding utf8
$info | ConvertTo-Json
