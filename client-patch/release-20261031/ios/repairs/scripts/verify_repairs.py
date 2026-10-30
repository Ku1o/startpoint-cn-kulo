"""Independent actual-IPA check, preserving current wrappers and old code.

Reuse the strict stage verifier with two narrow adaptations: compare the
already-patched five wrapper against current b386, and compare masked old code
in bounded chunks instead of allocating multiple whole-native prefix copies.
"""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
from pathlib import Path
import argparse,ast,inspect,json
from types import SimpleNamespace
import repair_common as c

PREFIX_PROOF=None
PLATFORM_PROOF=None

def chunked_prefix(old,new,allowed,chunk_bytes=1024*1024):
    import verify_stages as v
    end=old.segments[-1]['off'];ranges=[]
    for lo,hi in allowed:
        v.require(0<=lo<=hi,'Allowed native range reversed')
        if lo<end and hi>0:ranges.append((max(0,lo),min(end,hi)))
    count=0
    for at in range(0,end,chunk_bytes):
        stop=min(end,at+chunk_bytes);before=old.raw[at:stop];actual=bytearray(new.raw[at:stop])
        for lo,hi in ranges:
            left,right=max(at,lo),min(stop,hi)
            if left<right:actual[left-at:right-at]=before[left-at:right-at]
        v.require(actual==before,f'Unexpected existing native bytes changed at chunk {at:x}')
        count+=1
    global PREFIX_PROOF
    PREFIX_PROOF=dict(bytes_compared=end,chunk_bytes=chunk_bytes,chunks=count,
                      semantics='same full-prefix masked byte equality; only allocation strategy changed')
    return PREFIX_PROOF

def current_equipment_range(new,old,row):
    import verify_stages as v
    if row['name']!='five-in-one-old-wrapper':return v.sha(new.read(row['va'],row['bytes']))==row['sha256']
    v.require(row['va']==0x106207aa0 and row['bytes']==208,'Exact current five-wrapper extent required')
    return new.read(row['va'],row['bytes'])==old.read(row['va'],row['bytes'])

def platform_protection(old,new,previous,prepared,linked):
    import verify_stages as v
    targets={int(r['method_id']) for r in prepared['methods']}
    v.require(not targets & {18392,66181},'Business targets overlap protected wrapper MethodInfos')
    preserved=[];intersections=[]
    for fn in previous['functions']:
        if fn['method'] in targets:
            intersections.append(fn['method']);continue
        before=old.read(fn['address'],fn['size']);after=new.read(fn['address'],fn['size'])
        v.require(before==after,'Prior compiled non-target changed: '+str(fn['method']))
        preserved.append(dict(method=fn['method'],address=fn['address'],size=fn['size'],sha256=v.sha(after)))
    ranges=[('draw-wrapper-entry',0x103d69180,128),('draw-gate',0x103d691d8,12),
        ('draw-bridge',0x103d69200,88),('draw-stock',0x102b990d4,5224),
        ('draw-scale-bl',0x103a4561c,4),('draw-scale-trampoline',0x103d694d0,396),
        ('equipment-wrapper',0x10d9d9030,52),('five-wrapper',0x106207aa0,208),
        ('resolver-stock',0x104963a08,4372)]
    proofs=[]
    for name,va,size in ranges:
        before=old.read(va,size);after=new.read(va,size)
        v.require(before==after,'Current protected platform range changed: '+name)
        proofs.append(dict(name=name,address=va,size=size,sha256=v.sha(after)))
    active=v.u64(old.raw,v.INFO+48)
    for mid in (18392,66181):
        v.require(new.read(active+mid*8,8)==old.read(active+mid*8,8),'Protected active wrapper pointer changed')
        off=v.LEGACY+mid*8
        v.require(new.raw[off:off+8]==old.raw[off:off+8],'Protected legacy wrapper pointer changed')
    global PLATFORM_PROOF
    PLATFORM_PROOF=dict(status='actual_current_platform_chain_and_prior_non_target_functions_exact',
        native_sha256=linked['native_sha256'],previous_native_sha256=c.NATIVE_SHA,
        prior_functions=len(previous['functions']),non_target_functions_preserved=len(preserved),
        explicit_target_intersections=intersections,functions=preserved,ranges=proofs,
        inherited_draw_wrapper_cfi_limitation=True)
    return PLATFORM_PROOF

