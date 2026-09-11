"""Compile in an isolated directory; only one resulting function is packaged."""
from prepare import WORK, LEGACY
import subprocess, time

def main():
    sdk = LEGACY/'AIRSDK_51.2.1.5'
    compiler = sdk/'lib/aot/bin/compile-abc/compile-abc-64.exe'
    deps = sorted(p for p in (LEGACY/'android-baseline/abc').glob('*.abc') if not p.name.startswith('284-'))
    assert len(deps) == 284
    args = [str(compiler),'-mtriple=arm64-apple-ios',f'-fields={sdk}/lib/aot/lib/air-fields.arm64-air.txt',
            f'-sdk={sdk}/lib/aot/lib/avmglue.abc','-O=1',*map(str,deps),str(WORK/'compile/abyss.abc')]
    assert not any((WORK/'compile').glob('*.o')), 'refusing to overwrite a prior compilation'
    started = time.time()
    with (WORK/'compile.log').open('w',encoding='utf-8') as log:
        process = subprocess.Popen(args,cwd=WORK/'compile',stdout=log,stderr=subprocess.STDOUT)
        try:
            process.wait(timeout=240)
            assert process.returncode == 0, f'AIR compile failed: {WORK}/compile.log'
        finally:
            if process.poll() is None:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=15)
                process.wait(timeout=15)
    print('AOT compile complete',round(time.time()-started,2),'seconds')

if __name__ == '__main__': main()
