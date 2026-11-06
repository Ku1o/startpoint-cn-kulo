"""Maintained Windows gacha guard: one shared slot and bounded process tree.

Reuses the existing local Windows process definitions without changing that tool.
This wrapper does not launch AIR directly; keep run_background.py inside it.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes as w
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

if os.name == 'nt':
    import msvcrt

SUPPORT = Path(__file__).resolve().parents[2] / 'client-background/quiet_process.py'
SLOT = 'Local\\CodexStarpointGachaResourceSlotV1'
JOB_ENV = 'CODEX_GACHA_RESOURCE_JOB'


def receipt_root():
    configured = os.environ.get('STARPOINT_GACHA_RECEIPTS')
    work = os.environ.get('STARPOINT_WORK_ROOT')
    if not configured and not work:
        raise ValueError('Set STARPOINT_WORK_ROOT or STARPOINT_GACHA_RECEIPTS outside the source repository')
    value = Path(configured) if configured else Path(work) / 'gacha-resource-runs'
    if not value.is_absolute():
        raise ValueError('Gacha receipt root must be absolute')
    value = value.resolve()
    repository = Path(__file__).resolve().parents[3]
    if value == Path(value.anchor) or value.is_relative_to(repository) or repository.is_relative_to(value):
        raise ValueError('Gacha receipts must use a dedicated directory outside the source repository')
    if any(part.lower() in {'.git', '.cdn'} for part in value.parts):
        raise ValueError('Gacha receipt destination is protected')
    return value


def process_support():
    spec = importlib.util.spec_from_file_location('gacha_existing_windows_process', SUPPORT)
    q = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(q)
    return q


def inherited_guard():
    """An environment marker alone is insufficient; verify actual Job membership."""
    name = os.environ.get(JOB_ENV)
    if not name:
        return False
    if os.name != 'nt' or not name.startswith('Local\\CodexStarpointGachaJob_'):
        raise RuntimeError('Invalid inherited gacha resource guard')
    q = process_support()
    open_job = q._bind(q._kernel, 'OpenJobObjectW', w.HANDLE, w.DWORD, w.BOOL, w.LPCWSTR)
    current = q._bind(q._kernel, 'GetCurrentProcess', w.HANDLE)
    member = q._bind(q._kernel, 'IsProcessInJob', w.BOOL, w.HANDLE, w.HANDLE, ctypes.POINTER(w.BOOL))
    handle = q._checked(open_job(4, False, name))
    try:
        inside = w.BOOL()
        q._checked(member(current(), handle, ctypes.byref(inside)))
        limit = q.JOB_EXTENDED_LIMIT()
        q._checked(q._QueryJob(handle, 9, ctypes.byref(limit), ctypes.sizeof(limit), None))
        flags = limit.BasicLimitInformation.LimitFlags
        if not inside.value or flags & 0x2200 != 0x2200 or flags & 0x1800 or not 64 * 1024**2 <= limit.JobMemoryLimit <= 2048 * 1024**2:
            raise RuntimeError('Inherited Job does not enforce gacha limits')
        return True
    finally:
        q._CloseHandle(handle)


def cli_result(tail):
    """Read a bounded final JSON object, including native CLI's pretty JSON."""
    lines = tail.rstrip().splitlines()
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].startswith('{'):
            try:
                value = json.loads('\n'.join(lines[index:]))
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                pass
    return None


