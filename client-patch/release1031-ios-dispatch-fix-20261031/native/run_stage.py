"""Bounded compile/link/finalize/package stages for inherited dispatch repair."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
from pathlib import Path
import argparse, copy, os, struct, sys
from types import SimpleNamespace
from unittest.mock import patch
import common as c

def owned(path):
    path=Path(path).resolve()
    c.require(path.is_relative_to(c.TASK.resolve()), 'Artifact outside dispatch repair task')
    return path

def definitions_guard(port):
    """The only layout exception is the manifest's exact 25 removed traits."""
    manifest_path=Path(port['relocation_manifest'])
    if not manifest_path.is_absolute(): manifest_path=Path(port['_prepared_path']).parent/manifest_path
    manifest=c.read(manifest_path)
    helpers=manifest['helpers']
    required={101732,101820,101821,101665,101666,101667,101668,101669,101670,
              101685,101686,101687,101688,101689,101690,101691,101692,101697,
              101698,101702,101725,101729,101730,101812,101711}
    c.require({r['old_mid'] for r in helpers}==required and len(helpers)==25,
              'Exact reviewed helper migration set required')
    removed={(r['ci'],r['old_mid']) for r in helpers}
    def check(old,fresh,prepared):
        import native_support as support
        link=support.backend()
        for field in ('methods','metadata','scripts','ints','uints','doubles','strings',
                      'namespaces','ns_sets','multinames'):
            before=getattr(old,field)
            c.require(link.freeze(before)==link.freeze(getattr(fresh,field)[:len(before)]),
                      'Old declaration/pool prefix changed: '+field)
        for section in ('instances','classes'):
            c.require(link.freeze(getattr(fresh,section))==link.freeze(getattr(prepared,section)),
                      'Compiler declarations differ from prepared '+section)
            for ci,(before,after) in enumerate(zip(getattr(old,section),getattr(fresh,section))):
                c.require(link.freeze(before[:-1])==link.freeze(after[:-1]),
                          'Old class header changed: '+section)
                expected=[]
                for trait in before[-1]:
                    if section=='instances' and trait.kind==1 and (ci,trait.data[2]) in removed:
                        continue
                    expected.append(trait)
                c.require(link.freeze(after[-1])==link.freeze(expected),
                          'Undeclared old-class trait change: '+section+'/'+str(ci))
    return check

