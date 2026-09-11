param(
    [Parameter(Mandatory=$true)][string]$Java,
    [Parameter(Mandatory=$true)][string]$ApkSigner,
    [Parameter(Mandatory=$true)][string]$Keystore,
    [Parameter(Mandatory=$true)][string]$CredentialPath,
    [Parameter(Mandatory=$true)][string]$InputApk,
    [Parameter(Mandatory=$true)][string]$OutputApk
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputApk) { throw 'Refusing to overwrite an APK' }
$abyssSigningCredential = $null
try {
    $abyssSigningCredential = Import-Clixml -LiteralPath $CredentialPath
    $env:STARPOINT_ABYSS_APK_SIGNING_PASSWORD = $abyssSigningCredential.GetNetworkCredential().Password
    & $Java -jar $ApkSigner sign --ks $Keystore --ks-key-alias wf --ks-pass env:STARPOINT_ABYSS_APK_SIGNING_PASSWORD --key-pass env:STARPOINT_ABYSS_APK_SIGNING_PASSWORD --out $OutputApk $InputApk
    if ($LASTEXITCODE -ne 0) { throw "APK signing failed with exit code $LASTEXITCODE" }
}
finally {
    [Environment]::SetEnvironmentVariable('STARPOINT_ABYSS_APK_SIGNING_PASSWORD', $null, 'Process')
    $abyssSigningCredential = $null
}
