param(
    [Parameter(Mandatory=$true)][string]$Entry,
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]{0,40}$')][string]$RunName,
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$StageArguments,
    [ValidateRange(32,1536)][int]$MemoryMiB=1536,
    [ValidateRange(1,180)][int]$TimeoutSeconds=180
)
$ErrorActionPreference='Stop'
if (-not $env:SP_CLIENT_INPUTS) { throw 'Set SP_CLIENT_INPUTS to private JSON configuration' }
$settings=Get-Content -LiteralPath $env:SP_CLIENT_INPUTS -Raw|ConvertFrom-Json
function Input-Value([string]$key){$row=$settings.ios.$key;if($row -is [string]){return $row};if($row.path){return $row.path};throw "Private ios.$key.path missing"}
$python=Input-Value 'python'
$root=[IO.Path]::GetFullPath($settings.work_dir)
$work=Join-Path $root 'ios'
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
if($work.StartsWith($repo+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Private work_dir must be outside repository'}
foreach($p in @($root,$work,(Join-Path $work 'jobs'))){if(Test-Path -LiteralPath $p){if((Get-Item -LiteralPath $p).Attributes -band [IO.FileAttributes]::ReparsePoint){throw "Refuse reparse output: $p"}}}
$jobs=Join-Path $work 'jobs';New-Item -ItemType Directory -Path $jobs -Force|Out-Null
$receipt=Join-Path $jobs "$RunName.json";$log=[IO.Path]::ChangeExtension($receipt,'.log')
foreach($p in @($receipt,$log)){if(Test-Path -LiteralPath $p){throw "Fresh receipt required: $p"}}
# No engineering slot is acquired here. The coordinator must authorize it first.
# Inactive desktop wraps all child tools, including historical compc subprocesses.
$inner=[Math]::Min(170,[Math]::Max(1,$TimeoutSeconds-5))
& $python -B (Join-Path $PSScriptRoot 'support/process/run_bounded.py') `
    --limit-mib $MemoryMiB --timeout $TimeoutSeconds --cwd $work --receipt $receipt -- `
    $python -B (Join-Path $PSScriptRoot 'support/process/run_background.py') `
    --timeout $inner --cwd $work -- `
    $python -B (Join-Path $PSScriptRoot 'stage_entry.py') $Entry -- @StageArguments
if($LASTEXITCODE -ne 0){throw "Stage failed; retain receipt without automatic retry/budget increase: $receipt"}
$r=Get-Content -LiteralPath $receipt -Raw|ConvertFrom-Json
if($r.status -ne 'exited' -or $r.exitCode -ne 0 -or -not $r.cleanupConfirmed -or $r.activeProcessesAfterCleanup -ne 0){throw 'Job cleanup not confirmed'}
Write-Output "Completed $Entry with cleanup confirmed: $receipt"
