"""Actual-object switch corruption controls and final-native argument ABI checks."""
import argparse,json,struct,sys,types
from pathlib import Path
sys.dont_write_bytecode=True
import ios_repair as c


def main():
 ap=argparse.ArgumentParser();ap.add_argument('--inputs',type=Path,required=True);ap.add_argument('--linked',type=Path,required=True);ap.add_argument('--proof',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
 job=c.configure(args);c.framework();c.fresh(args.output)
 import lief,capstone,native_support as ns
 sys.path.insert(0,str(c.RECIPE/'settings/recipe'))
 import ios_switch
 linked=c.read(args.linked);compiled=c.read(linked['compiled_report']);proof=c.read(args.proof)
 c.require(proof['result']['status']=='independent_actual_stage_package_readback_passed' and proof['result']['native_sha256']==linked['native_sha256'],'Actual IPA readback missing')
 rows={r['method']:r for r in linked['functions']};cases=[]
 for object_row in compiled['objects']:
  path=Path(compiled['directory'])/object_row['name'];c.require(c.sha(path.read_bytes())==object_row['sha256'],'Object changed');obj=lief.parse(str(path))
  for sym in obj.symbols:
   if not sym.numberof_sections:continue
   matches=[mid for mid in (76815,76817) if f':{mid}:' in str(sym.name)]
   if not matches:continue
   mid,=matches;record,_,section,_,relocs=ns.symbol_record(obj,path,str(sym.name),mid)
   code=next(r['code_size'] for r in c.read(args.proof.with_name(args.proof.name.replace('-proof','-details')))['functions'] if r['method']==mid)
   good=ios_switch.verify_switch_tables(record,section,relocs,code);start=record.source_start-section.virtual_address
   for table in good['tables']:
    dispatch=table['dispatch'];cases.append(dict(method=mid,table=table['offset'],case='valid',passed=True))
    mutations=[('table_target',table['offset'],lambda word:0x7fffffff),('compare_bound',dispatch['bound_compare_offset'],lambda word:word+(1<<10)),('unsigned_guard',dispatch['bound_branch_offset'],lambda word:word^1),('u32_definition',dispatch['u32_definition_offset'],lambda word:word|(1<<30) if word&0xffc00000==0xb9400000 else word|(1<<31)),('sum_register',dispatch['add_offset'],lambda word:word&~(31<<16)|(31<<16))]
    for name,at,transform in mutations:
     raw=bytearray(section.content);pos=start+at;word=struct.unpack_from('<I',raw,pos)[0];changed=transform(word);c.require(changed!=word,'Negative control did not mutate its instruction');struct.pack_into('<I',raw,pos,changed)
     altered=types.SimpleNamespace(content=raw,virtual_address=section.virtual_address)
     try:ios_switch.verify_switch_tables(record,altered,relocs,code)
     except ValueError:cases.append(dict(method=mid,table=table['offset'],case=name,rejected=True))
     else:raise ValueError('Corrupt switch accepted: '+name)
 md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_LITTLE_ENDIAN)
 expected={76815:{0x20:('mov','x20, x2'),0x2c:('mov','x23, x1'),0x3c:('mov','x21, x0')},76817:{0x14:('ldr','x8, [x2, #0x10]'),0x18:('sub','w9, w1, #5'),0x2c:('csel','w9, w1, w9, hi')},101555:{0x20:('mov','x20, x3'),0x30:('mov','x25, x2'),0x3c:('mov','x23, x1'),0x40:('mov','x27, x0')}}
 with open(linked['native_file'],'rb') as f:
  for mid,checks in expected.items():
   row=rows[mid];f.seek(row['file_offset']);raw=f.read(row['size']);c.require(c.sha(raw)==row['sha256'],'Final native function changed')
   actual={i.address:(i.mnemonic,i.op_str) for i in md.disasm(raw,0)}
   c.require(all(actual.get(at)==op for at,op in checks.items()),'Receiver/MethodEnv/argument ABI differs: '+str(mid))
 c.require(len(cases)==18,'Expected three actual tables and fifteen corruptions')
 result=dict(status='actual_switch_negative_controls_and_entry_abi_passed',cases=cases,abi_instruction_checks=expected,bounded_job=job,native_sha256=linked['native_sha256'],native_executed=False)
 c.dump(args.output,result);print(json.dumps(dict(status=result['status'],switch_cases=len(cases),abi_methods=len(expected))))
if __name__=='__main__':main()
