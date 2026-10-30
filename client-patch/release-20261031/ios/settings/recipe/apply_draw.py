"""Apply only the independently reviewed live-frame draw bridge to actual linked output."""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
cfg.bind_tools()
from pathlib import Path
import argparse,json,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path[:0]=[cfg.path('libraries'),cfg.local('support/recipe-deps/pr43-ios')]
from native_support import backend
import platform_draw as d
import platform_equipment as e

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--linked',type=Path,required=True);args=ap.parse_args();out=args.linked.resolve();assert out.is_relative_to(cfg.work('settings'))
 report_path=out/'link-report.json';report=json.loads(report_path.read_text(encoding='utf-8'));assert report['status']=='linked_pending_unwind_finalization' and not report.get('platform_draw')
 baseline=Path(cfg.path('outputs_ios_r11_cumulative_compact_20261025_linked_worldflipper')).read_bytes();path=Path(report['native_file']);raw=path.read_bytes();assert d.sha(raw)==report['native_sha256']
 reviewed=Path(cfg.path('client_ios_draw_review_bridge88_v2_mechanism_review_json'));review=json.loads(reviewed.read_text(encoding='utf-8'));assert reviewed.is_file()
 raw=e.apply(baseline,raw,report,backend().file_offset)
 result=d.apply(baseline,raw,report,backend().file_offset);report['platform_draw'].update(adapter_source_sha256=d.sha(Path(d.__file__).read_bytes()),independent_mechanism_review=str(reviewed),review_sha256=d.sha(reviewed.read_bytes()),nullable_air_result=cfg.path('client_ios_final_capabilities_draw_air03_result_json'),inherited_limit='Baseline wrapper compact-unwind FRAME encoding does not describe all custom-wrapper saved-register locations; unchanged inherited limitation. New BLR return PC equals old BL return PC; compiled extension has its own verified compiler unwind. Native/device execution untested.')
 proof=d.verify(baseline,result,report,backend().file_offset);report['native_sha256']=d.sha(result);path.write_bytes(result);report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');(out/'draw-actual-verification.json').write_text(json.dumps(dict(proof,native_sha256=d.sha(result),platform_draw=report['platform_draw']),indent=2),encoding='utf-8');print(json.dumps(proof))
if __name__=='__main__':main()
