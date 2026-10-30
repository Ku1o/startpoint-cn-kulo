"""Prepare one frozen settings revision from formal R11; verify initializer/storage/retraction."""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
from pathlib import Path
import argparse,json,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'recipe'))
import prepare_final as p
from type_helpers import owning_script,KIND

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--frozen-contract',type=Path,required=True);ap.add_argument('--contract-sha256',required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();out=args.output.resolve();assert out.is_relative_to(cfg.work('settings')) and not out.exists();assert p.sha(args.frozen_contract.read_bytes())==args.contract_sha256;c=p.read(args.frozen_contract)
 adapter=out.parent/(out.name+'-input-contract.json');assert not adapter.exists();p.save(adapter,dict(android_base_swf=c['baseline'],android_base_sha256=c['baseline_sha256'],donor_swf=c['swf'],donor_sha256=c['sha256'],allowed_modified_abc_tags=sorted({r['abc_tag'] for r in c['methods']}),frozen_final_contract=str(args.frozen_contract.resolve()),frozen_final_contract_sha256=args.contract_sha256))
 sys.argv=[str(HERE/'recipe/prepare_final.py'),'--contract',str(adapter),'--output',str(out),'--draw-gated-extension'];p.main()
 report=p.read(out/'port.json');a=p.view(p.p.abcfmt.ABC((out/'full.abc').read_bytes()));ci,mid,bi=owning_script(a,KIND);assert mid==54758 and any(r['method_id']==mid for r in report['methods']),'real owning script initializer absent from AOT targets';assert any(x.op==0x58 and x.args==[ci] for x in p.p.asm.decode(a.a.bodies[bi][5]))
 forbidden={r['method'] for r in p.read(Path(cfg.path('native_storage_contract')))['methods']};assert not forbidden.intersection(r['method_id'] for r in report['methods']),'original storage native method must not be recompiled'
 assert not any('cnDegreeShopId' in label for label in a.by_label),'withdrawn degree helper remains'
 degree_labels=['pinball.scene.eventItemExchange.shop::EventItemExchangeShopScene/buttonClicked|1','pinball.scene.shop.dialog::ShopProductBuyDialog/beforePrepare|1'];assert not any(r['label'] in degree_labels for r in report['methods']),'withdrawn degree originals are still target methods'
 p.save(out/'revision-guards.json',dict(status='formal_r11_full_prepare_revision_guards_passed',frozen_contract=str(args.frozen_contract.resolve()),frozen_contract_sha256=args.contract_sha256,donor_sha256=c['sha256'],owning_kind_script_method=mid,owning_kind_class=ci,script_initializer_in_aot_targets=True,original_storage_native_ids_not_targets=sorted(forbidden),withdrawn_degree_helper_absent=True,withdrawn_degree_originals_not_targets=degree_labels,new_slots_on_old_classes=0,native_linked=False,ui_runtime_validation_pending=True))
 print(json.dumps(dict(status='revision_guards_passed',total_methods=report['total_methods'],aot_targets=len(set(r['method_id'] for r in report['methods'])|set(report['new_method_ids'])))))
if __name__=='__main__':main()
