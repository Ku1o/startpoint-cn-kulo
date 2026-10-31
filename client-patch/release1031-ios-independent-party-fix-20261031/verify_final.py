"""Read the final IPA independently and check the three original native entries."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
import argparse, ast, inspect, json, plistlib, struct, sys, zipfile
from pathlib import Path
from types import SimpleNamespace
import common as c
sys.path[:0] = [str(c.SOURCE/'release1031-ios-dispatch-fix-20261031/verify'),
    str(fc.private('libraries')),str(c.SOURCE/'ios-r11-port'),str(c.SOURCE/'pr43-ios'),str(c.SOURCE/'lens0907-0908')]
import package_contract as packages
import native_contract as native
import verify_stages as stage

PROOF={}
NATIVE=packages.MEMBER_NATIVE
SWF=packages.MEMBER_SWF

def readback(package,linked,previous):
    baseline=c.TASK/'jobs/identity01.log'
    receipt=c.read(baseline);source=linked['source_ipa']
    c.require(receipt['ipa_sha256']==source['ipa_sha256']==previous['ipa_sha256']==c.IPA_SHA,'Cumulative IPA input mismatch')
    c.require(Path(receipt['ipa']).resolve()==Path(source['ipa']).resolve(),'Input receipt path mismatch')
    c.require(packages.file_sha(package['ipa'])==package['ipa_sha256'],'Final IPA streamed digest mismatch')
    changed=[]
    with zipfile.ZipFile(source['ipa']) as old,zipfile.ZipFile(package['ipa']) as new:
        c.require(old.namelist()==new.namelist() and len(set(new.namelist()))==len(new.namelist()),'ZIP names/order/duplicates changed')
        c.require(old.comment==new.comment,'ZIP archive comment changed')
        for a,b in zip(old.infolist(),new.infolist()):
            c.require(all(getattr(a,k)==getattr(b,k) for k in ('filename','date_time','compress_type','comment','extra',
                'create_system','create_version','extract_version','flag_bits','internal_attr','external_attr')),'ZIP metadata changed: '+a.filename)
            same,ah,bh=packages.same_compressed(old,a,new,b)
            if not same:
                changed.append(a.filename);c.require(a.filename==NATIVE,'Non-native compressed member changed: '+a.filename)
            else:
                c.require((a.CRC,a.file_size,a.compress_size)==(b.CRC,b.file_size,b.compress_size) and ah==bh,
                    'Unchanged ZIP member header/CRC changed: '+a.filename)
        c.require(changed==[NATIVE],'Expected exactly one native replacement')
        for z in (old,new):
            c.require(z.getinfo(NATIVE).file_size<=packages.MAX_NATIVE and z.getinfo(SWF).file_size<=packages.MAX_SWF,'Payload size bound')
        before,after=old.read(NATIVE),new.read(NATIVE);bs,ns=old.read(SWF),new.read(SWF)
        identity=plistlib.loads(new.read('Payload/worldflipper.app/Info.plist'))
        c.require(tuple(identity[k] for k in ('CFBundleIdentifier','CFBundleShortVersionString','CFBundleVersion'))==
            ('com.kulo.wf','1.8.4','1.8.46'),'Bundle identity differs')
        member_count=len(new.infolist())
    c.require(c.sha(before)==source['native_sha256']==receipt['native_sha256']==c.NATIVE_SHA,'Actual input native mismatch')
    c.require(c.sha(after)==package['native_sha256']==linked['native_sha256'],'Final native identity mismatch')
    c.require(bs==ns and c.sha(ns)==source['swf_sha256']==receipt['swf_sha256']==package['swf_sha256']==linked['swf_sha256'],'SWF changed')
    packages.equal_file(after,linked['native_file']);packages.equal_file(ns,linked['swf_file'])
    return stage.Image(before),stage.Image(after),bs,ns,dict(changed_members=changed,
        unchanged_compressed_members_exact=member_count-1,unchanged_local_headers_exact=True,swf_exact=True,
        final_ipa_digest_streamed=True,baseline_identity_receipt=str(baseline),payload_crc_verified=True)

def preserve(old,new,previous,prepared,linked):
    c.require(c.sha(Path(prepared['full_abc_file']).read_bytes())==c.ABC_SHA,'Full ABC changed')
    c.require(prepared['old_methods']==prepared['total_methods']==c.METHODS,'Method count changed')
    c.require({int(r['method_id']) for r in prepared['methods']}==set(c.TARGETS),'Repair target scope differs')
    functions=[];seen=set();report=previous
    while True:
        if 'functions' not in report:
            c.require('plan_file' in report and 'chunks' in report,'Unknown cumulative link report shape')
            break
        for row in report['functions']:
            key=(int(row['method']),int(row['address']))
            if key in seen:continue
            seen.add(key)
            if int(row['method']) in c.TARGETS:continue
            c.require(old.read(row['address'],row['size'])==new.read(row['address'],row['size']),
                'Previously compiled native changed: '+str(key))
            functions.append(dict(method=row['method'],address=row['address'],size=row['size']))
        path=report.get('previous_link_report')
        if not path:break
        report=c.read(path)
    active=stage.u64(old.raw,stage.INFO+48);helpers=[]
    for mid in (101300,101301,101302,101872,18392,66181):
        at=old.offset(active+mid*8)
        c.require(old.raw[at:at+8]==new.raw[at:at+8],'Cumulative helper/wrapper active table changed')
        if mid<stage.LEGACY_COUNT:
            at=stage.LEGACY+mid*8;c.require(old.raw[at:at+8]==new.raw[at:at+8],'Wrapper legacy table changed')
        helpers.append(dict(method=mid,address=stage.u64(new.read(active+mid*8,8))))
    PROOF['preserved_native']=dict(previous_functions=functions,helper_and_wrapper_entries=helpers)
    PROOF['unwind_pages']=native.unwind_page_bounds(new)
    from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM
    disasm=Cs(CS_ARCH_ARM64,CS_MODE_ARM);entries=[]
    for row in linked['functions']:
        raw=new.read(row['address'],row['size']);mid=int(row['method'])
        calls=[r for r in linked['relocations'] if r['method']==mid and r['type']==2]
        c.require(row['size']>32 and not any('_llVerifyError' in r['symbol'] for r in calls),'Verifier-error carrier or trivial stub linked')
        ops=[dict(offset=hex(i.address-row['address']),op=i.mnemonic,args=i.op_str) for i in disasm.disasm(raw,row['address'])]
        c.require(any(x['op']=='ret' for x in ops),'Native entry lacks return')
        entries.append(dict(method=mid,bytes=len(raw),instructions=ops,branch_relocations=calls))
    PROOF['actual_native_entries']=entries

def equipment(old,new,report,read):
    plan=read(report['plan_file'])
    for r in plan['chunks']+plan['preserved_native_ranges']:
        c.require(old.read(r['va'],r['bytes'])==new.read(r['va'],r['bytes']),'Cumulative equipment code changed')
    for r in plan['patches']:
        at=r['file_offset'];n=len(bytes.fromhex(r['after']))
        c.require(old.raw[at:at+n]==new.raw[at:at+n],'Cumulative equipment patch changed')
    return plan

def bounded_prefix(old,new,allowed):PROOF['prefix']=packages.chunked_prefix(old,new,allowed)

def adapt():
    tree=ast.parse(inspect.getsource(stage.verify));fn=tree.body[0];hits=dict(prefix=0,equipment=0,preserve=0)
    for i,node in enumerate(fn.body):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='end' for t in node.targets):
            c.require('Unexpected existing native bytes changed' in ast.unparse(fn.body[i+3]),'Prefix verifier shape changed')
            fn.body[i:i+4]=ast.parse('_bounded_prefix(old,new,allowed)').body;hits['prefix']+=1;break
    for i,node in enumerate(fn.body):
        if isinstance(node,ast.Expr) and 'Previous native lineage' in ast.unparse(node):
            fn.body[i+1:i+1]=ast.parse('_preserve(old,new,previous,prepared,linked)').body;hits['preserve']+=1;break
    lo=hi=None
    for i,node in enumerate(fn.body):
        if not isinstance(node,ast.Assign):continue
        names={t.id for t in node.targets if isinstance(t,ast.Name)}
        if 'plan' in names:lo=i
        if lo is not None and 'detail' in names:hi=i;break
    c.require(lo is not None and hi-lo==5,'Equipment verifier shape changed')
    fn.body[lo:hi]=ast.parse('plan=_equipment(old,new,equipment,read)').body;hits['equipment']+=1
    c.require(all(v==1 for v in hits.values()),'Verifier adapter shape mismatch')
    ns=stage.__dict__.copy();ns.update(_bounded_prefix=bounded_prefix,_equipment=equipment,_preserve=preserve)
    exec(compile(ast.fix_missing_locations(tree),str(Path(__file__)),'exec'),ns)
    return ns['verify'],hits

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--package-report',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();guard=c.bounded_job();c.fresh(args.output)
    linked=c.read(c.read(args.package_report)['link_report']);models=linked['signing_models']
    c.require(len(models)==6 and {(r['mode'],r['signature_size']) for r in models}==
        {(mode,size) for mode in ('signature','ldid') for size in (0x80000,0x200000,0x400000)} and
        all(r['loader_metadata_preserved'] and r['all_loader_range_bytes_compared'] and r['rebase_entries_equal'] for r in models),
        'Exact-native signing models incomplete')
    stage.package_readback=readback;stage.dump=c.dump
    verifier,hits=adapt()
    result=verifier(SimpleNamespace(package_report=args.package_report,equipment_link=Path(str(fc.private('outputs_ios_r11_port_20261025_equipment_link_report_json'))),
        libraries=Path(str(fc.private('libraries'))),output=args.output,detail_output=args.output.with_name(args.output.stem+'-details.json')))
    c.dump(args.output.with_name(args.output.stem+'-party-proof.json'),dict(result=result,proof=PROOF,adapter_shapes=hits,
        bounded_job=guard,verifier_sha256=c.sha(Path(__file__).read_bytes()),
        reused_modules={Path(m.__file__).name:c.sha(Path(m.__file__).read_bytes()) for m in (stage,packages,native)},
        validation_boundary='Actual unsigned IPA static readback; iOS native/device execution untested'))
    print(json.dumps(dict(status=result['status'],compiled_functions=result['compiled_functions'],relocations=result['relocations_checked'],
        preserved_functions=len(PROOF['preserved_native']['previous_functions']),changed_members=result['package']['changed_members'])))

if __name__=='__main__':main()
