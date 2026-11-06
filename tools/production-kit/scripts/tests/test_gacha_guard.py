"""Small allocation, timeout, child cleanup and cross-process slot probes."""
import json
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
if len(sys.argv) != 2:
    raise SystemExit('Usage: python test_gacha_guard.py <existing evidence directory>')
run = Path(sys.argv[1]).resolve() / ('guard-tests-' + str(time.time_ns()))
run.mkdir()

def command(name, source, timeout=10):
    return [sys.executable, '-X', 'utf8', '-B', str(root / 'gacha_guard.py'),
            '--memory-mib', '128', '--timeout', str(timeout), '--cwd', str(root),
            '--receipt', str(run / (name + '.json')), '--', sys.executable, '-B', '-u', '-c', source]

results = []
def probe(name, source, expected, status, timeout=10):
    completed = subprocess.run(command(name, source, timeout), capture_output=True, text=True, timeout=20)
    report = json.loads((run / (name + '.json')).read_text(encoding='utf-8'))
    assert completed.returncode == expected, (name, completed.returncode, completed.stderr[:1000])
    assert report['status'] == status, (name, report['status'])
    assert report['limitsReadBack'] is True
    assert report['activeProcessesAfterCleanup'] == 0
    results.append({'probe': name, 'status': status, 'exitCode': expected, 'cleanupActive': 0})

probe('normal', "print('small job success')", 0, 'completed')
probe('inherited-job', "import gacha_guard; assert gacha_guard.inherited_guard(); print('actual Job membership verified')", 0, 'completed')
probe('fake-marker', "import os,gacha_guard\nos.environ[gacha_guard.JOB_ENV]='Local\\\\CodexStarpointGachaJob_absent'\ntry:\n gacha_guard.inherited_guard()\nexcept OSError:\n raise SystemExit(72)\nraise SystemExit(99)", 72, 'command_failed')
probe('allocation-denied', "import sys\ntry:\n x=bytearray(512*1024*1024)\nexcept MemoryError:\n print('expected allocation rejection'); sys.exit(73)\nsys.exit(99)", 73, 'command_failed')
probe('timeout-tree', "import subprocess,sys,time\np=subprocess.Popen([sys.executable,'-B','-c','import time; time.sleep(60)'])\nprint('child',p.pid,flush=True)\ntime.sleep(60)", 124, 'timeout', 1)

holder = subprocess.Popen(command('slot-holder', "import time; print('slot ready',flush=True); time.sleep(2)"), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
try:
    deadline = time.monotonic() + 5
    while not (run / 'slot-holder.log').exists() or (run / 'slot-holder.log').stat().st_size == 0:
        if time.monotonic() >= deadline:
            raise RuntimeError('holder did not start')
        time.sleep(.05)
    busy = subprocess.run(command('slot-busy', "raise RuntimeError('must not start')"), capture_output=True, text=True, timeout=10)
    report = json.loads((run / 'slot-busy.json').read_text(encoding='utf-8'))
    assert busy.returncode == 75 and report['status'] == 'slot_busy_no_process_started'
    assert 'pid' not in report
    assert holder.wait(timeout=10) == 0
    results.append({'probe': 'shared-slot', 'secondExitCode': 75, 'secondProcessStarted': False})
finally:
    if holder.poll() is None:
        holder.terminate()
        holder.wait(timeout=10)

summary = {'tests': results, 'directory': str(run), 'scope': 'Windows committed-memory denial, cleanup and exclusivity only; not crash root cause diagnosis'}
(run / 'RESULT.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary))
