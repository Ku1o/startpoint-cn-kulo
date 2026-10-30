"""Bind withdrawal to actual new IPA: both original shop bodies, signatures and native functions."""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
from pathlib import Path
import argparse,bisect,json,sys,zipfile
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE/'recipe'),cfg.path('libraries'),cfg.repo('client-patch/ios-r11-port')]
import prepare_final as p,verify_stages as v

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--package-report',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();package=v.read(args.package_report);link=v.read(package['link_report']);prepared=v.read(link['source_prepare_report']);registry=p.read(cfg.path('r11_baseline_record'))['artifact'];assert registry['ipa_sha256']=='339e19ca373284ed778dd3fcda5ee2aa2e93915f550add733629de5bd989c33b'
 old_full=Path(registry['full_abc']).read_bytes();assert v.sha(old_full)==registry['full_abc_sha256'];old=p.view(p.p.abcfmt.ABC(old_full));new_full=(Path(link['source_prepare_report']).parent/prepared['full_abc_file']).read_bytes();new=p.view(p.p.abcfmt.ABC(new_full));assert v.sha(new_full)==package['full_abc_sha256'];assert v.sha(Path(package['ipa']).read_bytes())==package['ipa_sha256']
 with zipfile.ZipFile(package['ipa']) as z:actual=z.read(registry['native_member']);swf=z.read(registry['swf_member'])
 assert v.sha(actual)==package['native_sha256']==link['native_sha256'];assert v.sha(swf)==package['swf_sha256'];im=v.Image(actual);base_path=Path(cfg.path('outputs_ios_r11_cumulative_compact_20261025_linked_worldflipper'));baseline=v.Image(base_path.read_bytes());assert v.sha(baseline.raw)==registry['native_sha256'];old_active=v.u64(baseline.raw,p.INFO_OFFSET+48);active=v.u64(actual,p.INFO_OFFSET+48);starts=sorted(v.function_starts(baseline));rows=[]
 labels=['pinball.scene.eventItemExchange.shop::EventItemExchangeShopScene/buttonClicked|1','pinball.scene.shop.dialog::ShopProductBuyDialog/beforePrepare|1']
 for label in labels:
  oi,=old.by_label[label];ni,=new.by_label[label];ob=old.a.bodies[oi];nb=new.a.bodies[ni];mid=ob[0];assert nb[0]==mid and p.p.freeze(ob)==p.p.freeze(nb) and p.p.freeze(old.a.methods[mid])==p.p.freeze(new.a.methods[mid]) and p.signature(old,mid)==p.signature(new,mid)
  entry=v.u64(im.read(active+mid*8,8));old_entry=v.u64(baseline.read(old_active+mid*8,8));assert entry==old_entry;assert im.raw[v.LEGACY+mid*8:v.LEGACY+mid*8+8]==baseline.raw[v.LEGACY+mid*8:v.LEGACY+mid*8+8]
  at=bisect.bisect_right(starts,entry-v.BASE)-1;start=v.BASE+starts[at];end=v.BASE+starts[at+1];native_before=baseline.read(start,end-start);native_after=im.read(start,end-start);assert native_before==native_after and im.read(entry,16)==baseline.read(entry,16)
  cls=label.split('/')[0];ci,=[i for i,r in enumerate(old.a.instances) if old.a.mn_name(r[0])==cls];assert p.p.freeze(old.a.instances[ci])==p.p.freeze(new.a.instances[ci]) and p.p.freeze(old.a.classes[ci])==p.p.freeze(new.a.classes[ci]);assert not any(r['method']==mid for r in link['functions']+link['hooks'])
  rows.append(dict(qname=label,actual_method_info=mid,full_body_and_headers_activation_exact=True,method_info_and_signature_exact=True,owner_instance_and_class_traits_exact=True,active_entry=hex(entry),active_and_legacy_entries_exact=True,entry16_sha256=v.sha(im.read(entry,16)),complete_native_function_start=hex(start),complete_native_function_bytes=end-start,complete_native_function_sha256=v.sha(native_after),complete_native_function_byte_exact=True,not_recompiled_or_hooked=True))
 helper='cnDegreeShopId';assert not any(helper in label for label in new.by_label);assert not any(helper in str(r) for r in link['functions']+link['relocations']);assert helper.encode() not in new_full and helper.encode() not in actual
 compiled=v.read(link['compiled_report']);objects=[]
 for row in compiled['objects']:
  obj=v.Object(Path(compiled['directory'])/row['name'],row['sha256']);assert not any(helper in s['name'] for s in obj.symbols);objects.append(dict(path=str(obj.path),sha256=row['sha256'],withdrawn_helper_symbols=0))
 report=dict(status='actual_ipa_degree_client_retraction_exact_formal_r11_verified',ipa=package['ipa'],ipa_sha256=package['ipa_sha256'],native_sha256=package['native_sha256'],full_abc_sha256=package['full_abc_sha256'],baseline_ipa_sha256=registry['ipa_sha256'],methods=rows,withdrawn_helper_no_definition=True,withdrawn_helper_no_object_or_linked_aot_symbol=True,withdrawn_helper_no_full_abc_or_native_ascii_residue=True,compiled_object_checks=objects,server_degree_grant_not_changed_by_this_check=True,native_executed=False)
 v.dump(args.output,report);print(json.dumps({k:report[k] for k in ('status','ipa_sha256','native_sha256','withdrawn_helper_no_object_or_linked_aot_symbol')}))
if __name__=='__main__':main()
