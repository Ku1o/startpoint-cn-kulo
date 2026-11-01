"""Independent bounded readback of the final C8601 IPA and cumulative native chain."""
import argparse,json,sys,types
from pathlib import Path
sys.dont_write_bytecode=True
import ios_repair as c


def main():
 ap=argparse.ArgumentParser();ap.add_argument('--inputs',type=Path,required=True);ap.add_argument('--package-report',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
 job=c.configure(args);c.framework();c.fresh(args.output)
 sys.path.insert(0,str(c.SOURCE/'release1031-ios-dispatch-fix-20261031/verify'))
 review=c.module('c8601_cumulative_verifier',c.SOURCE/'release1031-ios-independent-party-fix-20261031/verify_final.py')
 package=c.read(args.package_report);linked=c.read(package['link_report']);source=linked['source_ipa']
 baseline=c.read(c.INPUTS['baseline_record'])['artifact']
 c.require(source['ipa_sha256']==baseline['ipa_sha256']=='1990178abd4078beb39e26e5c2f985b6cc1af4900c72868f5b79221fcc21e907','Wrong input IPA')
 flat=args.output.with_name(args.output.stem+'-baseline.json');c.dump(flat,baseline)
 c.TARGETS={76815,76817,101555};c.METHODS=101873;c.ABC_SHA=package['full_abc_sha256']
 models=linked['signing_models']
 c.require(len(models)==6 and {(r['mode'],r['signature_size']) for r in models}=={(mode,size) for mode in ('signature','ldid') for size in (0x80000,0x200000,0x400000)} and all(r['loader_metadata_preserved'] and r['all_loader_range_bytes_compared'] and r['rebase_entries_equal'] for r in models),'Signing layout models missing')
 def readback(p,l,previous):return review.packages.readback(p,l,previous,flat,review.stage.Image)
 review.stage.package_readback=readback;review.stage.dump=c.dump
 preserve=review.preserve
 def resolved_preserve(old,new,previous,prepared,current):
  resolved=dict(prepared,full_abc_file=current['full_abc_file'])
  return preserve(old,new,previous,resolved,current)
 review.preserve=resolved_preserve
 # Equipment's historical chunks remain protected, except the independently
 # decoded original-entry branches/bridges of this exact three-method delta.
 def equipment(old,new,report,read):
  plan=read(report['plan_file'])
  allowed=[(r['offset'],r['offset']+4) for r in linked['hooks']]+[(r['file_offset'],r['file_offset']+16) for r in linked['entry_bridges']]
  count=0
  for row in plan['chunks']+plan['preserved_native_ranges']:
   start=old.offset(row['va'],row['bytes']);before=old.read(row['va'],row['bytes']);after=bytearray(new.read(row['va'],row['bytes']))
   for lo,hi in allowed:
    lo,hi=max(start,lo),min(start+len(after),hi)
    if lo<hi:after[lo-start:hi-start]=before[lo-start:hi-start]
   c.require(after==before,'Prior equipment native range changed');count+=1
  for row in plan['patches']:
   at=row['file_offset'];n=len(bytes.fromhex(row['after']))
   c.require(old.raw[at:at+n]==new.raw[at:at+n],'Prior equipment patch changed')
  review.PROOF['equipment_ranges_preserved']=count
  return plan
 review.equipment=equipment
 previous=c.read(linked['previous_link_report']);equipment_path=Path(linked['previous_link_report'])
 while 'plan_file' not in previous:
  equipment_path=Path(previous['previous_link_report']);previous=c.read(equipment_path)
 verifier,hits=review.adapt()
 result=verifier(types.SimpleNamespace(package_report=args.package_report,equipment_link=equipment_path,libraries=Path(c.INPUTS['ios']['libraries']['path']),output=args.output,detail_output=args.output.with_name(args.output.stem+'-details.json')))
 proof=dict(result=result,proof=review.PROOF,adapter_shapes=hits,bounded_job=job,verifier_sha256=c.sha(Path(__file__).read_bytes()),validation_boundary='Actual unsigned IPA static readback; iOS native/device execution untested')
 c.dump(args.output.with_name(args.output.stem+'-proof.json'),proof)
 print(json.dumps(dict(status=result['status'],compiled_functions=result['compiled_functions'],relocations=result['relocations_checked'],preserved_functions=len(review.PROOF['preserved_native']['previous_functions']),changed_members=result['package']['changed_members'])))
if __name__=='__main__':main()
