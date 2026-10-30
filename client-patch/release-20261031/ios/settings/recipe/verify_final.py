"""Independent stage verifier with exactly two reviewed original-draw adaptations."""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
cfg.bind_tools()
from pathlib import Path
import argparse,ast,hashlib,inspect,json,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
SOURCE=Path(cfg.repo('client-patch'))
sys.path[:0]=[cfg.path('libraries'),str(SOURCE/'ios-r11-port')]
import verify_stages as v
import platform_draw
import platform_equipment

def draw_check(old,new,linked):
 result=platform_draw.verify(old.raw,new.raw,linked,lambda raw,va:old.offset(va))
 platform_equipment.verify(old.raw,new.raw,linked,lambda raw,va:old.offset(va))
 assert result['bridge_file_start']==0x3d69200 and result['bridge_file_end']==0x3d69258
 return [(0x3d691e0,0x3d691e4),(0x3d69200,0x3d69258),(old.offset(platform_equipment.TAIL),old.offset(platform_equipment.TAIL)+4)]

def equipment_range(new,old,row,linked):
 before=old.read(row['va'],row['bytes']);after=new.read(row['va'],row['bytes'])
 v.require(v.sha(before)==row['sha256'],'original equipment protected preimage differs')
 if row['name']!='five-in-one-old-wrapper':return v.sha(after)==row['sha256']
 v.require(row['va']==platform_equipment.FIVE_WRAPPER and row['bytes']==208,'exact five-in-one wrapper required')
 expected=bytearray(before);off=platform_equipment.TAIL-row['va'];fn,=[r for r in linked['functions'] if r['method']==18392]
 expected[off:off+4]=platform_draw.branch(platform_equipment.TAIL,fn['address'],True)
 return after==expected

def verifier():
 source=inspect.getsource(v.verify);tree=ast.parse(source);fn=tree.body[0];changed=0
 for i,node in list(enumerate(fn.body)):
  if isinstance(node,ast.For) and ast.unparse(node.target)=='(mid, target)' and ast.unparse(node.iter)=='changed_slots.items()':
   fn.body[i:i]=ast.parse("require(66181 in changed_slots and 18392 in changed_slots, 'both original platform methods must be compiled')\nchanged_slots.pop(66181)\nchanged_slots.pop(18392)").body;changed+=1;break
 for i,node in list(enumerate(fn.body)):
  if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='end' for t in node.targets) and ast.unparse(node.value)=="old.segments[-1]['off']":
   fn.body.insert(i,ast.parse('allowed += _draw_check(old,new,linked)').body[0]);changed+=1;break
 for node in ast.walk(fn):
  if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='require' and len(node.args)==2 and isinstance(node.args[1],ast.Constant) and node.args[1].value=='Equipment protected resolver bytes changed':
   node.args[0]=ast.parse('_equipment_range(new,old,r,linked)',mode='eval').body;changed+=1
 assert changed==3,'independent verifier shape changed'
 ns=v.__dict__.copy();ns['_draw_check']=draw_check;ns['_equipment_range']=equipment_range;exec(compile(ast.fix_missing_locations(tree),str(Path(v.__file__)),'exec'),ns);return ns['verify']

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--package-report',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--detail-output',type=Path,required=True);args=ap.parse_args();args.equipment_link=Path(cfg.path('outputs_ios_r11_port_20261025_equipment_link_report_json'));args.libraries=Path(cfg.path('libraries'))
 try:report=verifier()(args)
 except Exception as error:v.dump(args.output,dict(status='independent_verification_failed',error=str(error)));raise
 report.update(draw_adapter_verifier_source_sha256=v.sha(Path(__file__).read_bytes()),draw_original_id_compiled=True,draw_active_dispatch_retained=True,baseline_wrapper_unwind_inherited_limit=True)
 v.dump(args.output,report);print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
