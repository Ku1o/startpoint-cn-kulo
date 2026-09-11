$ErrorActionPreference = 'Stop'
$taskDir = if ($env:STARPOINT_IOS_PROFILE_WORK) { $env:STARPOINT_IOS_PROFILE_WORK } else { 'F:\codex\ios-profile-follow-port-20260908' }
$sdkRoot = 'F:\codex\ios-rush-leaderboard-port-20260830\AIRSDK_51.2.1.5'
$compiler = Join-Path $sdkRoot 'lib\aot\bin\compile-abc\compile-abc-64.exe'
$fields = Join-Path $sdkRoot 'lib\aot\lib\air-fields.arm64-air.txt'
$avmglue = Join-Path $sdkRoot 'lib\aot\lib\avmglue.abc'
$deps = @(Get-ChildItem -LiteralPath 'F:\codex\ios-rush-leaderboard-port-20260830\android-baseline\abc' -File |
    Where-Object Name -NotLike '284-*' | Sort-Object Name | ForEach-Object FullName)
if ($deps.Count -ne 284) { throw 'Expected exactly 284 dependency ABC files' }
Push-Location -LiteralPath (Join-Path $taskDir 'compile')
try {
    & $compiler '-mtriple=arm64-apple-ios' "-fields=$fields" "-sdk=$avmglue" '-O=1' @deps `
        (Join-Path $taskDir 'compile\profile-follow.abc') *> (Join-Path $taskDir 'compile.log')
    if ($LASTEXITCODE -ne 0) { throw "AOT compiler failed; see $taskDir\compile.log" }
} finally {
    Pop-Location
}
