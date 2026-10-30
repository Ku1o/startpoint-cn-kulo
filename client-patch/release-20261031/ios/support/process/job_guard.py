"""Exact adopted Windows Job guard, without carrier globals or imports."""
import os, ctypes
def require(ok, message):
    if not ok: raise ValueError(message)

def require_bounded_job(wall_limit_seconds=60):
    """Refuse direct Python invocation outside the approved Windows Job tree."""
    require(os.name == 'nt', 'Windows bounded launcher required')
    require(0 < wall_limit_seconds <= 180, 'Task wall budget outside authorization')
    from ctypes import wintypes as w
    class Basic(ctypes.Structure):
        _fields_ = [('p',ctypes.c_int64),('j',ctypes.c_int64),('flags',w.DWORD),
                    ('minimum',ctypes.c_size_t),('maximum',ctypes.c_size_t),
                    ('active',w.DWORD),('affinity',ctypes.c_size_t),
                    ('priority',w.DWORD),('scheduling',w.DWORD)]
    class Io(ctypes.Structure):
        _fields_ = [(n,ctypes.c_uint64) for n in ('a','b','c','d','e','f')]
    class Extended(ctypes.Structure):
        _fields_ = [('basic',Basic),('io',Io),('process',ctypes.c_size_t),
                    ('job',ctypes.c_size_t),('peakProcess',ctypes.c_size_t),
                    ('peakJob',ctypes.c_size_t)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.IsProcessInJob.argtypes = [w.HANDLE,w.HANDLE,ctypes.POINTER(w.BOOL)]
    kernel.IsProcessInJob.restype = w.BOOL
    kernel.QueryInformationJobObject.argtypes = [w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.c_void_p]
    kernel.QueryInformationJobObject.restype = w.BOOL
    inside = w.BOOL()
    require(kernel.IsProcessInJob(kernel.GetCurrentProcess(),None,ctypes.byref(inside)) and inside.value,
            'Not running inside a Windows Job')
    current = Extended()
    require(kernel.QueryInformationJobObject(None,9,ctypes.byref(current),ctypes.sizeof(current),None),
            'Cannot inspect current Job; no unrestricted fallback')
    require(current.basic.flags & 0x2300 == 0x2300, 'Missing kill-on-close and process/job memory hard limits')
    require(not current.basic.flags & 0x1800, 'Breakaway/silent-breakaway Job is not permitted')
    require(0 < current.job <= 1536*1024**2 and 0 < current.process <= 1536*1024**2,
            'Current Job memory limit is outside this task authorization')
    return dict(jobMemoryBytes=current.job, processMemoryBytes=current.process,
                jobLimitFlags=current.basic.flags, launcherWallLimitRequiredSeconds=wall_limit_seconds,
                wallLimitEvidence='external run_bounded receipt; memory Job query does not establish wall timeout')
