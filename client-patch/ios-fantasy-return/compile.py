"""Bounded headless AIR compilation; package only the donor function."""
from common import *
import subprocess,time

def main():
    dest=WORK/'compile';dest.mkdir()
    source=WORK/'navigation-compiler-input.abc'
    assert sha(source.read_bytes())==json.loads((WORK/'prepare.json').read_text())['compiler_input_sha256']
    deps=sorted(p for p in (LEGACY/'android-baseline/abc').glob('*.abc') if not p.name.startswith('284-'))
    assert len(deps)==284
    args=[str(SDK/'lib/aot/bin/compile-abc/compile-abc-64.exe'),'-mtriple=arm64-apple-ios',
          '-fields='+str(SDK/'lib/aot/lib/air-fields.arm64-air.txt'),'-sdk='+str(SDK/'lib/aot/lib/avmglue.abc'),
          '-O=1','-verify-warnings',*map(str,deps),str(source)]
    started=time.monotonic()
    with (WORK/'compile.log').open('wb') as log:
        proc=subprocess.Popen(args,cwd=dest,stdout=log,stderr=subprocess.STDOUT)
        try:
            assert proc.wait(timeout=240)==0,'AIR compilation failed; see compile.log'
        finally:
            if proc.poll() is None:
                subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,timeout=15)
                proc.wait(timeout=15)
    dump(WORK/'compile-report.json',dict(elapsed_seconds=time.monotonic()-started,
         objects=[dict(path=str(p),sha256=sha(p.read_bytes())) for p in dest.glob('*.o')]))
    print('Compiled in',round(time.monotonic()-started,1),'seconds')

if __name__=='__main__':main()
