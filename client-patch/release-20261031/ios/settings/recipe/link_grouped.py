"""Use unchanged linker guards with new-only allocation grouped by compiler unwind."""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
cfg.bind_tools()
from pathlib import Path
import argparse,ast,inspect,json,re,sys
sys.dont_write_bytecode=True
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
SOURCE=Path(cfg.repo('client-patch'))
sys.path[:0]=[cfg.path('libraries'),str(SOURCE/'ios-r11-port')]
import link_stage,verify_stages as independent

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--prepared',type=Path,required=True);ap.add_argument('--compiled',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
 compiled=link_stage.read(args.compiled);objects={str(Path(compiled['directory'])/r['name']):independent.Object(Path(compiled['directory'])/r['name'],r['sha256']) for r in compiled['objects']};allocation=[]
 def order(item):
  mid,value=item;record,path,*_=value;fn=objects[str(path)].function(record.symbol);row=dict(method=mid,symbol=record.symbol,object=str(path),object_sha256=independent.sha(objects[str(path)].raw),compiler_encoding=fn['encoding'],inline_table=fn['code_size']<len(fn['data']),size=record.size)
  allocation.append(row);return row['inline_table'],row['compiler_encoding'],mid
 source=inspect.getsource(link_stage.original.run);tree=ast.parse(source);changed=0
 for node in ast.walk(tree):
  if isinstance(node,ast.For) and ast.unparse(node.target)=='(mid, (record, *_))':
   assert ast.unparse(node.iter)=='sorted(funcs.items())';node.iter.keywords.append(ast.keyword(arg='key',value=ast.Name(id='_new_unwind_order',ctx=ast.Load())));changed+=1
 assert changed==1,'allocation loop shape changed'
 ns=link_stage.original.__dict__.copy();ns['_new_unwind_order']=order;exec(compile(ast.fix_missing_locations(tree),str(Path(link_stage.original.__file__)), 'exec'),ns);adapted=ns['run']
 opt=argparse.Namespace(prepared=args.prepared,compiled=args.compiled,output=args.output,previous_link=Path(cfg.path('outputs_ios_r11_cumulative_compact_20261025_linked_link_report_json')),previous_package=Path(cfg.path('outputs_ios_r11_cumulative_compact_20261025_starpoint_ios_1_8_4_equipment_r11_compact_20261025_unsigned_json')),runtime_stubs=Path(cfg.path('runtime_stubs')),dependencies=Path(cfg.path('dependencies')))
 # The adapted function must resolve the existing report/input/allocator hooks
 # from the original module's mutable globals during link_stage's patches.
 from types import FunctionType
 link_stage.original.__dict__['_new_unwind_order']=order
 adapted=FunctionType(adapted.__code__,link_stage.original.__dict__)
 with patch.object(link_stage.original,'run',adapted):report=link_stage.run_link(opt)
 positions={int(r['method']):r['address'] for r in report['functions']}
 for row in allocation:row['linked_address']=positions[row['method']]
 allocation.sort(key=lambda r:r['linked_address']);proof=dict(strategy='group only newly allocated functions by inline-table flag and unchanged compiler compact-unwind encoding',source_linker=str(Path(link_stage.original.__file__)),source_linker_sha256=independent.sha(Path(link_stage.original.__file__).read_bytes()),adapter_sha256=independent.sha(Path(__file__).read_bytes()),modified_ast_nodes=1,compiled_report_sha256=independent.sha(args.compiled.read_bytes()),functions=allocation,old_addresses_or_objects_changed=False)
 independent.dump(args.output/'allocation-contract.json',proof);report['allocation_contract']=str(args.output.resolve()/'allocation-contract.json');report['allocation_contract_sha256']=independent.sha((args.output/'allocation-contract.json').read_bytes());link_stage.save(args.output/'link-report.json',report)
 print(json.dumps(dict(status=report['status'],functions=len(allocation),native_sha256=report['native_sha256'])))
if __name__=='__main__':main()
