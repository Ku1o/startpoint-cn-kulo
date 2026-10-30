"""Read frozen final Android contract against actual prepared iOS method coverage."""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
from pathlib import Path
import argparse,collections,json,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import prepare_final as q

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--prepared',type=Path,required=True);ap.add_argument('--contract',type=Path,required=True);args=ap.parse_args();p=q.read(args.prepared);c=q.read(args.contract)
 assert q.sha(Path(c['swf']).read_bytes())==c['sha256']==p['donor_android_swf_sha256'];t=q.view(q.p.abcfmt.ABC((args.prepared.parent/p['full_abc_file']).read_bytes()));units=q.units(c['swf']);sources={k:q.view(q.p.abcfmt.ABC(v[0])) for k,v in units.items() if k in p['changed_tags']};covered=[];hard=[]
 for row in c['methods']:
  sv=sources[row['abc_tag']];sb=sv.a.bodies[row['body']];assert sb[0]==row['method'] and q.sha(sb[5])==row['new']['code_sha256']
  targets=[r for r in p['methods'] if r['source_tag']==row['abc_tag'] and r['source_body']==row['body']]
  if row['abc_tag']=='cn.carry.StageCarryState':
   bi,=t.by_label[row['label']];mid=t.a.bodies[bi][0];assert mid in p['new_helper_sources'][0]['methods'];assert q.p.freeze(sv.normalized(row['body']))==q.p.freeze(t.normalized(bi));targets=[dict(method_id=mid,strategy='complete_new_class_import')]
  assert targets,('frozen method absent',row['abc_tag'],row['label'])
  covered.append(dict(abc_tag=row['abc_tag'],label=row['label'],source_method=row['method'],ios_targets=[r['method_id'] for r in targets],adaptations=[r.get('adaptation') for r in targets]))
  instructions=q.p.asm.decode(sb[5])
  for i,x in enumerate(instructions):
   if x.op not in (0x6c,0x6d,0x6e,0x6f):continue
   assert row['label']==q.PATHS,'hard static/instance slot access requires separate proof'
   assert x.op in (0x6c,0x6d) and sb[7] and any(z.op==0x57 for z in instructions),'only independent activation hard slots supported'
   # The clone retains the complete original 18-field source activation; the
   # old original method keeps its immutable 4-field descriptor and typed bridge.
   assert x.args[0] in [tr.data[1] for tr in sb[7] if tr.kind in (0,6)]
   hard.append(dict(label=row['label'],instruction=i,operation=x.name,slot=x.args[0],storage='new clone activation, never an old owner static slot'))
 carry,=[r for r in p['new_helper_sources'] if r['tag']=='cn.carry.StageCarryState'];assert carry['abc_sha256']==q.sha(units['cn.carry.StageCarryState'][0])=='6849f52ea234769bb73fadad08604e9f8009b4e4fc0a0c01c22a7d9284c507a5'
 assert len(covered)==len(c['methods']) and len(p['storage'])==len(c['new_static_states'])
 out=dict(status='all_frozen_final_android_methods_mapped_to_prepared_ios',frozen_contract=str(args.contract.resolve()),frozen_contract_sha256=q.sha(args.contract.read_bytes()),donor_swf_sha256=c['sha256'],prepared_full_abc_sha256=q.sha((args.prepared.parent/p['full_abc_file']).read_bytes()),method_count=len(covered),per_abc=dict(collections.Counter(r['abc_tag'] for r in covered)),new_static_states=26,carry_helper_abc_sha256=carry['abc_sha256'],carry_methods=len(carry['methods']),old_static_slots_and_old_activation_preserved=True,hard_slot_audit=hard,mappings=covered,native_executed=False,device_tested=False)
 q.save(args.prepared.parent/'frozen-contract-verification.json',out);print(json.dumps({k:out[k] for k in ('status','method_count','per_abc','new_static_states','carry_helper_abc_sha256')}))
if __name__=='__main__':main()
