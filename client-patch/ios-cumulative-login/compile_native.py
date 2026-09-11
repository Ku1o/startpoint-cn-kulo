"""Run only the headless arm64 AIR compiler, with a bounded process tree."""
from prepare import WORK,LEGACY,SDK,dump,sha
import argparse,json,subprocess,time

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--attempt',default='compile');ap.add_argument('--optimization',choices=['0','1'],default='1');ap.add_argument('--raw-ir',action='store_true');args0=ap.parse_args()
    assert args0.attempt.replace('-','').isalnum()
    directory=WORK/args0.attempt;directory.mkdir(exist_ok=True)
    port=json.loads((WORK/'port.json').read_text('utf8'))
    source=(WORK/port['full_abc_file']).read_bytes();assert sha(source)==port['full_abc_sha256']
    if not (directory/'cumulative.abc').exists():(directory/'cumulative.abc').write_bytes(source)
    else:assert (directory/'cumulative.abc').read_bytes()==source
    compiler=SDK/'lib/aot/bin/compile-abc/compile-abc-64.exe'
    deps=sorted((LEGACY/'android-baseline/abc').glob('*.abc'))
    deps=[p for p in deps if not p.name.startswith('284-')]
    assert len(deps)==284,len(deps)
    args=[str(compiler),'-mtriple=arm64-apple-ios','-fields='+str(SDK/'lib/aot/lib/air-fields.arm64-air.txt'),
        '-sdk='+str(SDK/'lib/aot/lib/avmglue.abc'),'-O='+args0.optimization,'-verify-warnings',
        *(['-save-raw-ll'] if args0.raw_ir else []),*[str(p) for p in deps],str(directory/'cumulative.abc')]
    assert not list(directory.glob('*.o')),'refusing to overwrite compiler outputs'
    started=time.monotonic()
    log_path=WORK/(args0.attempt+'.log')
    with log_path.open('wb') as log:
        p=subprocess.Popen(args,cwd=directory,stdout=log,stderr=subprocess.STDOUT)
        try:
            code=p.wait(timeout=240)
            assert code==0,('compiler failed',code,str(log_path))
        finally:
            if p.poll() is None:subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True,timeout=15)
    result=dict(elapsed_seconds=round(time.monotonic()-started,2),headless=True,directory=str(directory),optimization=args0.optimization,objects=[dict(name=p.name,bytes=p.stat().st_size,sha256=sha(p.read_bytes())) for p in sorted(directory.glob('cumulative*.o'))])
    dump(WORK/(args0.attempt+'-report.json'),result)
    print('Compiled native objects:',len(result['objects']),'elapsed:',result['elapsed_seconds'])

if __name__=='__main__':main()