def prefix_negative_controls():
    from types import SimpleNamespace
    import verify_stages as v
    raw=bytes(range(256))*4;old=SimpleNamespace(raw=raw,segments=[{'off':len(raw)}])
    changed=bytearray(raw);changed[126:130]=b'ABCD'
    chunked_prefix(old,SimpleNamespace(raw=changed),[(126,130)],127)
    rejected=[]
    for name,where in [('before_mask',125),('after_mask',130),('another_chunk',700)]:
        broken=bytearray(changed);broken[where]^=1
        try:chunked_prefix(old,SimpleNamespace(raw=broken),[(126,130)],127)
        except ValueError:rejected.append(name)
        else:raise ValueError('Chunked prefix negative control accepted: '+name)
    return dict(passed=4,rejected=rejected,scope='in-memory 1KiB samples only')

def verifier():
    import verify_stages as v
    tree=ast.parse(inspect.getsource(v.verify));fn=tree.body[0];equipment=prefix=platform=0
    for node in ast.walk(fn):
        if (isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='require'
            and len(node.args)==2 and isinstance(node.args[1],ast.Constant)
            and node.args[1].value=='Equipment protected resolver bytes changed'):
            node.args[0]=ast.parse('_current_equipment_range(new,old,r)',mode='eval').body;equipment+=1
    for i,node in list(enumerate(fn.body)):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='end' for t in node.targets):
            if ast.unparse(node.value)!="old.segments[-1]['off']":continue
            following=fn.body[i:i+4]
            c.require(len(following)==4 and isinstance(following[1],ast.Assign) and isinstance(following[2],ast.For),
                      'Original prefix comparison shape changed')
            c.require('Unexpected existing native bytes changed' in ast.unparse(following[3]),'Original prefix require changed')
            fn.body[i:i+4]=ast.parse('_chunked_prefix(old,new,allowed)').body;prefix+=1;break
    for i,node in list(enumerate(fn.body)):
        if (isinstance(node,ast.Expr) and isinstance(node.value,ast.Call)
            and any(isinstance(a,ast.Constant) and a.value=='Previous native lineage' for a in node.value.args)):
            fn.body[i+1:i+1]=ast.parse('_platform_protection(old,new,previous,prepared,linked)').body;platform+=1;break
    c.require((equipment,prefix,platform)==(1,1,1),'Independent verifier AST source shape changed')
    namespace=v.__dict__.copy();namespace.update(_current_equipment_range=current_equipment_range,
        _chunked_prefix=chunked_prefix,_platform_protection=platform_protection)
    exec(compile(ast.fix_missing_locations(tree),str(Path(v.__file__)),'exec'),namespace)
    return namespace['verify']

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--package-report',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    c.bounded_job();out=c.fresh(args.output);package=c.read(args.package_report,128*1024)
    c.require(args.package_report.resolve().is_relative_to(c.TASK.resolve()),'Package report outside new task')
    c.framework();import verify_stages as v
    linked=c.read(package['link_report']);previous=c.read(linked['previous_link_report'])
    c.require(previous['native_sha256']==c.NATIVE_SHA and previous['full_abc_sha256']==c.ABC_SHA,'Wrong previous cumulative carrier')
    out.mkdir(parents=True)
    negatives=prefix_negative_controls()
    options=SimpleNamespace(package_report=args.package_report,
        equipment_link=Path(cfg.path('outputs_ios_r11_port_20261025_equipment_link_report_json')),libraries=c.LIBRARIES,
        output=out/'raw-verification.json',detail_output=out/'independent-details.json')
    report=verifier()(options)
    c.require(PLATFORM_PROOF is not None and PREFIX_PROOF is not None,'Actual preservation proof missing')
    report.update(business_methods=17,chunked_prefix_proof=PREFIX_PROOF,prefix_negative_controls=negatives,
        prior_non_target_functions_preserved=PLATFORM_PROOF['non_target_functions_preserved'],
        current_platform_chain_byte_exact=True,inherited_draw_wrapper_cfi_limitation=True,
        wildcard_atom_abi_requires_separate_actual_compiled_proof=True,
        adapter_source_sha256=c.sha(Path(__file__).read_bytes()))
    # Existing verifier already emitted details. Save the adapter summary once;
    # do not overwrite any earlier task receipt or source/package report.
    c.dump(out/'independent-verification.json',report)
    c.dump(out/'platform-preservation.json',PLATFORM_PROOF)
    print(json.dumps(dict(status=report['status'],ipa_sha256=report['ipa_sha256'],
                         native_sha256=report['native_sha256'],compiled_functions=report['compiled_functions'],
                         relocations=report['relocations_checked'],actual_atom_abi_pending=True)))

if __name__=='__main__':main()
