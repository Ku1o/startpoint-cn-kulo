"""Bounded synchronous AIR AOT compilation, with process-tree cleanup."""
from prepare import WORK,LEGACY
from pathlib import Path
import subprocess,time,json

sdk=LEGACY/'AIRSDK_51.2.1.5'
compiler=sdk/'lib/aot/bin/compile-abc/compile-abc-64.exe'
deps=sorted(p for p in (LEGACY/'android-baseline/abc').glob('*.abc') if not p.name.startswith('284-'))
assert len(deps)==284
args=[str(compiler),'-mtriple=arm64-apple-ios',f'-fields={sdk}/lib/aot/lib/air-fields.arm64-air.txt',f'-sdk={sdk}/lib/aot/lib/avmglue.abc','-O=1',*map(str,deps),str(WORK/'compile/lens.abc')]
started=time.time()
with (WORK/'compile.log').open('w',encoding='utf-8') as log:
    p=subprocess.Popen(args,cwd=WORK/'compile',stdout=log,stderr=subprocess.STDOUT)
    try:
        p.wait(timeout=240)
        assert p.returncode==0,f'AIR compilation failed ({p.returncode}); see {WORK}/compile.log'
    except BaseException:
        subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True)
        p.wait();raise
print('AOT compile complete',round(time.time()-started,2),'seconds')
