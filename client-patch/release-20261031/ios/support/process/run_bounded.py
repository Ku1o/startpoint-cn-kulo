"""Task-local Windows process-tree memory limit; start suspended, then assign Job.

No unrestricted fallback. Each run has a wall timeout and file-output limit.
Reference: https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
"""
import argparse
import ctypes as c
from ctypes import wintypes as w
import json
import msvcrt
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

K = c.WinDLL('kernel32', use_last_error=True)
SIZE = c.c_size_t

class BASIC(c.Structure):
    _fields_ = [('processTime', c.c_int64), ('jobTime', c.c_int64),
                ('flags', w.DWORD), ('minWorkingSet', SIZE), ('maxWorkingSet', SIZE),
                ('activeLimit', w.DWORD), ('affinity', SIZE),
                ('priority', w.DWORD), ('scheduling', w.DWORD)]

class IO(c.Structure):
    _fields_ = [(n, c.c_uint64) for n in ('readOps','writeOps','otherOps','readBytes','writeBytes','otherBytes')]

class EXTENDED(c.Structure):
    _fields_ = [('basic', BASIC), ('io', IO), ('processMemory', SIZE), ('jobMemory', SIZE),
                ('peakProcess', SIZE), ('peakJob', SIZE)]

class ACCOUNTING(c.Structure):
    _fields_ = [(n, c.c_int64) for n in ('user','kernel','periodUser','periodKernel')] + [
        (n, w.DWORD) for n in ('faults','total','active','terminated')]

class STARTUP(c.Structure):
    _fields_ = [('cb', w.DWORD), ('reserved', w.LPWSTR), ('desktop', w.LPWSTR),
                ('title', w.LPWSTR)] + [(n,w.DWORD) for n in
                ('x','y','width','height','xchars','ychars','fill','flags')] + [
                ('show', w.WORD), ('reservedBytes', w.WORD), ('reserved2', c.POINTER(c.c_byte)),
                ('stdin', w.HANDLE), ('stdout', w.HANDLE), ('stderr', w.HANDLE)]

class PROCESS(c.Structure):
    _fields_ = [('process', w.HANDLE), ('thread', w.HANDLE), ('pid', w.DWORD), ('tid', w.DWORD)]

def bind(name, args, result):
    f=getattr(K,name); f.argtypes=args; f.restype=result; return f

create_job=bind('CreateJobObjectW',[c.c_void_p,w.LPCWSTR],w.HANDLE)
create_mutex=bind('CreateMutexW',[c.c_void_p,w.BOOL,w.LPCWSTR],w.HANDLE)
release_mutex=bind('ReleaseMutex',[w.HANDLE],w.BOOL)
set_job=bind('SetInformationJobObject',[w.HANDLE,c.c_int,c.c_void_p,w.DWORD],w.BOOL)
query_job=bind('QueryInformationJobObject',[w.HANDLE,c.c_int,c.c_void_p,w.DWORD,c.c_void_p],w.BOOL)
assign=bind('AssignProcessToJobObject',[w.HANDLE,w.HANDLE],w.BOOL)
create_process=bind('CreateProcessW',[w.LPCWSTR,w.LPWSTR,c.c_void_p,c.c_void_p,w.BOOL,w.DWORD,c.c_void_p,w.LPCWSTR,c.POINTER(STARTUP),c.POINTER(PROCESS)],w.BOOL)
resume=bind('ResumeThread',[w.HANDLE],w.DWORD)
wait=bind('WaitForSingleObject',[w.HANDLE,w.DWORD],w.DWORD)
get_exit=bind('GetExitCodeProcess',[w.HANDLE,c.POINTER(w.DWORD)],w.BOOL)
terminate_job=bind('TerminateJobObject',[w.HANDLE,w.UINT],w.BOOL)
terminate_process=bind('TerminateProcess',[w.HANDLE,w.UINT],w.BOOL)
close=bind('CloseHandle',[w.HANDLE],w.BOOL)

