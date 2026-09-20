"""Run the unchanged lifecycle harness against the exact iOS helper source."""
from pathlib import Path
import sys,json,shutil,subprocess,importlib.util
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent));import prepare as p
def main():
    work=p.WORK/'session-tests';work.mkdir(exist_ok=False)
    src=HERE.parent.parent/'r10-public-release/tests'
    for name in ['SessionHarness.as','harness-app.xml']:shutil.copy2(src/name,work/name)
    args=[p.build.JAVA,'-Dflexlib='+str(p.SDK/'frameworks'),'-Xmx512m','-jar',p.SDK/'lib/mxmlc-cli.jar',
          '+configname=air','-swf-version=44','-target-player=32.0','-debug=false',
          '-compiler.source-path='+str(p.WORK/'generated'),'-output='+str(work/'SessionHarness.swf'),work/'SessionHarness.as']
    p.build.run(args,work,'compile')
    with (work/'run.log').open('wb') as log:
        r=subprocess.run([str(p.SDK/'bin/adl.exe'),'-nodebug',str(work/'harness-app.xml')],cwd=work,stdout=log,stderr=subprocess.STDOUT,timeout=30)
    result=json.loads((work/'session-results.json').read_text('utf-8'))
    assert r.returncode==0 and result['passed'] and result['assertions']==56
    print(json.dumps(result))
if __name__=='__main__':main()
