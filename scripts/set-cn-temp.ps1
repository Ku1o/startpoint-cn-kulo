param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$ProjectRoot
)

$ErrorActionPreference = "Stop"

$resolvedProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
$tempDirectory = Join-Path $resolvedProjectRoot "tmp\cn-server"
New-Item -ItemType Directory -Force -Path $tempDirectory | Out-Null

# Fail before starting Node if the stable temp directory is not writable.
$probePath = Join-Path $tempDirectory ".write-test-$PID-$([Guid]::NewGuid().ToString('N')).tmp"
try {
    [IO.File]::WriteAllText($probePath, "ok")
}
finally {
    if (Test-Path -LiteralPath $probePath) {
        Remove-Item -LiteralPath $probePath -Force
    }
}

$env:TEMP = $tempDirectory
$env:TMP = $tempDirectory

Write-Output $tempDirectory