def checked(value):
    if not value: raise c.WinError(c.get_last_error())
    return value

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--limit-mib',type=int,default=1536)
    p.add_argument('--timeout',type=float,default=60)
    p.add_argument('--cwd',required=True)
    p.add_argument('--receipt',required=True)
    p.add_argument('command',nargs=argparse.REMAINDER)
    a=p.parse_args(); command=a.command[1:] if a.command[:1]==['--'] else a.command
    if not command or not 32<=a.limit_mib<=2048 or not 0<a.timeout<=180:
        raise ValueError('Require command, 32..2048 MiB and <=180 second timeout')
    exe=shutil.which(command[0])
    if not exe: raise FileNotFoundError(command[0])
    command[0]=str(Path(exe).resolve())
    receipt=Path(a.receipt); log=receipt.with_suffix('.log')
    if receipt.exists() or log.exists(): raise FileExistsError('Use a fresh receipt name')
    receipt.parent.mkdir(parents=True,exist_ok=True)
    mutex=checked(create_mutex(None,False,'Local\\Codex_TicketB_BoundedVerification'))
    owns_mutex=wait(mutex,0) in (0,0x80)
    if not owns_mutex:
        close(mutex); raise RuntimeError('Another bounded verification is already running')
    job=None; pi=PROCESS(); started=time.monotonic(); status='launcher_failed'; code=w.DWORD(1)
    report={'command':command,'cwd':a.cwd,'limitBytes':a.limit_mib*1024**2,
            'timeoutSeconds':a.timeout,'log':str(log),'startSuspended':True,
            'jobAssignedBeforeResume':False,'breakawayAllowed':False}
    try:
        job=checked(create_job(None,None)); info=EXTENDED()
        info.basic.flags=0x2000|0x200|0x100|0x8
        info.basic.activeLimit=8
        info.processMemory=info.jobMemory=report['limitBytes']
        checked(set_job(job,9,c.byref(info),c.sizeof(info)))
        installed=EXTENDED(); checked(query_job(job,9,c.byref(installed),c.sizeof(installed),None))
        if installed.jobMemory!=report['limitBytes'] or installed.basic.flags!=info.basic.flags:
            raise RuntimeError('Installed Job limits differ; refusing launch')
        with open(log,'xb',buffering=0) as output, open(os.devnull,'rb') as null:
            oh=msvcrt.get_osfhandle(output.fileno()); ih=msvcrt.get_osfhandle(null.fileno())
            os.set_handle_inheritable(oh,True); os.set_handle_inheritable(ih,True)
            si=STARTUP(); si.cb=c.sizeof(si); si.flags=0x100|0x1; si.show=0
            si.stdin=ih; si.stdout=si.stderr=oh
            env=dict(os.environ); env.pop('NODE_OPTIONS',None)
            env_block=c.create_unicode_buffer('\0'.join(f'{k}={v}' for k,v in sorted(env.items(),key=lambda x:x[0].upper()))+'\0\0')
            checked(create_process(command[0],c.create_unicode_buffer(subprocess.list2cmdline(command)),
                None,None,True,0x4|0x08000000|0x400,env_block,a.cwd,c.byref(si),c.byref(pi)))
            report['pid']=pi.pid
            checked(assign(job,pi.process)); report['jobAssignedBeforeResume']=True
            if resume(pi.thread)==0xffffffff: raise c.WinError(c.get_last_error())
            close(pi.thread); pi.thread=None
            status='exited'
            while wait(pi.process,100)==0x102:
                if time.monotonic()-started>a.timeout:
                    status='timeout'; checked(terminate_job(job,124)); break
                if log.stat().st_size>5*1024**2:
                    status='output_limit'; checked(terminate_job(job,125)); break
            checked(wait(pi.process,5000)==0)
            checked(get_exit(pi.process,c.byref(code)))
        peak=EXTENDED(); checked(query_job(job,9,c.byref(peak),c.sizeof(peak),None))
        report.update(peakJobCommitBytes=peak.peakJob,peakProcessCommitBytes=peak.peakProcess)
    finally:
        cleanup_ok=False
        report['activeProcessesAfterCleanup']=None
        if job:
            terminated=bool(terminate_job(job,126))
            report['terminateJobSucceeded']=terminated
            for _ in range(250):
                count=ACCOUNTING()
                if not query_job(job,1,c.byref(count),c.sizeof(count),None):
                    report['cleanupQueryError']=c.get_last_error(); break
                report['activeProcessesAfterCleanup']=count.active
                if count.active==0:
                    cleanup_ok=terminated; break
                time.sleep(.02)
        if pi.process:
            if not report['jobAssignedBeforeResume']:
                stopped=bool(terminate_process(pi.process,126)) and wait(pi.process,5000)==0
                report['unassignedProcessTerminated']=stopped
                cleanup_ok=cleanup_ok and stopped
            close(pi.process)
        if pi.thread: close(pi.thread)
        if job: close(job)
        report['cleanupConfirmed']=cleanup_ok
        if not cleanup_ok: status='cleanup_failed'
        release_mutex(mutex); close(mutex)
        report.update(status=status,exitCode=code.value,elapsedSeconds=round(time.monotonic()-started,3))
        receipt.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
    return 0 if status=='exited' and code.value==0 else 1

if __name__=='__main__': sys.exit(main())
