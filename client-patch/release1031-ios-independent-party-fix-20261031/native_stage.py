"""Compile and bind real owner methods while preserving the cumulative carrier."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
import argparse, os, sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import common as c

def owned(path):
    path=Path(path).resolve();c.require(path.is_relative_to(c.TASK.resolve()),'Artifact outside party repair task');return path
def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['compile','link','finalize','package'])
    ap.add_argument('--prepared',type=Path);ap.add_argument('--compiled',type=Path)
    ap.add_argument('--linked',type=Path);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();c.bounded_job();output=owned(args.output)
    previous_env=os.environ.get('PYTHONDONTWRITEBYTECODE');os.environ['PYTHONDONTWRITEBYTECODE']='1'
    try:
        c.framework();import compile_port,link_stage,native_support
        signing=c.module('party_signing',fc.tool('repairs/scripts/signing_models.py'));signing.c=c
        sys.modules['signing_models']=signing
        if args.stage in ('compile','link'):
            prepared=owned(args.prepared);port=c.read(prepared)
            c.require(port['old_methods']==port['total_methods']==c.METHODS and
                      port['full_abc_sha256']==port['base_full_abc_sha256']==c.ABC_SHA,'Wrong cumulative input')
            c.require(native_support.wanted_methods(port)==set(c.TARGETS),'Only the three real owners may compile/link')
            c.fresh(output)
        if args.stage=='compile':
            report=compile_port.run(prepared,output,sdk=c.SDK,dependencies=c.DEPENDENCIES,background=c.BACKGROUND,timeout=165)
        elif args.stage=='link':
            options=SimpleNamespace(prepared=prepared,compiled=owned(args.compiled),output=output,
                previous_link=c.PREVIOUS/'linked01/link-report.json',
                previous_package=c.PREVIOUS/'StarPoint-iOS-1.8.4-release1031-battle-f1069-fix-r1-unsigned.json',
                runtime_stubs=c.STUBS,dependencies=c.DEPENDENCIES)
            adapter=c.module('party_grouped_link',fc.tool('repairs/scripts/run_native_stage.py'));adapter.c=c
            report=adapter.grouped_link(link_stage,options)
            c.require({r['method'] for r in report['hooks']}==set(c.TARGETS),'Missing or extra original entry binding')
            c.require(len(report['table_sites'])==6,'Both native method tables must bind all three targets')
        elif args.stage=='finalize':
            c.require(c.read(output/'link-report.json')['status']=='linked_pending_unwind_finalization','No pending native finalization')
            sys.path.insert(0,str(fc.tool('settings/recipe')))
            finalizer=c.module('party_strict_finalizer',fc.tool('settings/recipe/finalize_final.py'))
            unwind=c.module('party_unwind_repack',c.SOURCE/'release1031-ios-battle-f1069-fix-20261031/native/unwind_repack.py');unwind.c=c
            with (patch.object(finalizer.finalize_delta,'verify_switch_tables',finalizer.strict_switch),
                  patch.object(finalizer.finalize_delta,'_augment_model',unwind.wrap_augment(finalizer.finalize_delta._augment_model)),
                  patch.object(link_stage.support,'verify_signing_models',signing.verify_signing_models)):
                report=link_stage.finalize(SimpleNamespace(output=output))
        else:
            c.fresh(output);c.fresh(output.with_suffix('.json'))
            package=c.module('party_existing_packager',c.SOURCE/'ios-r11-port/package_stage.py')
            with patch.object(sys,'argv',[str(Path(package.__file__)),'--linked',str(owned(args.linked)),'--output',str(output)]):package.main()
            report=c.read(output.with_suffix('.json'),128*1024)
        print(args.stage,report['status'])
    finally:
        if previous_env is None:os.environ.pop('PYTHONDONTWRITEBYTECODE',None)
        else:os.environ['PYTHONDONTWRITEBYTECODE']=previous_env
if __name__=='__main__':main()
