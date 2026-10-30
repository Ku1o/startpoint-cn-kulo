from pathlib import Path
import bootstrap
from input_config import input_path,work_path
import json
from apply_to_candidate import apply_to_candidate
from hashlib import sha256
ROOT=Path(__file__).resolve().parent

def main():
 out=work_path('carry163/contract-tests');out.mkdir(parents=True,exist_ok=False);checks=[]
 def reject(name,path,expected):
  try:apply_to_candidate(path,expected,work_path('carry163/output')/(name+'.swf'))
  except RuntimeError as e:checks.append({'case':name,'rejected':True,'reason':str(e).splitlines()[-1]})
  else:raise AssertionError('accepted '+name)
 p=input_path('r11_swf');reject('wrong-hash',p,'0'*64)
 p=input_path('old163_swf');reject('old-163-present',p,sha256(p.read_bytes()).hexdigest())
 p=input_path('carry_swf');reject('duplicate-helper',p,sha256(p.read_bytes()).hexdigest())
 report={'passed':True,'checks':checks};(out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
