param([string]$LanHost, [string]$ConfigPath, [string]$KeysPath)
$ErrorActionPreference='Stop'
$admissionRepo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
if (-not $LanHost) { $LanHost=(Get-Content -LiteralPath (Join-Path $admissionRepo 'outputs/android-build-local.json') -Raw | ConvertFrom-Json).lan_host -replace ':\d+$','' }
if (-not $ConfigPath) { $ConfigPath=Join-Path $admissionRepo 'outputs/client-admission-private/client-admission.json' }
if (-not $KeysPath) { $KeysPath=Join-Path $admissionRepo 'outputs/client-admission-private/client-admission.keys.json' }
if (Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in 8002,8013 }) { throw 'Isolated test ports are already occupied.' }
$admissionEnv=@{ DATA_DIR=(Join-Path $admissionRepo 'outputs/client-admission-work/server-data'); CN_LISTEN_HOST='0.0.0.0'; CN_LISTEN_PORT='8002'; SESSION_HOST='0.0.0.0'; SESSION_PORT='8013'; SESSION_PUBLIC_HOST=$LanHost; CN_PUBLIC_HOST=$LanHost; CN_LOCAL_CLIENT_PLATFORM='android'; LOG_LEVEL='warn'; CLIENT_ADMISSION_CONFIG=$ConfigPath; CLIENT_ADMISSION_KEYS=$KeysPath }
$admissionPrior=@{}
foreach($admissionName in $admissionEnv.Keys){$admissionPrior[$admissionName]=[Environment]::GetEnvironmentVariable($admissionName,'Process');[Environment]::SetEnvironmentVariable($admissionName,$admissionEnv[$admissionName],'Process')}
Push-Location $admissionRepo
try { & node -r ts-node/register/transpile-only src/cn-server.ts }
finally {Pop-Location;foreach($admissionName in $admissionEnv.Keys){[Environment]::SetEnvironmentVariable($admissionName,$admissionPrior[$admissionName],'Process')}}
