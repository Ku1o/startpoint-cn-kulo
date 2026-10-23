param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$DebugLog,
    [ValidateRange(1, 600)]
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).ProviderPath.TrimEnd('\', '/')
$logDirectory = Join-Path $ProjectRoot '.logs'
$receiptPath = Join-Path $logDirectory $(if ($DebugLog) { 'cn-server-debug-current.json' } else { 'cn-server-current.json' })
function Read-StartupReceipt {
    $value = Get-Content -Raw -LiteralPath $receiptPath | ConvertFrom-Json
    # PowerShell versions differ: some automatically parse ISO JSON strings.
    # Preserve the logger's exact millisecond UTC spelling for IPC identity.
    foreach ($name in @('startedAt', 'loggerStartedAt')) {
        if ($value.$name -is [datetime]) {
            $value.$name = $value.$name.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", [Globalization.CultureInfo]::InvariantCulture)
        }
    }
    return $value
}
$receipt = Read-StartupReceipt
if (!$receipt.stopPipe -or !$receipt.stopToken -or !$receipt.loggerStartedAt -or !$receipt.serverEntry) {
    throw 'This startup receipt has no verified graceful-stop IPC support. Do not treat a hard stop as graceful.'
}
if ($receipt.exitedAt) { throw 'The recorded server has already exited; no stop request was sent.' }
if ([IO.Path]::GetFullPath($receipt.projectRoot).TrimEnd('\', '/') -ine $ProjectRoot) { throw 'Receipt belongs to another project.' }
$serverEntry = Join-Path $ProjectRoot 'out/cn-server.js'
if ([IO.Path]::GetFullPath($receipt.serverEntry) -ine [IO.Path]::GetFullPath($serverEntry)) { throw 'Receipt is not for this project CN server entry.' }
$pipePrefix = '\\.\pipe\'
if (!$receipt.stopPipe.StartsWith($pipePrefix, [StringComparison]::Ordinal)) { throw 'Stop endpoint is not a local named pipe.' }
$pipeName = $receipt.stopPipe.Substring($pipePrefix.Length)
if ($pipeName -cnotmatch ('^starpoint-cn-stop-' + [regex]::Escape([string]$receipt.loggerPid) + '-[a-f0-9-]{36}$')) { throw 'Stop pipe does not match the recorded logger.' }

function Assert-ProcessIdentity($ProcessId, $ExpectedEntry, $ExpectedStart) {
    if (!$ProcessId -or [long]$ProcessId -lt 1) { throw 'Invalid recorded PID.' }
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $([long]$ProcessId)"
    if (!$processInfo -or !$processInfo.CommandLine -or !$processInfo.ExecutablePath -or !$processInfo.CreationDate) { throw "Cannot verify process $ProcessId." }
    if ([IO.Path]::GetFullPath($processInfo.ExecutablePath) -ine [IO.Path]::GetFullPath($receipt.executable)) { throw "PID $ProcessId executable mismatch." }
    $command = $processInfo.CommandLine.Replace('/', '\')
    $entry = ([IO.Path]::GetFullPath($ExpectedEntry)).Replace('/', '\')
    $entryMatches = $command -imatch ('(?:^|[\s"])' + [regex]::Escape($entry) + '(?=[\s"]|$)')
    # The ordinary launcher invokes the logger by its project-relative name.
    # The separately checked absolute child entry and parent PID bind it to this instance.
    if (!$entryMatches -and $ProcessId -eq $receipt.loggerPid) {
        $entryMatches = $command -imatch '(?:^|[\s"])scripts\\run-cn-logged\.cjs(?=[\s"]|$)'
    }
    if (!$entryMatches) { throw "PID $ProcessId command does not match the recorded entry." }
    $created = ([datetime]$processInfo.CreationDate).ToUniversalTime()
    $expected = ([datetimeoffset]::Parse($ExpectedStart)).UtcDateTime
    if ([Math]::Abs(($created - $expected).TotalSeconds) -gt 2) { throw "PID $ProcessId start time mismatch; OS=$($created.ToString('o')) receipt=$($expected.ToString('o')); it may have been reused." }
    return $processInfo
}

$serverProcess = Assert-ProcessIdentity $receipt.pid $serverEntry $receipt.startedAt
$null = Assert-ProcessIdentity $receipt.loggerPid $receipt.loggerEntry $receipt.loggerStartedAt
if ($serverProcess.ParentProcessId -ne $receipt.loggerPid) { throw 'Server parent PID does not match its logger.' }
if ([int]$receipt.httpPort -lt 1 -or [int]$receipt.httpPort -gt 65535) { throw 'No verifiable HTTP port in startup receipt.' }
$listeners = @(Get-NetTCPConnection -LocalPort ([int]$receipt.httpPort) -State Listen -ErrorAction SilentlyContinue)
if (!$listeners.Count -or @($listeners | Where-Object { $_.OwningProcess -ne $receipt.pid }).Count) { throw 'HTTP listener does not belong exclusively to the recorded server PID.' }

# Re-read after OS checks: a new startup may have atomically replaced the receipt.
$current = Read-StartupReceipt
if ($current.pid -ne $receipt.pid -or $current.loggerPid -ne $receipt.loggerPid -or
    $current.startedAt -cne $receipt.startedAt -or $current.stopToken -cne $receipt.stopToken -or
    $current.stopPipe -cne $receipt.stopPipe -or $current.exitedAt) { throw 'Startup receipt changed during verification.' }
$request = @{ version = 1; pid = $receipt.pid; loggerPid = $receipt.loggerPid; startedAt = $receipt.startedAt;
    stopToken = $receipt.stopToken; requestedAt = [datetime]::UtcNow.ToString('o') }
$pipe = [IO.Pipes.NamedPipeClientStream]::new('.', $pipeName, [IO.Pipes.PipeDirection]::InOut, [IO.Pipes.PipeOptions]::Asynchronous)
$writer = $null
$reader = $null
try {
    $pipe.Connect(5000)
    $writer = [IO.StreamWriter]::new($pipe, [Text.UTF8Encoding]::new($false), 1024, $true)
    $reader = [IO.StreamReader]::new($pipe, [Text.UTF8Encoding]::new($false), $false, 1024, $true)
    $writer.WriteLine(($request | ConvertTo-Json -Compress))
    $writer.Flush()
    $reply = $reader.ReadLineAsync()
    if (!$reply.Wait(5000)) { throw 'Local stop channel did not acknowledge the request; inspect the server before retrying.' }
    $response = $reply.Result | ConvertFrom-Json
    if (!$response.accepted) { throw "Local stop request was rejected: $($response.error)" }
} finally {
    if ($reader) { $reader.Dispose() }
    if ($writer) { $writer.Dispose() }
    $pipe.Dispose()
}
Write-Output "Graceful shutdown requested. Waiting for connections, database and logs to finish..."

$deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
while ([datetime]::UtcNow -lt $deadline) {
    $state = Read-StartupReceipt
    if ($state.pid -ne $receipt.pid -or $state.loggerPid -ne $receipt.loggerPid -or $state.startedAt -cne $receipt.startedAt) { throw 'Receipt was replaced while waiting; inspect the original PID manually.' }
    if ($state.exitedAt) {
        if ($state.exitCode -ne 0 -or $state.signal -or !$state.gracefulStop.clean) { throw 'Server exited without a confirmed clean IPC shutdown; inspect its log.' }
        $original = Get-CimInstance Win32_Process -Filter "ProcessId = $([long]$receipt.pid)"
        if ($original -and [Math]::Abs((([datetime]$original.CreationDate).ToUniversalTime() - ([datetimeoffset]::Parse($receipt.startedAt)).UtcDateTime).TotalSeconds) -le 2) { throw 'Original server process has not exited yet.' }
        $remaining = @(Get-NetTCPConnection -LocalPort ([int]$receipt.httpPort) -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -eq $receipt.pid })
        if ($remaining.Count) { throw 'Original server still owns a listening socket.' }
        Write-Output "CN graceful shutdown completed. PID=$($receipt.pid) loggerPID=$($receipt.loggerPid)"
        return
    }
    if ($state.gracefulStop.state -eq 'timed-out') { throw 'Logger graceful-stop deadline expired; no hard kill was performed.' }
    if ($state.gracefulStop.state -eq 'ipc-failed') { throw 'Server IPC stop delivery failed; no hard kill was performed.' }
    Start-Sleep -Milliseconds 200
}
throw "Graceful shutdown did not finish in $TimeoutSeconds seconds. No process was force-killed; inspect the recorded PID and log."
