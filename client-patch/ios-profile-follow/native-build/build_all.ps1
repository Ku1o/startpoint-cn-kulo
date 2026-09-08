$ErrorActionPreference = 'Stop'
# Set STARPOINT_IOS_PROFILE_WORK to a new task directory before rebuilding.
foreach ($step in @('prepare.py', 'import_methods.py')) {
    & python (Join-Path $PSScriptRoot $step)
    if ($LASTEXITCODE -ne 0) { throw "$step failed" }
}
& (Join-Path $PSScriptRoot 'compile.ps1')
foreach ($step in @('inspect_compile.py', 'build_native.py', 'verify_native.py', 'check_profile_branches.py')) {
    & python (Join-Path $PSScriptRoot $step)
    if ($LASTEXITCODE -ne 0) { throw "$step failed" }
}
