param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 2147483647)]
    [int] $ProcessId
)

$ErrorActionPreference = 'Stop'
if ([IntPtr]::Size -ne 8) { throw 'Run this diagnostic with 64-bit PowerShell.' }

# Queries region metadata only; it never reads process memory contents,
# suspends the process, changes protection, or empties its working set.
if (-not ('StarPointRegionProbe' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;

public static class StarPointRegionProbe {
    [StructLayout(LayoutKind.Sequential)]
    struct Region {
        public IntPtr BaseAddress, AllocationBase;
        public uint AllocationProtect;
        public UIntPtr RegionSize;
        public uint State, Protect, Type;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct SystemInfo {
        public uint ProcessorInfo, PageSize;
        public IntPtr MinimumAddress, MaximumAddress;
        public UIntPtr ProcessorMask;
        public uint ProcessorCount, ProcessorType, AllocationGranularity;
        public ushort ProcessorLevel, ProcessorRevision;
    }
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern UIntPtr VirtualQueryEx(IntPtr process, IntPtr address, out Region region, UIntPtr length);
    [DllImport("kernel32.dll")]
    static extern void GetNativeSystemInfo(out SystemInfo info);
    [DllImport("kernel32.dll")]
    static extern bool CloseHandle(IntPtr handle);

    public static Dictionary<string,long> Capture(int pid) {
        IntPtr handle = OpenProcess(0x0400, false, pid); // PROCESS_QUERY_INFORMATION
        if (handle == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
        var totals = new Dictionary<string,long> {
            {"privateCommittedBytes",0}, {"mappedCommittedBytes",0},
            {"imageCommittedBytes",0}, {"otherCommittedBytes",0},
            {"reservedBytes",0}, {"regionCount",0}
        };
        try {
            SystemInfo info; GetNativeSystemInfo(out info);
            long address = info.MinimumAddress.ToInt64(), maximum = info.MaximumAddress.ToInt64();
            var watch = Stopwatch.StartNew();
            while (address < maximum) {
                if (totals["regionCount"] >= 1000000 || watch.ElapsedMilliseconds > 5000)
                    throw new InvalidOperationException("Region scan exceeded its bounded budget; no complete sample available.");
                Region region;
                if (VirtualQueryEx(handle, new IntPtr(address), out region,
                    new UIntPtr((uint)Marshal.SizeOf(typeof(Region)))).ToUInt64() == 0)
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                long bytes = checked((long)region.RegionSize.ToUInt64());
                long next = checked(region.BaseAddress.ToInt64() + bytes);
                if (bytes <= 0 || next <= address) throw new InvalidOperationException("Non-progressing region scan.");
                totals["regionCount"]++;
                if (region.State == 0x1000) {
                    string key = region.Type == 0x20000 ? "privateCommittedBytes"
                        : region.Type == 0x40000 ? "mappedCommittedBytes"
                        : region.Type == 0x1000000 ? "imageCommittedBytes" : "otherCommittedBytes";
                    totals[key] += bytes;
                } else if (region.State == 0x2000) totals["reservedBytes"] += bytes;
                address = next;
            }
            return totals;
        } finally { CloseHandle(handle); }
    }
}
'@
}

$targetProcess = Get-Process -Id $ProcessId
try {
    $startedAt = $targetProcess.StartTime.ToUniversalTime().ToString('o')
    $regions = [StarPointRegionProbe]::Capture($ProcessId)
    $targetProcess.Refresh()
    if ($targetProcess.HasExited) { throw 'Target exited during collection; discard this sample.' }
    [ordered]@{
        timestamp = [DateTime]::UtcNow.ToString('o')
        pid = $ProcessId
        processStartedAt = $startedAt
        privateBytes = $targetProcess.PrivateMemorySize64
        workingSetBytes = $targetProcess.WorkingSet64
        virtualBytes = $targetProcess.VirtualMemorySize64
        handleCount = $targetProcess.HandleCount
        threadCount = $targetProcess.Threads.Count
        regions = $regions
    } | ConvertTo-Json -Compress -Depth 3
} finally { $targetProcess.Dispose() }
