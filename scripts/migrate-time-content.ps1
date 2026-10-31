param(
    [ValidateSet("Preview", "Apply", "Verify", "Rollback", "Release", "Recover")][string]$Mode = "Preview",
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$SupplementPlan,
    [string]$PlanDigest
)
$ErrorActionPreference = "Stop"
$deploymentRoot = (Resolve-Path -LiteralPath $ProjectRoot).ProviderPath
$nodeExecutable = (Get-Command node -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
if ([bool]$SupplementPlan -ne [bool]$PlanDigest) { throw 'SupplementPlan and PlanDigest must be provided together.' }
if ($SupplementPlan -and $Mode -notin @('Preview', 'Apply', 'Verify')) { throw 'Supplement arguments are only valid for Preview, Apply or Verify.' }
if ($SupplementPlan) {
    $SupplementPlan = (Resolve-Path -LiteralPath $SupplementPlan).ProviderPath
    if ($PlanDigest -notmatch '^[a-f0-9]{64}$') { throw 'PlanDigest must be the reviewed lowercase SHA256.' }
}
function Invoke-Deployment([string]$Command) {
    $deploymentArgs = @('--env-file=.env', 'scripts/time-content-deployment.cjs', $Command, '--project', $deploymentRoot)
    if ($SupplementPlan -and $Command -in @('preview', 'apply', 'verify')) {
        $deploymentArgs += @('--supplement', $SupplementPlan, '--plan-digest', $PlanDigest)
    }
    & $nodeExecutable @deploymentArgs
    if ($LASTEXITCODE -ne 0) { throw "Time/content command '$Command' failed. Service remains stopped; keep the backup and receipt." }
}
function Test-DeploymentAlreadyStopped {
    # Reuse the CLI's strict receipt/PID and both-port checks. A missing or old
    # logger capability alone is never evidence that the service has stopped.
    $proof = & $nodeExecutable --env-file=.env -e @'
Promise.resolve().then(() => {
    const deployment = require('./scripts/time-content-deployment.cjs');
    return deployment.assertStopped(deployment.paths(process.cwd()));
}).then(() => {
    process.stdout.write('TIME_CONTENT_STOPPED');
}, error => {
    process.stdout.write('STOP_PROOF_FAILED: ' + error.message);
    process.exitCode = 1;
});
'@
    return $LASTEXITCODE -eq 0 -and ($proof -join "`n") -ceq 'TIME_CONTENT_STOPPED'
}
Push-Location -LiteralPath $deploymentRoot
try {
    switch ($Mode) {
        "Preview" { Invoke-Deployment "preview" }
        "Verify" { Invoke-Deployment "verify" }
        "Apply" {
            if (Test-DeploymentAlreadyStopped) {
                Write-Host "CN is already stopped; strict deployment PID/port checks passed."
            } else {
                & (Join-Path $deploymentRoot 'scripts/stop-cn-logged.ps1') -ProjectRoot $deploymentRoot
            }
            Invoke-Deployment "apply"
            Invoke-Deployment "verify"
            Invoke-Deployment "release"
            & (Join-Path $deploymentRoot 'scripts/start-cn-logged.ps1')
            Write-Host "Migration verified. CN startup requested; check the startup ready receipt."
        }
        "Rollback" {
            Invoke-Deployment "rollback"
            Write-Host "Data restored while the maintenance lock remains. Restore matching program files before Release."
        }
        "Release" { Invoke-Deployment "release" }
        "Recover" { Invoke-Deployment "recover" }
    }
} finally { Pop-Location }