def restore_resolver_chain(link_stage, report):
    """Keep equipment/five wrappers and rebind their sole resolver call."""
    MID=18392; WRAPPER=0x10d9d9030; FIVE=0x106207aa0; TAIL=0x106207af4
    link=link_stage.original.link
    baseline=(c.PUBLIC/'worldflipper').read_bytes()
    native_path=Path(report['native_file']); actual=bytearray(native_path.read_bytes())
    c.require(c.sha(actual)==report['native_sha256'], 'Linked native drift before wrapper restoration')
    old_settings=c.read(c.PREVIOUS/'linked01/link-report.json')
    oldfn,=[f for f in old_settings['functions'] if f['method']==MID]
    newfn,=[f for f in report['functions'] if f['method']==MID]
    offset=lambda va: link.file_offset(baseline,va)
    def branch_target(word,pc):
        c.require(word&0xfc000000 in (0x14000000,0x94000000),'Expected exact B/BL')
        value=word&0x3ffffff
        return pc+(value-(1<<26) if value&(1<<25) else value)*4
    prior=branch_target(struct.unpack_from('<I',baseline,offset(TAIL))[0],TAIL)
    c.require(prior==oldfn['address'], 'Current cumulative resolver tail changed')
    c.require(not any(f':{MID}:' in r['symbol'] for r in report['relocations']),
              'Direct native cross-call would bypass retained resolver wrappers')
    active=struct.unpack_from('<Q',baseline,104549248+48)[0]
    sites=[offset(active+MID*8),0x62c0780+MID*8]
    for at in sites: actual[at:at+8]=baseline[at:at+8]
    restored=[h for h in report['hooks'] if h['method']==MID]
    c.require({h['previous'] for h in restored}=={WRAPPER,FIVE}, 'Unexpected current resolver hook sites')
    for hook in restored:
        at=hook['offset'];actual[at:at+4]=baseline[at:at+4]
    target=newfn['address']; via=target
    if not (-(1<<27)<=target-TAIL<(1<<27)):
        bridges=[v for v in report['entry_bridges'] if v['target']==target and
                 -(1<<27)<=v['address']-TAIL<(1<<27)]
        c.require(bool(bridges), 'No verified existing resolver entry veneer in BL range')
        via=bridges[0]['address']
    delta=via-TAIL;c.require(delta%4==0 and -(1<<27)<=delta<(1<<27),'Resolver BL range')
    tail=offset(TAIL);replacement=struct.pack('<I',0x94000000|((delta//4)&0x3ffffff))
    actual[tail:tail+4]=replacement
    for start,length in ((WRAPPER,52),(FIVE,84),(TAIL+4,120)):
        at=offset(start);c.require(actual[at:at+length]==baseline[at:at+length],
                                  'Resolver wrapper differs outside sole tail BL')
    report['hooks']=[h for h in report['hooks'] if h['method']!=MID]
    report['table_sites']=[at for at in report['table_sites'] if at not in sites]
    report['dispatch_resolver_wrapper']=dict(method=MID,equipment_wrapper=WRAPPER,
        five_in_one_wrapper=FIVE,tail=TAIL,tail_file_offset=tail,previous_target=prior,
        compiled_function=target,via=via,before=baseline[tail:tail+4].hex(),after=replacement.hex(),
        retained_table_sites=sites,restored_default_hooks=restored,
        equipment_and_five_postprocessing_preserved=True,native_executed=False)
    report['native_sha256']=c.sha(actual)
    native_path.write_bytes(actual)
    link_stage.save(native_path.parent/'link-report.json',report)
    return report

def restore_draw_chain(link_stage, report):
    """Keep the live wrapper/GC frame and retarget only its typed extension."""
    MID=66181;WRAPPER=0x103d69180;ISLAND=0x103d69200;CALL=ISLAND+8
    link=link_stage.original.link
    baseline=(c.PUBLIC/'worldflipper').read_bytes()
    path=Path(report['native_file']);actual=bytearray(path.read_bytes())
    c.require(c.sha(actual)==report['native_sha256'],'Native drift before draw-chain restoration')
    current=c.read(c.PREVIOUS/'linked01/link-report.json')
    beforefn,=[f for f in current['functions'] if f['method']==MID]
    fn,=[f for f in report['functions'] if f['method']==MID]
    c.require(not any(f':{MID}:' in r['symbol'] for r in report['relocations']),
              'Direct native cross-call would bypass retained draw wrapper')
    at=link.file_offset(baseline,CALL)
    adrp,add,blr=struct.unpack_from('<III',baseline,at)
    c.require(adrp&0x9f00001f==0x90000010 and add&0xffc003ff==0x91000210 and
              blr==0xd63f0200,'Current draw extension must be ADRP/ADD/BLR x16')
    immediate=((adrp>>29)&3)|(((adrp>>5)&0x7ffff)<<2)
    if immediate&(1<<20): immediate-=1<<21
    oldtarget=(CALL&~4095)+(immediate<<12)+((add>>10)&0xfff)
    c.require(oldtarget==beforefn['address'],'Current draw extension target changed')
    hooks=[h for h in report['hooks'] if h['method']==MID]
    c.require(bool(hooks) and {h['previous'] for h in hooks}=={WRAPPER},
              'Unexpected current draw entry hook')
    for row in hooks:
        off=row['offset'];actual[off:off+4]=baseline[off:off+4]
    active=struct.unpack_from('<Q',baseline,104549248+48)[0]
    sites=[link.file_offset(baseline,active+MID*8),0x62c0780+MID*8]
    for off in sites:actual[off:off+8]=baseline[off:off+8]
    target=fn['address'];delta=(target>>12)-(CALL>>12)
    c.require(-(1<<20)<=delta<(1<<20),'New draw ADRP range')
    immediate=delta&0x1fffff
    replacement=struct.pack('<II',0x90000010|((immediate&3)<<29)|((immediate>>2)<<5),
                            0x91000210|((target&4095)<<10))
    actual[at:at+8]=replacement
    start=link.file_offset(baseline,WRAPPER);end=link.file_offset(baseline,0x103d694c4)
    proof=bytearray(actual[start:end]);proof[at-start:at-start+8]=baseline[at:at+8]
    c.require(proof==baseline[start:end],'Draw wrapper changed outside typed extension address')
    report['hooks']=[h for h in report['hooks'] if h['method']!=MID]
    report['table_sites']=[off for off in report['table_sites'] if off not in sites]
    report['dispatch_draw_wrapper']=dict(method=MID,wrapper=WRAPPER,bridge=ISLAND,
        call_address=CALL,call_file_offset=at,previous_target=oldtarget,compiled_function=target,
        before=baseline[at:at+8].hex(),after=replacement.hex(),retained_table_sites=sites,
        restored_default_hooks=hooks,live_frame_gc_cleanup_and_stock_draw_preserved=True,
        inherited_wrapper_cfi_limitation=True,native_executed=False)
    report['native_sha256']=c.sha(actual);path.write_bytes(actual)
    link_stage.save(path.parent/'link-report.json',report)
    return report

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('stage',choices=['baseline','compile','link','finalize','package'])
    ap.add_argument('--prepared',type=Path);ap.add_argument('--compiled',type=Path)
    ap.add_argument('--linked',type=Path);ap.add_argument('--output',type=Path)
    args=ap.parse_args();c.bounded_job()
    previous_env=os.environ.get('PYTHONDONTWRITEBYTECODE');os.environ['PYTHONDONTWRITEBYTECODE']='1'
    try:
        if args.stage=='baseline':
            paths=c.baseline_reports();print('Pinned public baseline metadata:',paths[0]);return
        c.require(args.output is not None,'Output required');output=owned(args.output)
        c.framework();import compile_port,link_stage
        signing=c.module('dispatch_bounded_signing',fc.tool('repairs/scripts/signing_models.py'));signing.c=c
        # grouped_link imports this module by its stable name.
        sys.modules['signing_models']=signing
        if args.stage in ('compile','link'):
            c.require(args.prepared is not None,'Prepared port required')
            prepared=owned(args.prepared);port=c.read(prepared)
            c.require(port['old_methods']==101843 and port['base_full_abc_sha256']==c.ABC_SHA,
                      'Wrong cumulative public source')
            c.require({18392,66181}<={r['method_id'] for r in port['methods']},
                      'Both wrapper extension methods require explicit recompilation')
            c.fresh(output)
        if args.stage=='compile':
            result=compile_port.run(prepared,output,sdk=c.SDK,dependencies=c.DEPENDENCIES,
                                   background=c.BACKGROUND,timeout=165)
        elif args.stage=='link':
            c.require(args.compiled is not None,'Compile report required')
            baseline_link,baseline_package=c.baseline_reports()
            options=SimpleNamespace(prepared=prepared,compiled=owned(args.compiled),output=output,
                previous_link=baseline_link,previous_package=baseline_package,
                runtime_stubs=c.STUBS,dependencies=c.DEPENDENCIES)
            adapter=c.module('dispatch_grouped_link',fc.tool('repairs/scripts/run_native_stage.py'));adapter.c=c
            guard=definitions_guard(dict(port,_prepared_path=str(prepared)))
            with patch.object(link_stage.original,'check_definitions',guard):
                result=adapter.grouped_link(link_stage,options)
            result=restore_resolver_chain(link_stage,result)
            result=restore_draw_chain(link_stage,result)
        elif args.stage=='finalize':
            current=c.read(output/'link-report.json')
            c.require(current['status']=='linked_pending_unwind_finalization', 'Not awaiting finalization')
            sys.path.insert(0,str(fc.tool('settings/recipe')))
            finalizer=c.module('dispatch_strict_finalizer',fc.tool('settings/recipe/finalize_final.py'))
            from unwind_repack import wrap_augment
            with (patch.object(finalizer.finalize_delta,'verify_switch_tables',finalizer.strict_switch),
                  patch.object(finalizer.finalize_delta,'_augment_model',
                               wrap_augment(finalizer.finalize_delta._augment_model)),
                  patch.object(link_stage.support,'verify_signing_models',signing.verify_signing_models)):
                result=link_stage.finalize(SimpleNamespace(output=output))
        else:
            c.require(args.linked is not None,'Finalized link report required');c.fresh(output)
            package=c.module('dispatch_packager',c.SOURCE/'ios-r11-port/package_stage.py')
            with patch.object(sys,'argv',[str(Path(package.__file__)),'--linked',str(owned(args.linked)),
                                         '--output',str(output)]): package.main()
            result=c.read(output.with_suffix('.json'),128*1024)
        print(args.stage,result['status'])
    finally:
        if previous_env is None:os.environ.pop('PYTHONDONTWRITEBYTECODE',None)
        else:os.environ['PYTHONDONTWRITEBYTECODE']=previous_env

if __name__=='__main__':main()
