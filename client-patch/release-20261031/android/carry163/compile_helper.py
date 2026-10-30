from pathlib import Path
import json,subprocess,zipfile,hashlib,sys,struct,zlib
ROOT=Path(__file__).resolve().parent
import bootstrap
from input_config import runtime,work_path
from swfabc import swftags,abcfmt

# Original adopted bytes; the current source differs only by LF/EOF normalization.
ORIGINAL_SOURCE_SHA256='6ac6ff8f5eead3984f932c9d7a4cfb58b058452c0311d058ebd00a6a7d30b856'

def main():
 assert hashlib.sha256((ROOT/'src/cn/carry/StageCarryState.as').read_bytes()).hexdigest()=='2e4141d743ce2aff36b4b649fe350c4a644b90938af2f7a2b65eef2152a86443','adopted helper source changed'
 out=work_path('carry163/helper-build');out.mkdir(parents=True,exist_ok=False);cfg=runtime();sdk=Path(cfg['sdk']);cmd=[cfg['java'],'-Dflexlib='+str(sdk/'frameworks'),'-jar',str(sdk/'lib/compc-cli.jar'),'+configname=air','-compiler.float=false','-debug=false','-compiler.source-path='+str(ROOT/'src'),'-include-classes=cn.carry.StageCarryState','-output='+str(out/'StageCarryState.swc')];p=subprocess.run(cmd,cwd=out,capture_output=True,timeout=90);(out/'compile.log').write_bytes(p.stdout+p.stderr)
 if p.returncode:raise RuntimeError('helper compile failed')
 raw=zipfile.ZipFile(out/'StageCarryState.swc').read('library.swf');(out/'library.swf').write_bytes(raw);_,_,_,body=swftags.load_swf(str(out/'library.swf'));units=[]
 for c,a,h,n in swftags.iter_tags(body):
  if c==82:
   p=body[a+h:a+h+n];nul=p.index(b'\0',4);units.append(p[nul+1:])
 assert len(units)==1;abc=abcfmt.ABC(units[0]);assert [abc.mn_name(r[0]) for r in abc.instances]==['cn.carry::StageCarryState'];assert hashlib.sha256(units[0]).hexdigest()=='6849f52ea234769bb73fadad08604e9f8009b4e4fc0a0c01c22a7d9284c507a5','adopted helper ABC changed';(out/'StageCarryState.abc').write_bytes(units[0]);report={'exit_code':0,'command':cmd,'source_sha256':hashlib.sha256((ROOT/'src/cn/carry/StageCarryState.as').read_bytes()).hexdigest(),'abc_sha256':hashlib.sha256(units[0]).hexdigest(),'classes':1,'methods':len(abc.bodies),'native_device_tested':False};(out/'compile-receipt.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
