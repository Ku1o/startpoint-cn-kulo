$toolDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $toolDir

if (-not $env:WF_APK) {
    $defaultApk = 'F:\startpoint-cn-main\弹国服\client-1.8.1-current.apk'
    if (Test-Path -LiteralPath $defaultApk) {
        $env:WF_APK = $defaultApk
    }
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 wf_gui.py
} else {
    & python wf_gui.py
}
