param(
    [Parameter(Mandatory=$true)][string]$InputApk,
    [Parameter(Mandatory=$true)][string]$OutputApk,
    [Parameter(Mandatory=$true)][string]$ApkSigner,
    [string]$Java = 'java'
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputApk) { throw 'Signing output must be new.' }
$keyStore = 'F:\StartPointCN\wf_full_patch\launcher.jks'
$credentialFile = 'F:\codex\.codex\secrets\startpoint-apk-signing.credential.xml'
try {
    # DPAPI decryption is confined to this signing process. No password is
    # written to disk, printed, or passed as a command-line argument.
    $signingCredential = Import-Clixml -LiteralPath $credentialFile
    [Environment]::SetEnvironmentVariable('LENS_APK_SIGNING_SECRET', $signingCredential.GetNetworkCredential().Password, 'Process')
    & $Java -jar $ApkSigner sign --ks $keyStore --ks-key-alias wf --ks-pass env:LENS_APK_SIGNING_SECRET --key-pass env:LENS_APK_SIGNING_SECRET --v1-signing-enabled true --v2-signing-enabled true --out $OutputApk $InputApk
    if ($LASTEXITCODE -ne 0) { throw "APK signing failed with exit code $LASTEXITCODE" }
} finally {
    [Environment]::SetEnvironmentVariable('LENS_APK_SIGNING_SECRET', $null, 'Process')
    Remove-Variable signingCredential -ErrorAction SilentlyContinue
}
