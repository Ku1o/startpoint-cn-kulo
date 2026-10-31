"""Bounded native stages for one new getter; no old function replacement."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
from pathlib import Path
import argparse,os,sys
from types import SimpleNamespace
from unittest.mock import patch
import common as c

def owned(path):
    path=Path(path).resolve()
    c.require(path.is_relative_to(c.TASK.resolve()),'Artifact outside new battle repair task')
    return path

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('stage',choices=['compile','link','finalize','package'])
    ap.add_argument('--prepared',type=Path);ap.add_argument('--compiled',type=Path)
    ap.add_argument('--linked',type=Path);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();c.bounded_job();output=owned(args.output)
    previous=os.environ.get('PYTHONDONTWRITEBYTECODE');os.environ['PYTHONDONTWRITEBYTECODE']='1'
    try:
        c.framework();import compile_port,link_stage
        signing=c.module('battle_bounded_signing',fc.tool('repairs/scripts/signing_models.py'));signing.c=c
        sys.modules['signing_models']=signing
        if args.stage in ('compile','link'):
            c.require(args.prepared is not None,'Prepared port required')
            prepared=owned(args.prepared);port=c.read(prepared)
            c.require(port['old_methods']==c.METHODS and port['total_methods']==c.METHODS+1
                and port['base_full_abc_sha256']==c.ABC_SHA,'Wrong cumulative getter-only input')
            import native_support
            c.require(native_support.wanted_methods(port)=={c.NEW_METHOD},'Only the new getter may compile/link')
            c.fresh(output)
        if args.stage=='compile':
            report=compile_port.run(prepared,output,sdk=c.SDK,dependencies=c.DEPENDENCIES,
                                   background=c.BACKGROUND,timeout=165)
        elif args.stage=='link':
            c.require(args.compiled is not None,'Compile report required')
            options=SimpleNamespace(prepared=prepared,compiled=owned(args.compiled),output=output,
                previous_link=c.PREVIOUS/'linked01/link-report.json',
                previous_package=c.PREVIOUS/'StarPoint-iOS-1.8.4-release1031-dispatch-fix-r1-unsigned.json',
                runtime_stubs=c.STUBS,dependencies=c.DEPENDENCIES)
            adapter=c.module('battle_grouped_link',fc.tool('repairs/scripts/run_native_stage.py'));adapter.c=c
            report=adapter.grouped_link(link_stage,options)
            c.require(not report['hooks'] and not report['table_sites'],
                      'Getter-only link changed an existing native function/table entry')
        elif args.stage=='finalize':
            c.require(c.read(output/'link-report.json')['status']=='linked_pending_unwind_finalization',
                      'Native does not await unwind finalization')
            sys.path.insert(0,str(fc.tool('settings/recipe')))
            finalizer=c.module('battle_strict_finalizer',fc.tool('settings/recipe/finalize_final.py'))
            from unwind_repack import wrap_augment
            with (patch.object(finalizer.finalize_delta,'verify_switch_tables',finalizer.strict_switch),
                  patch.object(finalizer.finalize_delta,'_augment_model',
                               wrap_augment(finalizer.finalize_delta._augment_model)),
                  patch.object(link_stage.support,'verify_signing_models',signing.verify_signing_models)):
                report=link_stage.finalize(SimpleNamespace(output=output))
        else:
            c.require(args.linked is not None,'Finalized link report required');c.fresh(output)
            package=c.module('battle_packager',c.SOURCE/'ios-r11-port/package_stage.py')
            with patch.object(sys,'argv',[str(Path(package.__file__)),'--linked',str(owned(args.linked)),
                                         '--output',str(output)]):package.main()
            report=c.read(output.with_suffix('.json'),128*1024)
        print(args.stage,report['status'])
    finally:
        if previous is None:os.environ.pop('PYTHONDONTWRITEBYTECODE',None)
        else:os.environ['PYTHONDONTWRITEBYTECODE']=previous

if __name__=='__main__':main()
