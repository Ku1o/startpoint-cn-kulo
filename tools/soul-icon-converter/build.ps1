$ErrorActionPreference = 'Stop'

$projectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$releaseDirectory = Join-Path $projectDirectory 'dist'
$compilerPath = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'

if (-not (Test-Path -LiteralPath $compilerPath)) {
    $compilerPath = 'C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe'
}

if (-not (Test-Path -LiteralPath $compilerPath)) {
    throw '找不到 Windows 自带的 C# 编译器。'
}

$generatedModel = Join-Path $projectDirectory 'SoulColorModel.g.cs'
if (-not (Test-Path -LiteralPath $generatedModel)) {
    throw '缺少内置颜色模型 SoulColorModel.g.cs；请重新获取完整工具目录。'
}

$generatedPreviewAssets = Join-Path $projectDirectory 'GamePreviewAssets.g.cs'
if (-not (Test-Path -LiteralPath $generatedPreviewAssets)) {
    throw '缺少内置游戏预览素材 GamePreviewAssets.g.cs；请重新获取完整工具目录。'
}

New-Item -ItemType Directory -Force -Path $releaseDirectory | Out-Null
$executablePath = Join-Path $releaseDirectory '魂珠图标一键转换工具.exe'

$compilerArguments = @(
    '/nologo'
    '/target:winexe'
    '/platform:anycpu'
    '/optimize+'
    '/debug-'
    '/codepage:65001'
    ('/out:' + $executablePath)
    ('/win32manifest:' + (Join-Path $projectDirectory 'app.manifest'))
    '/reference:System.dll'
    '/reference:System.Core.dll'
    '/reference:System.Drawing.dll'
    '/reference:System.Windows.Forms.dll'
    (Join-Path $projectDirectory 'AssemblyInfo.cs')
    (Join-Path $projectDirectory 'Program.cs')
    (Join-Path $projectDirectory 'SoulTransformer.cs')
    (Join-Path $projectDirectory 'PixelPreviewBox.cs')
    (Join-Path $projectDirectory 'GamePreviewBox.cs')
    (Join-Path $projectDirectory 'MainForm.cs')
    $generatedModel
    $generatedPreviewAssets
)

& $compilerPath $compilerArguments
if ($LASTEXITCODE -ne 0) {
    throw "编译失败，退出码：$LASTEXITCODE"
}

Copy-Item -LiteralPath (Join-Path $projectDirectory '使用说明.txt') -Destination $releaseDirectory -Force
Get-FileHash -Algorithm SHA256 -LiteralPath $executablePath |
    Select-Object Path, Hash
