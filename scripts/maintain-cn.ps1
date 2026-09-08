param(
    [ValidateSet("Preview", "Apply", "Recover")][string]$Mode = "Preview",
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$UpdateArchive
)
$ErrorActionPreference = "Stop"
$projectDirectory = (Resolve-Path -LiteralPath $ProjectRoot).ProviderPath.TrimEnd('\')
$maintenanceDirectory = Join-Path $projectDirectory ".storage-maintenance"
$controllerPath = Join-Path $maintenanceDirectory "controller.json"
$activePath = Join-Path $maintenanceDirectory "active.lock"
$nodeExecutable = (Get-Command node -ErrorAction Stop).Source
$null = & (Join-Path $projectDirectory "scripts\set-cn-temp.ps1") -ProjectRoot $projectDirectory
$cliPath = Join-Path $projectDirectory "out\storage-maintenance.js"
$script:controller = $null
$script:mutexAcquired = $false
$mutexHash = [Security.Cryptography.SHA256]::Create()
try { $mutexId = [BitConverter]::ToString($mutexHash.ComputeHash([Text.Encoding]::UTF8.GetBytes($projectDirectory.ToLowerInvariant()))).Replace('-', '') }
finally { $mutexHash.Dispose() }
$controllerMutex = New-Object Threading.Mutex($false, ("Local\StarPointStorage-" + $mutexId))

function Resolve-ReleasePath([string]$Root, [string]$Relative) {
    if ($Relative -notmatch '^[A-Za-z0-9_./-]+$' -or $Relative.StartsWith('/') -or $Relative.Contains('\')) { throw "Invalid release member: $Relative" }
    $parts = $Relative.Split('/')
    if ($parts -contains '..' -or $parts -contains '.' -or $parts -contains '') { throw "Invalid release path: $Relative" }
    if ($parts[0] -match '^(\.cdn|\.database|\.env.*|\.git.*|\.codex.*|\.storage-maintenance|node_modules|logs|\.logs|tmp|work)$') { throw "Protected release path: $Relative" }
    $rootPath = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $targetPath = [IO.Path]::GetFullPath((Join-Path $rootPath ($Relative.Replace('/', '\'))))
    if (!$targetPath.StartsWith($rootPath + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Release path escaped project" }
    $parentPath = $targetPath
    while ($parentPath.Length -gt $rootPath.Length) {
        if (Test-Path -LiteralPath $parentPath) {
            if (((Get-Item -LiteralPath $parentPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Release path crosses a junction: $Relative" }
        }
        $parentPath = Split-Path -Parent $parentPath
    }
    return $targetPath
}

function Write-Controller {
    $temporaryPath = $controllerPath + ".tmp"
    $bytes = [Text.Encoding]::UTF8.GetBytes(($script:controller | ConvertTo-Json -Depth 12))
    $stream = [IO.File]::Open($temporaryPath, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
    if (Test-Path -LiteralPath $controllerPath) { [IO.File]::Replace($temporaryPath, $controllerPath, $controllerPath + ".bak") }
    else { [IO.File]::Move($temporaryPath, $controllerPath) }
}

function Get-ReleaseHash([string]$LiteralPath) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($LiteralPath)
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '') }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}

function Copy-ReleaseFile([string]$Source, [string]$Destination) {
    $temporaryPath = $Destination + '.storage-new-' + [Guid]::NewGuid().ToString()
    try {
        [IO.File]::Copy($Source, $temporaryPath, $false)
        $stream = [IO.File]::Open($temporaryPath, [IO.FileMode]::Open, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $stream.Flush($true) } finally { $stream.Dispose() }
        if (Test-Path -LiteralPath $Destination) { [IO.File]::Replace($temporaryPath, $Destination, [NullString]::Value) }
        else { [IO.File]::Move($temporaryPath, $Destination) }
    } finally {
        if (Test-Path -LiteralPath $temporaryPath) { Remove-Item -LiteralPath $temporaryPath -Force }
    }
}

function Invoke-MaintenanceCli([string]$Command, [switch]$Json) {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        if ($Json) { $output = & $nodeExecutable --env-file=.env $script:cliPath $Command --project $projectDirectory }
        else { & $nodeExecutable --env-file=.env $script:cliPath $Command --project $projectDirectory | Out-Host }
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreference }
    if ($code -ne 0) { throw "Maintenance command '$Command' failed (exit $code)." }
    if ($Json) { return ($output -join "`n" | ConvertFrom-Json) }
}

function Stage-UpdateArchive([string]$ArchivePath) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $ArchivePath).ProviderPath)
    try {
        $manifestEntry = $archive.GetEntry("_maintenance/manifest.json")
        if (!$manifestEntry -or $manifestEntry.Length -gt 4MB) { throw "Update archive requires _maintenance/manifest.json" }
        $reader = New-Object IO.StreamReader($manifestEntry.Open())
        try { $manifest = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
        if ($manifest.format -ne 1 -or @($manifest.files).Count -lt 1) { throw "Unsupported update manifest" }
        $members = @{}
        foreach ($file in $manifest.files) {
            $null = Resolve-ReleasePath $projectDirectory $file.path
            if ($members.ContainsKey($file.path) -or $file.sha256 -notmatch '^[a-fA-F0-9]{64}$') { throw "Duplicate member or invalid SHA-256" }
            $members[$file.path] = $file
        }
        $seen = @{}
        foreach ($entry in $archive.Entries) {
            if ($entry.FullName.EndsWith('/')) { continue }
            if ($seen.ContainsKey($entry.FullName)) { throw "Duplicate ZIP member" }
            $seen[$entry.FullName] = $true
            if ($entry.FullName -ne "_maintenance/manifest.json" -and !$members.ContainsKey($entry.FullName)) { throw "Unlisted ZIP member: $($entry.FullName)" }
        }
        $archiveHash = (Get-ReleaseHash $ArchivePath).ToLowerInvariant()
        $stageDirectory = Join-Path $maintenanceDirectory ("staged\" + $archiveHash)
        foreach ($file in $manifest.files) {
            $entry = $archive.GetEntry($file.path)
            if (!$entry) { throw "Missing ZIP member: $($file.path)" }
            $target = Resolve-ReleasePath $stageDirectory $file.path
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
            if ((Test-Path -LiteralPath $target) -and (Get-ReleaseHash $target) -ne $file.sha256) {
                Remove-Item -LiteralPath $target -Force
            }
            if (!(Test-Path -LiteralPath $target)) { [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $false) }
            if ((Get-ReleaseHash $target) -ne $file.sha256) { throw "SHA-256 mismatch: $($file.path)" }
        }
        foreach ($required in @(
            "out/storage-maintenance.js", "out/lib/storage-layout.js", "out/lib/maintenance-state.js", "out/lib/receive-history-retention.js", "out/lib/atomic-json-file.js",
            "out/cn-server.js", "out/data/index.js", "out/data/initializers/wdfpData.js", "out/data/snapshots/player-snapshot.js", "out/lib/mission/counters.js",
            "out/lib/quest/recommended-party-history.js", "out/routes/api/quest.js", "out/lib/mode15.js", "out/lib/mode15-optional.js", "scripts/start-cn-logged.ps1"
        )) {
            if (!$members.ContainsKey($required)) { throw "Maintenance runtime missing from update: $required" }
        }
        return [pscustomobject]@{ directory = $stageDirectory; files = @($manifest.files) }
    } finally { $archive.Dispose() }
}

function Get-OwnedServerProcess {
    $logInfoPath = Join-Path $projectDirectory ".logs\cn-server-current.json"
    if (!(Test-Path -LiteralPath $logInfoPath)) { return $null }
    $logInfo = Get-Content -Raw -LiteralPath $logInfoPath | ConvertFrom-Json
    $serverProcess = Get-Process -Id ([int]$logInfo.pid) -ErrorAction SilentlyContinue
    if (!$serverProcess) { return $null }
    $logRoot = [IO.Path]::GetFullPath((Join-Path $projectDirectory ".logs")).TrimEnd('\') + '\'
    if (!([IO.Path]::GetFullPath([string]$logInfo.stdout)).StartsWith($logRoot, [StringComparison]::OrdinalIgnoreCase)) { throw "Server PID receipt belongs to another project" }
    $command = Get-CimInstance Win32_Process -Filter ("ProcessId = " + [int]$logInfo.pid)
    $recordedStart = [DateTimeOffset]::Parse([string]$logInfo.startedAt)
    if ($serverProcess.ProcessName -ne 'node' -or $command.CommandLine -notmatch 'cn-server\.js' -or
        [Math]::Abs(($serverProcess.StartTime.ToUniversalTime() - $recordedStart.UtcDateTime).TotalSeconds) -gt 15) {
        throw "Server PID receipt is stale or ambiguous; no process was stopped."
    }
    return $serverProcess
}

function Stop-OwnedServer([int]$Port) {
    $serverProcess = Get-OwnedServerProcess
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        if (!$serverProcess -or $listener.OwningProcess -ne $serverProcess.Id) { throw "Port $Port belongs to a different process; refusing to stop it." }
    }
    if ($serverProcess) {
        Write-Host "Stopping CN server PID $($serverProcess.Id)..."
        Stop-Process -Id $serverProcess.Id -ErrorAction Stop
        if (!$serverProcess.WaitForExit(15000)) { throw "Server did not stop in time" }
    }
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw "Server port remains occupied" }
}

function Apply-ProgramFiles {
    if (!$script:controller.stageDirectory) { return }
    $script:controller.phase = "backing-up-program"
    Write-Controller
    foreach ($file in $script:controller.files) {
        $target = Resolve-ReleasePath $projectDirectory $file.path
        $backup = Resolve-ReleasePath $script:controller.programBackup $file.path
        $file.existed = Test-Path -LiteralPath $target
        if ($file.existed) {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $backup) | Out-Null
            Copy-Item -LiteralPath $target -Destination $backup
            $file.beforeSha256 = Get-ReleaseHash $backup
        }
    }
    $script:controller.phase = "applying-program"
    Write-Controller
    foreach ($file in $script:controller.files) {
        $source = Resolve-ReleasePath $script:controller.stageDirectory $file.path
        $target = Resolve-ReleasePath $projectDirectory $file.path
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Copy-ReleaseFile $source $target
        if ((Get-ReleaseHash $target) -ne $file.sha256) { throw "Installed file verification failed" }
    }
    $script:controller.phase = "program-applied"
    Write-Controller
}

function Restore-ProgramFiles {
    if (!$script:controller.stageDirectory -or $script:controller.phase -in @('preparing','backing-up-program')) { return }
    foreach ($file in $script:controller.files) {
        $target = Resolve-ReleasePath $projectDirectory $file.path
        if ($file.existed) {
            $backup = Resolve-ReleasePath $script:controller.programBackup $file.path
            if ((Get-ReleaseHash $backup) -ne $file.beforeSha256) { throw "Program backup verification failed" }
            Copy-ReleaseFile $backup $target
        } elseif (Test-Path -LiteralPath $target) {
            # Only the explicitly recorded new release file can be removed.
            Remove-Item -LiteralPath $target -Force
        }
    }
}

function Start-ProductionAndVerify([string]$DatabasePath, [int]$LayoutVersion, [bool]$RequireReceipt) {
    $env:LOG_LEVEL = "warn"
    $env:GACHA_VERBOSE_LOGS = "false"
    $env:GAME_VERBOSE_LOGS = "false"
    $serverProcess = Get-OwnedServerProcess
    if (!$serverProcess) { & (Join-Path $projectDirectory "scripts\start-cn-logged.ps1") -RetentionDays 7 }
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        $serverProcess = Get-OwnedServerProcess
        if (!$serverProcess) { throw "CN server exited during startup; inspect .logs" }
        $receiptPath = Join-Path $projectDirectory ".logs\cn-server-ready.json"
        if ($RequireReceipt -and (Test-Path -LiteralPath $receiptPath)) {
            try { $receipt = Get-Content -Raw -LiteralPath $receiptPath | ConvertFrom-Json } catch { $receipt = $null }
            if ($receipt -and $receipt.pid -eq $serverProcess.Id -and $receipt.database -eq $DatabasePath -and $receipt.storageLayoutVersion -eq $LayoutVersion -and
                [DateTimeOffset]::Parse([string]$receipt.readyAt).UtcDateTime -ge $serverProcess.StartTime.ToUniversalTime()) { return }
        } elseif (!$RequireReceipt) {
            $listeners = @(Get-NetTCPConnection -OwningProcess $serverProcess.Id -State Listen -ErrorAction SilentlyContinue)
            if ($listeners.Count -gt 0) { return }
        }
        Start-Sleep -Milliseconds 500
    }
    throw "CN server readiness verification timed out"
}

Push-Location $projectDirectory
try {
    try { $script:mutexAcquired = $controllerMutex.WaitOne(0) }
    catch [Threading.AbandonedMutexException] { $script:mutexAcquired = $true }
    if (!$script:mutexAcquired) { throw "Another maintenance controller is running for this project" }
    if ($Mode -eq "Recover") {
        if (!(Test-Path -LiteralPath $controllerPath)) { throw "No maintenance controller state found" }
        $script:controller = Get-Content -Raw -LiteralPath $controllerPath | ConvertFrom-Json
        if ($script:controller.project -ne $projectDirectory) { throw "Controller belongs to a different project" }
        $owner = Get-Process -Id ([int]$script:controller.pid) -ErrorAction SilentlyContinue
        if ($owner -and [Math]::Abs(($owner.StartTime.ToUniversalTime() - [DateTimeOffset]::Parse($script:controller.processStartedAt).UtcDateTime).TotalSeconds) -lt 2) { throw "Maintenance controller is still running" }
        if ($script:controller.stageDirectory) { $script:cliPath = Join-Path $script:controller.stageDirectory "out\storage-maintenance.js" }
        $state = Invoke-MaintenanceCli "status" -Json
        if ($state.id -and $state.id -eq $script:controller.previousDatabaseRunId) {
            $state = [pscustomobject]@{phase='not-started'; layoutBefore=$script:controller.layoutBefore}
        }
        if ($state.phase -in @('service-starting','rollback-starting','completed','rolled-back')) {
            if (Test-Path -LiteralPath $activePath) { Remove-Item -LiteralPath $activePath -Force }
            $expectedVersion = if ($state.phase -in @('rollback-starting','rolled-back')) { [int]$state.layoutBefore } else { 1 }
            Start-ProductionAndVerify $state.database $expectedVersion ($expectedVersion -eq 1)
            if ($state.phase -in @('service-starting','rollback-starting')) { Invoke-MaintenanceCli "complete" }
        } else {
            Stop-OwnedServer ([int]$script:controller.port)
            if ($state.phase -eq 'not-started') { Invoke-MaintenanceCli "unlock-unstarted" }
            else { Invoke-MaintenanceCli "rollback"; Invoke-MaintenanceCli "release" }
            Restore-ProgramFiles
            if (Test-Path -LiteralPath $activePath) { Remove-Item -LiteralPath $activePath -Force }
            Start-ProductionAndVerify $script:controller.database ([int]$state.layoutBefore) $false
            if ($state.phase -ne 'not-started') { Invoke-MaintenanceCli "complete" }
        }
        $script:controller.phase = "recovered"
        Write-Controller
        Write-Host "Recovery completed. Current cloud data remains in its configured directory."
        exit 0
    }

    $staged = $null
    if ($Mode -in @('Preview','Apply') -and !$UpdateArchive -and (Test-Path -LiteralPath (Join-Path $projectDirectory 'storage-update.zip'))) { $UpdateArchive = Join-Path $projectDirectory 'storage-update.zip' }
    if ($UpdateArchive) {
        $staged = Stage-UpdateArchive $UpdateArchive
        $script:cliPath = Join-Path $staged.directory 'out\storage-maintenance.js'
        $needsProgramUpdate = $false
        foreach ($file in $staged.files) {
            $target = Resolve-ReleasePath $projectDirectory $file.path
            if (!(Test-Path -LiteralPath $target) -or (Get-ReleaseHash $target) -ne $file.sha256) { $needsProgramUpdate = $true; break }
        }
        if (!$needsProgramUpdate) { $staged = $null; $script:cliPath = Join-Path $projectDirectory 'out\storage-maintenance.js' }
    }
    $preview = Invoke-MaintenanceCli "preview" -Json
    Write-Host "Database: $($preview.database)"
    Write-Host ("Database size: {0:N1} MiB; free disk: {1:N1} GiB; required additional space: {2:N1} GiB" -f ($preview.bytes/1MB),($preview.availableBytes/1GB),($preview.requiredAdditionalBytes/1GB))
    Write-Host "Storage layout: $($preview.stats.layoutVersion); history deletion candidates: $($preview.historyDeletionCandidates)"
    Write-Host "Persistent retention: $($preview.policy.maxDays) days, $($preview.policy.maxRows) rows per player."
    if ($Mode -eq 'Preview') { exit 0 }
    if ($preview.automaticRetentionEnabled -eq $false) { throw "RECEIVE_HISTORY_RETENTION_ENABLED disables scheduled maintenance. Review that setting before applying this upgrade." }
    if ([double]$preview.availableBytes -lt [double]$preview.requiredAdditionalBytes) { throw "Insufficient free space for backup and migration" }
    New-Item -ItemType Directory -Force -Path $maintenanceDirectory | Out-Null
    if (Test-Path -LiteralPath $activePath) { throw "Previous maintenance has not finished; run maintain-cn-recover.bat" }
    $previousDatabaseState = Invoke-MaintenanceCli "status" -Json
    $runId = [Guid]::NewGuid().ToString()
    $fileRecords = @()
    if ($staged) { $fileRecords = @($staged.files | ForEach-Object { [pscustomobject]@{ path=$_.path; sha256=$_.sha256; existed=$false; beforeSha256=$null } }) }
    $script:controller = [pscustomobject]@{
        project=$projectDirectory; pid=$PID; processStartedAt=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString('o');
        phase='preparing'; database=$preview.database; port=$preview.port;
        previousDatabaseRunId=$previousDatabaseState.id; layoutBefore=$preview.stats.layoutVersion;
        stageDirectory=$(if($staged){$staged.directory}else{$null}); programBackup=(Join-Path $maintenanceDirectory ('program-backups\'+$runId)); files=$fileRecords
    }
    Write-Controller
    $activeStream = [IO.File]::Open($activePath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    $activeStream.Dispose()
    Stop-OwnedServer ([int]$preview.port)
    Apply-ProgramFiles
    Invoke-MaintenanceCli "apply"
    Invoke-MaintenanceCli "release"
    $script:controller.phase = 'service-starting'
    Write-Controller
    Remove-Item -LiteralPath $activePath -Force
    Start-ProductionAndVerify $preview.database 1 $true
    Invoke-MaintenanceCli "complete"
    $script:controller.phase = 'completed'
    Write-Controller
    Write-Host "Completed: upgrade, persistent retention, database compaction, and server restart."
    Write-Host "Report: $($preview.state)"
} catch {
    Write-Host ("Maintenance stopped: " + $_.Exception.Message) -ForegroundColor Red
    if ($script:controller -or (Test-Path -LiteralPath $activePath)) {
        Write-Host "Do not overwrite the database or remove lock files. Run maintain-cn-recover.bat."
    } else {
        Write-Host "Preflight failed before stopping the server or changing the database. Correct the reported issue and retry."
    }
    exit 1
} finally {
    if ($script:mutexAcquired) { $controllerMutex.ReleaseMutex() }
    $controllerMutex.Dispose()
    Pop-Location
}