def guarded_main(callback, *, heavy=False):
    """Guard CLI entrypoints once; all subprocesses inherit the same limited Job."""
    if '--help' in sys.argv[1:] or '-h' in sys.argv[1:]:
        return callback()
    try:
        if inherited_guard():
            return callback()
        if os.name != 'nt':
            raise RuntimeError('This gacha CLI needs a supported process-tree resource guard')
        command = sys.argv[1] if len(sys.argv) > 1 else ''
        memory = 2048 if heavy or command in {'build', 'resume', 'capture', '_record'} else 512
        timeout = 1800 if memory == 2048 else 600
        receipts = receipt_root()
        receipts.mkdir(parents=True, exist_ok=True)
        receipt = receipts / (Path(sys.argv[0]).stem + '-' + uuid.uuid4().hex + '.json')
        args = [sys.executable, '-X', 'utf8', '-B', str(Path(__file__).resolve()),
                '--memory-mib', str(memory), '--timeout', str(timeout),
                '--cwd', str(Path.cwd()), '--receipt', str(receipt), '--',
                sys.executable, '-X', 'utf8', '-B', str(Path(sys.argv[0]).resolve()), *sys.argv[1:]]
        done = subprocess.run(args, stdout=subprocess.DEVNULL, timeout=timeout + 20)
        record = json.loads(receipt.read_text(encoding='utf8'))
        log = receipt.with_suffix('.log')
        tail = ''
        if log.is_file():
            with log.open('rb') as stream:
                stream.seek(max(0, log.stat().st_size - 65536))
                tail = stream.read(65536).decode('utf8', errors='replace')
        result = {'status': record['status'], 'exitCode': done.returncode}
        # Preserve compact pipeline and pretty native results from the bounded
        # log tail, without loading arbitrary diagnostics into the orchestrator.
        parsed = cli_result(tail)
        if parsed is not None:
            result = parsed
        if done.returncode:
            result.update(status=record['status'], exitCode=done.returncode, diagnosticTail=tail[-2000:])
        result['resourceGuard'] = {'receipt': str(receipt), 'memoryMiB': memory, 'log': str(log)}
        print(json.dumps(result, ensure_ascii=False))
        return done.returncode
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'guard_failed_closed', 'error': str(exc)[:2000]}), file=sys.stderr)
        return 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--memory-mib', type=int, default=512)
    p.add_argument('--timeout', type=float, default=900)
    p.add_argument('--reserve-mib', type=int, default=4096)
    p.add_argument('--cwd', type=Path, required=True)
    p.add_argument('--receipt', type=Path, required=True)
    p.add_argument('command', nargs=argparse.REMAINDER)
    args = p.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if os.name != 'nt' or not command:
        p.error('Windows and an explicit command after -- are required')
    if not 64 <= args.memory_mib <= 2048 or args.reserve_mib < 4096:
        p.error('memory must be 64..2048 MiB; reserve must be at least 4096 MiB')
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= 1800:
        p.error('timeout must be positive and at most 1800 seconds')
    if not args.cwd.is_dir() or args.receipt.exists():
        p.error('cwd must exist and receipt must be a new file')
    log = args.receipt.with_suffix('.log')
    if log.exists():
        p.error('log must be a new file')
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    q = process_support()
    create_mutex = q._bind(q._kernel, 'CreateMutexW', w.HANDLE, ctypes.c_void_p, w.BOOL, w.LPCWSTR)
    release_mutex = q._bind(q._kernel, 'ReleaseMutex', w.BOOL, w.HANDLE)

    class MEMORY(ctypes.Structure):
        _fields_ = [('length', w.DWORD), ('load', w.DWORD)] + [
            (n, ctypes.c_ulonglong) for n in ('total', 'available', 'pageTotal', 'pageAvailable', 'virtualTotal', 'virtualAvailable', 'extended')]

    get_memory = q._bind(q._kernel, 'GlobalMemoryStatusEx', w.BOOL, ctypes.POINTER(MEMORY))

    def available_mib():
        m = MEMORY()
        m.length = ctypes.sizeof(m)
        q._checked(get_memory(ctypes.byref(m)))
        return m.available // (1024 * 1024)

    report = {'schemaVersion': 1, 'memoryLimitMiB': args.memory_mib,
              'memoryScope': 'Windows Job committed memory for the launched process tree; excludes unrelated apps and GPU memory',
              'timeoutSeconds': args.timeout, 'slot': SLOT, 'cwd': str(args.cwd),
              'command': command, 'log': str(log), 'status': 'not_started',
              'activeProcessesAfterCleanup': None}
    mutex = job = None
    owns_slot = assigned = False
    proc = q.PROCESS_INFORMATION()
    attributes = None
    attributes_ready = False
    started = time.monotonic()
    code = 1
    try:
        mutex = q._checked(create_mutex(None, False, SLOT))
        wait = q._Wait(mutex, 0)
        if wait == 0x102:
            report['status'] = 'slot_busy_no_process_started'
            return_code = 75
        elif wait not in (0, 0x80):
            raise ctypes.WinError(ctypes.get_last_error())
        else:
            owns_slot = True
            report['availablePhysicalMiBBefore'] = available_mib()
            if report['availablePhysicalMiBBefore'] < args.memory_mib + args.reserve_mib:
                report['status'] = 'insufficient_headroom_no_process_started'
                return_code = 75
            else:
                requested = Path(command[0])
                executable = shutil.which(command[0]) if not os.path.dirname(command[0]) else str((requested if requested.is_absolute() else args.cwd / requested).resolve())
                if not executable or Path(executable).suffix.lower() in ('.cmd', '.bat'):
                    raise ValueError('Use an explicit executable, not an implicit shell or batch file')
                with open(log, 'xb', buffering=0) as output, open(os.devnull, 'rb') as input_file:
                    handles = [msvcrt.get_osfhandle(f.fileno()) for f in (input_file, output)]
                    for h in handles:
                        os.set_handle_inheritable(h, True)
                    si = q.STARTUPINFOEX()
                    si.StartupInfo.cb = ctypes.sizeof(si)
                    si.StartupInfo.dwFlags = 0x100 | 0x80
                    si.StartupInfo.hStdInput = handles[0]
                    si.StartupInfo.hStdOutput = si.StartupInfo.hStdError = handles[1]
                    size = ctypes.c_size_t()
                    q._InitializeAttributes(None, 1, 0, ctypes.byref(size))
                    attributes = ctypes.create_string_buffer(size.value)
                    q._checked(q._InitializeAttributes(attributes, 1, 0, ctypes.byref(size)))
                    attributes_ready = True
                    si.lpAttributeList = ctypes.cast(attributes, ctypes.c_void_p)
                    inherited = (w.HANDLE * len(handles))(*handles)
                    q._checked(q._UpdateAttribute(attributes, 0, 0x20002, inherited, ctypes.sizeof(inherited), None, None))
                    job_name = 'Local\\CodexStarpointGachaJob_' + uuid.uuid4().hex
                    job = q._checked(q._CreateJob(None, job_name))
                    limits = q.JOB_EXTENDED_LIMIT()
                    limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x200  # kill on close + total Job memory; no breakaway
                    limits.JobMemoryLimit = args.memory_mib * 1024 * 1024
                    q._checked(q._SetJob(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
                    verified = q.JOB_EXTENDED_LIMIT()
                    q._checked(q._QueryJob(job, 9, ctypes.byref(verified), ctypes.sizeof(verified), None))
                    if verified.JobMemoryLimit != limits.JobMemoryLimit or verified.BasicLimitInformation.LimitFlags & 0x2200 != 0x2200:
                        raise RuntimeError('Job limits did not read back; refusing to launch')
                    report['limitsReadBack'] = True
                    env = dict(os.environ)
                    env.update(OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2', MKL_NUM_THREADS='2', MAGICK_THREAD_LIMIT='2')
                    env[JOB_ENV] = job_name
                    report['jobName'] = job_name
                    environment = ctypes.create_unicode_buffer('\0'.join(k + '=' + v for k, v in sorted(env.items(), key=lambda pair: pair[0].upper())) + '\0\0')
                    cmdline = ctypes.create_unicode_buffer(subprocess.list2cmdline(command))
                    q._checked(q._CreateProcess(executable, cmdline, None, None, True, 0x4 | 0x80000 | 0x08000000 | 0x400,
                                               environment, str(args.cwd.resolve()), ctypes.byref(si), ctypes.byref(proc)))
                    report['pid'] = proc.dwProcessId
                    q._checked(q._AssignJob(job, proc.hProcess))
                    assigned = True
                    if q._ResumeThread(proc.hThread) == 0xFFFFFFFF:
                        raise ctypes.WinError(ctypes.get_last_error())
                    deadline = time.monotonic() + args.timeout
                    report['status'] = 'running'
                    return_code = 1
                    while True:
                        outcome = q._Wait(proc.hProcess, 200)
                        if outcome == 0:
                            exit_code = w.DWORD()
                            q._checked(q._ExitCode(proc.hProcess, ctypes.byref(exit_code)))
                            return_code = exit_code.value
                            report['status'] = 'completed' if return_code == 0 else 'command_failed'
                            break
                        if outcome != 0x102:
                            raise ctypes.WinError(ctypes.get_last_error())
                        if time.monotonic() >= deadline:
                            report['status'], return_code = 'timeout', 124
                            break
                        if available_mib() < args.reserve_mib:
                            report['status'], return_code = 'system_headroom_stop', 76
                            break
                        if output.tell() > 64 * 1024 * 1024:
                            report['status'], return_code = 'log_budget_stop', 77
                            break
        code = return_code
    except KeyboardInterrupt:
        report['status'], code = 'interrupted', 130
    except Exception as exc:
        report['status'], code = 'guard_failed_closed', 1
        report['error'] = str(exc)[:2000]
    finally:
        try:
            if proc.hProcess:
                if assigned:
                    q._stop_job(job, proc.hProcess)
                else:
                    q._checked(q._TerminateProcess(proc.hProcess, 124))
                    if q._Wait(proc.hProcess, 10000) != 0:
                        raise RuntimeError('unassigned suspended process did not exit')
            if job:
                info = q.JOB_ACCOUNTING()
                q._checked(q._QueryJob(job, 1, ctypes.byref(info), ctypes.sizeof(info), None))
                report['activeProcessesAfterCleanup'] = info.ActiveProcesses
                if info.ActiveProcesses:
                    raise RuntimeError('Job still contains active processes')
                peak = q.JOB_EXTENDED_LIMIT()
                q._checked(q._QueryJob(job, 9, ctypes.byref(peak), ctypes.sizeof(peak), None))
                report['jobPeakReportedBytes'] = peak.PeakJobMemoryUsed
                report['peakNote'] = 'Windows accounting can include a rejected allocation; not a sampled RSS maximum.'
        except Exception as exc:
            report['cleanupError'], code = str(exc)[:2000], 1
        finally:
            if attributes_ready:
                q._DeleteAttributes(attributes)
            for handle in (proc.hThread, proc.hProcess, job):
                if handle:
                    q._CloseHandle(handle)
            if owns_slot:
                if not release_mutex(mutex):
                    report['mutexReleaseError'], code = ctypes.get_last_error(), 1
            if mutex:
                q._CloseHandle(mutex)
            report['exitCode'] = code
            report['elapsedSeconds'] = round(time.monotonic() - started, 3)
            args.receipt.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(json.dumps({'status': report['status'], 'exitCode': code, 'receipt': str(args.receipt)}, ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
