"""Independent actual-IPA verification of one appended leaf instance getter."""
from __future__ import annotations
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
import argparse,ast,hashlib,importlib.util,inspect,json,struct,sys
from pathlib import Path
from types import SimpleNamespace
sys.dont_write_bytecode=True

TASK=Path(str(fc.client() / 'revision-ios-battle-f1069-fix-20261031'))
PREVIOUS=TASK.parent/'revision-ios-dispatch-fix-20261031'
SOURCE=Path(str(fc.REPO / 'client-patch'))
OLD_VERIFY=SOURCE/'release1031-ios-dispatch-fix-20261031/verify'
sys.path[:0]=[str(OLD_VERIFY),str(fc.private('libraries')),str(SOURCE/'ios-r11-port'),
              str(SOURCE/'pr43-ios'),str(SOURCE/'lens0907-0908')]
import dispatch_contract as dispatch
import package_contract as package_tools
import native_contract as old_native
import verify_stages as stage

OWNER='pinball.scene.battle.battle.ability::BattleAbilityTotalizerImpl'
SUM_OWNER='pinball.scene.battle.battle.ability::DuringCheckerWithDecimal'
NEW_MID=OLD_COUNT=101872
SUM_VA=0x102660568
SUM_SHA='1c479798577ddcdcf532116203dc3385acaf93713a7917372204a4824080d3e5'
INPUT_ABC_SHA='7568bf806d123809c89a0d1ad7882135299f229778887bfd300b24c8d165a530'
INPUT_NATIVE_SHA='2eb568827e72c89b7ae0f60582d6c32523468cc61286ce1b262d9cae8be54caa'
PROOF={}

def require(ok,message):dispatch.require(ok,message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):
    path=Path(path);require(path.is_file() and path.stat().st_size<=32*1024**2,'JSON input path/size')
    return json.loads(path.read_text('utf-8-sig'))
def dump(path,data):
    path=Path(path).resolve();require(path.is_relative_to((TASK/'verify-review').resolve()),'Report outside task verify-review')
    require(not path.exists(),'Fresh report required');path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2,default=str);f.write('\n')
def job_guard():
    source=SOURCE/'release1031-ios-battle-f1069-fix-20261031/native/common.py'
    spec=importlib.util.spec_from_file_location('battle_final_job_guard',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module.bounded_job()

def static_sum_slot(a,ci):
    p=dispatch.framework();sdk=dispatch.SDK/'lib/aot/lib'
    builtin=p.abcfmt.ABC((sdk/'builtin.abc').read_bytes())
    # The SDK builtin ABC contains historical early disp IDs. AVM's parser
    # explicitly ignores those fields and Traits::buildBindings allocates by
    # binding order; keep their raw values as evidence instead of guessing IDs.
    base=[];bindings={};builtin_traits=[]
    for owner in ('Object','Class'):
        instance,=[x for x in builtin.instances if builtin.mn_name(x[0])==owner]
        require(builtin.mn_name(instance[1])==('*' if owner=='Object' else 'Object'),'SDK builtin inheritance differs')
        for trait in instance[6]:
            if trait.kind not in (1,2,3):continue
            # Builtin public names use API-version namespace sets. These four
            # reviewed names are all distinct; retain raw MNs and bind by name
            # only in this SDK-only base, then reject any application collision.
            key=('sdk-builtin',builtin.mn_name(trait.name))
            require(key not in bindings,'Unexpected builtin override requires another model')
            at=len(base);bindings[key]=(at,trait.kind);base.extend([None]*(1 if trait.kind==1 else 2))
            base[at+(trait.kind==3)]=trait.data[2]
            builtin_traits.append(dict(owner=owner,name=builtin.mn_name(trait.name),kind=trait.kind,
                                       multiname=builtin.multinames[trait.name],
                                       ignored_early_disp_id=trait.data[1],relative_slot=at))
    require([(x['owner'],x['name'],x['kind']) for x in builtin_traits]==[
        ('Object','isPrototypeOf',1),('Object','hasOwnProperty',1),('Object','propertyIsEnumerable',1),
        ('Class','prototype',2)],'Actual SDK builtin Class bindings differ from reviewed model')
    app_methods=[t for t in a.classes[ci][1] if t.kind in (1,2,3)]
    require([(a.mn_name(t.name),t.kind,t.data[2]) for t in app_methods]==[
        ('sum',1,55720),('min',1,55721),('maxMaybe',1,55722),
        ('existsActive',1,55723),('collectActives',1,55724)],
        'Actual DuringCheckerWithDecimal static bindings differ from reviewed class')
    slots=list(base);bindings=dict(bindings)
    for trait in a.classes[ci][1]:
        if trait.kind not in (1,2,3):continue
        require(a.mn_name(trait.name) not in {x['name'] for x in builtin_traits},
                'Application ClassTraits overrides a builtin binding')
        key=dispatch.binding(a,trait.name)
        if key not in bindings:
            bindings[key]=(len(slots),trait.kind);slots.extend([None]*(1 if trait.kind==1 else 2))
        at,kind=bindings[key]
        require((kind==1)==(trait.kind==1),'Static dispatch binding kind differs')
        if trait.kind==3:at+=1
        slots[at]=int(trait.data[2])
    at,=[i for i,mid in enumerate(slots) if mid==55720]
    offset=0x80+at*8
    require(len(base)==5 and offset==0xa8,'Actual builtin Class/static sum slot is not +0xa8')
    return dict(builtin_Class_method_slots=len(base),builtin_traits=builtin_traits,
        early_disp_id_semantics='AVM AbcParser ignores early disp IDs; binding order allocates runtime slots',
        primary_source='https://github.com/adobe/avmplus/blob/master/core/AbcParser.cpp#L583-L601',
        app_sum_ignored_early_disp_id=next(t.data[1] for t in a.classes[ci][1] if t.kind==1 and t.data[2]==55720),
        sum_method=55720,absolute_method_slot=at,vtable_offset=offset)

def leaf_contract(a,b,runtime,prepared):
    p=dispatch.framework()
    require(len(a.methods)==OLD_COUNT and len(b.methods)==OLD_COUNT+1,'Only one MethodInfo may append')
    require(prepared['base_full_abc_sha256']==INPUT_ABC_SHA,'Wrong cumulative ABC input')
    require({int(x['method_id']) for x in prepared['methods']}=={NEW_MID},'Only new getter may compile')
    require(len(a.instances)==len(b.instances) and len(a.classes)==len(b.classes),'No classes may be added/removed')
    ci,=[i for i,x in enumerate(a.instances) if a.mn_name(x[0])==OWNER]
    require(ci==5331 and a.mn_name(a.instances[ci][1])=='Object' and a.instances[ci][2]&1,'Reviewed sealed leaf differs')
    children=[a.mn_name(x[0]) for x in a.instances if x[1]==a.instances[ci][0]]
    require(not children,'New instance method would affect a subclass')
    require(p.freeze(a.classes)==p.freeze(b.classes),'Any old class-side declaration changed')
    require(p.freeze(a.scripts)==p.freeze(b.scripts),'Any runtime script declaration changed')
    for index,(before,after) in enumerate(zip(a.instances,b.instances)):
        require(p.freeze(before[:-1])==p.freeze(after[:-1]),'Old instance header changed')
        if index!=ci:require(p.freeze(before[-1])==p.freeze(after[-1]),'Unrelated instance trait changed')
        else:
            require(len(after[-1])==len(before[-1])+1
                and p.freeze(before[-1])==p.freeze(after[-1][:-1]),'Leaf method was not a sole tail append')
            added=after[-1][-1]
            require(added.kind==1 and added.attr==0 and added.metadata==[]
                and added.name==68523 and added.data==['method',0,NEW_MID],'New getter trait contract changed')
    info=b.methods[NEW_MID]
    require((b.mn_name(info[0]),[b.mn_name(x) for x in info[1]],info[3],info[4])
            ==('Number',['int'],0,None),'New getter Number(int) signature differs')
    body,=[x for x in b.bodies if x[0]==NEW_MID]
    require(len(body[5])==44 and sha(body[5])==prepared['methods'][0]['after_code_sha256']
            and body[6]==[] and body[7]==[],'New actual getter body/activation differs')
    p.check_body(body,b)
    old_body={x[0]:x for x in a.bodies};new_body={x[0]:x for x in b.bodies}
    require(all(p.freeze(x)==p.freeze(new_body[mid]) for mid,x in old_body.items()),'Existing full body/activation changed')
    slots=dispatch.preserved_old_dispatch(a,b)
    model=dispatch.Dispatch(b);_,after_slots,_=model.model(OWNER)
    before_slots=dispatch.Dispatch(a).model(OWNER)[1]
    require(len(after_slots)==len(before_slots)+1 and after_slots[-1].method==NEW_MID,'Getter is not new final leaf slot')
    require(dispatch.focus_getter(b)==dispatch.focus_getter(runtime),'Runtime original +0x6a0 getter differs')
    sum_ci,=[i for i,x in enumerate(a.instances) if a.mn_name(x[0])==SUM_OWNER]
    sum_trait,=[t for t in a.classes[sum_ci][1] if t.kind==1 and t.data[2]==55720]
    require(a.mn_name(sum_trait.name)=='sum','Existing sum owner/name differs')
    sum_info=a.methods[55720]
    require((a.mn_name(sum_info[0]),[a.mn_name(x) for x in sum_info[1]],sum_info[3])
        ==('Number',['Array','pinball.scene.battle.battle.enemy::Enemy'],0),'Existing sum signature/ABI differs')
    require(a.mn_name(42622)==SUM_OWNER,'Native FinddefTable index does not name sum ClassClosure')
    scripts=[s for s in a.scripts if any(t.kind==4 and t.name==42622 and t.data[2]==sum_ci for t in s[1])]
    require(len(scripts)==1 and len(scripts[0][1])==1,'Sum ClassClosure is not sole script global slot')
    source_air=read(TASK/'fixtures/air01/air-report.json')
    require(source_air['status']=='actual_prepared_getter_air_negative_positive_passed'
        and source_air['prepared_full_abc_sha256']==prepared['full_abc_sha256']
        and source_air['prepared_method']==NEW_MID and source_air['negative_error_id']==1069,'AIR evidence differs')
    positive,=[x for x in source_air['runs'] if x['mode']=='positive']
    negative,=[x for x in source_air['runs'] if x['mode']=='negative']
    require(positive['exit_code']==negative['exit_code']==0 and 'GETTER_AIR_OK 60' in positive['log']
        and 'GETTER_AIR_ERROR 1069' in negative['log'],'AIR negative/positive checks did not pass')
    graft,=[x for x in positive['production_body_grafts'] if x['source_method']==NEW_MID]
    require(graft['source_code_sha256']==sha(body[5]) and graft['normalized_exact'],'AIR did not execute this getter body')
    PROOF['leaf_abc']=dict(class_index=ci,new_method=NEW_MID,new_trait_name=68523,
        new_leaf_relative_slot=len(before_slots),old_dispatch=slots,all_old_fields_bodies_activations_scripts_exact=True,
        sum_static_slot=static_sum_slot(a,sum_ci),sum_class_multiname=42622,
        sum_finddef_byte_offset=24+42622*8,air_evidence_sha256=sha((TASK/'fixtures/air01/air-report.json').read_bytes()),
        air_assertions=60,air_negative_error_id=1069,desktop_air_boundaries=source_air['fixture_inputs'])

def protected_native(old,new,previous,prepared,linked):
    require(previous['native_sha256']==INPUT_NATIVE_SHA and previous['full_abc_sha256']==INPUT_ABC_SHA,'Wrong previous carrier')
    require({int(x['method']) for x in linked['functions']}=={NEW_MID}
        and not linked['hooks'] and not linked['table_sites'],'Only one new function/table tail may change')
    require(len(previous['functions'])==359,'Expected current359 cumulative functions')
    for row in previous['functions']:
        require(old.read(row['address'],row['size'])==new.read(row['address'],row['size']),
                'Current compiled function changed: '+str(row['method']))
    before=read(PREVIOUS/'verify-review/final-run01-dispatch-summary.json')['native_wrapper_proof']
    for row in before['preserved_ranges']:
        require(old.read(row['address'],row['bytes'])==new.read(row['address'],row['bytes']),
                'Current wrapper/stock/GC path changed: '+row['name'])
    active=stage.u64(old.raw,stage.INFO+48)
    for mid in (18392,66181,55720):
        require(old.read(active+mid*8,8)==new.read(active+mid*8,8),'Protected active pointer changed')
        at=stage.LEGACY+mid*8
        require(old.raw[at:at+8]==new.raw[at:at+8],'Protected legacy pointer changed')
    require(stage.u64(old.read(active+55720*8,8))==SUM_VA
        and sha(old.read(SUM_VA,376))==SUM_SHA and new.read(SUM_VA,376)==old.read(SUM_VA,376),
        'Existing actual sum55720 body/entry differs')
    require(struct.unpack_from('<I',new.read(SUM_VA,40),32)[0]==0xaa0303f3,'Sum MethodEnv is not in x3')
    row,=linked['functions'];PROOF['new_function_bytes']=new.read(row['address'],row['size']).hex()
    PROOF['native_preservation']=dict(prior_compiled_functions_exact=359,wrapper_ranges_exact=before['preserved_ranges'],
        wrapper_binding_mutations=0,old_sum_method=55720,old_sum_pointer=SUM_VA,
        old_sum_size=376,old_sum_sha256=SUM_SHA,old_sum_MethodEnv_register='x3')
    PROOF['unwind_storage']=old_native.unwind_page_bounds(new)

def exact_equipment(old,new,equipment,read_function):
    plan=read_function(equipment['plan_file'])
    for row in plan['chunks']:require(old.read(row['va'],row['bytes'])==new.read(row['va'],row['bytes']),'Equipment chunk changed')
    for row in plan['patches']:
        at=row['file_offset'];length=len(bytes.fromhex(row['after']))
        require(old.raw[at:at+length]==new.raw[at:at+length],'Equipment patch changed')
    for row in plan['preserved_native_ranges']:
        require(old.read(row['va'],row['bytes'])==new.read(row['va'],row['bytes']),'Equipment protected range changed')
    return plan

def bounded_prefix(old,new,allowed):PROOF['prefix']=package_tools.chunked_prefix(old,new,allowed)

def adapt():
    abc_tree=ast.parse(inspect.getsource(stage.abc_checks));abc_fn=abc_tree.body[0];hits=0
    for i,node in enumerate(abc_fn.body):
        if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Tuple) \
            and [x.id for x in node.targets[0].elts]==['a','b','c','d']:
            abc_fn.body[i+1:i+1]=ast.parse('_leaf_contract(a,b,d,prepared)').body;hits+=1;break
    require(hits==1,'Original ABC verifier source shape changed')
    ns=stage.__dict__.copy();ns['_leaf_contract']=leaf_contract
    exec(compile(ast.fix_missing_locations(abc_tree),str(Path(stage.__file__)),'exec'),ns)
    stage.abc_checks=ns['abc_checks']
    tree=ast.parse(inspect.getsource(stage.verify));fn=tree.body[0];counts=dict(prefix=0,protection=0,equipment=0)
    for i,node in list(enumerate(fn.body)):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='end' for t in node.targets):
            if ast.unparse(node.value)!="old.segments[-1]['off']":continue
            require('Unexpected existing native bytes changed' in ast.unparse(fn.body[i+3]),'Original prefix block changed')
            fn.body[i:i+4]=ast.parse('_bounded_prefix(old,new,allowed)').body;counts['prefix']+=1;break
    for i,node in list(enumerate(fn.body)):
        if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and any(
            isinstance(x,ast.Constant) and x.value=='Previous native lineage' for x in node.value.args):
            fn.body[i+1:i+1]=ast.parse('_protected_native(old,new,previous,prepared,linked)').body;counts['protection']+=1;break
    lo=hi=None
    for i,node in enumerate(fn.body):
        if not isinstance(node,ast.Assign):continue
        names={t.id for t in node.targets if isinstance(t,ast.Name)}
        if 'plan' in names:lo=i
        if lo is not None and 'detail' in names:hi=i;break
    require(lo is not None and hi-lo==5,'Original equipment verifier source shape changed')
    fn.body[lo:hi]=ast.parse('plan=_exact_equipment(old,new,equipment,read)').body;counts['equipment']+=1
    require(all(x==1 for x in counts.values()),'Verifier adapter shape mismatch')
    ns=stage.__dict__.copy();ns.update(_bounded_prefix=bounded_prefix,_protected_native=protected_native,_exact_equipment=exact_equipment)
    exec(compile(ast.fix_missing_locations(tree),str(Path(stage.__file__)),'exec'),ns)
    return ns['verify'],dict(counts,leaf_abc=hits)

def actual_getter_abi(linked):
    from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM
    raw=bytes.fromhex(PROOF['new_function_bytes']);row,=linked['functions']
    instructions=list(Cs(CS_ARCH_ARM64,CS_MODE_ARM).disasm(raw,row['address']))
    tokens={x.address-row['address']:(x.mnemonic,x.op_str) for x in instructions}
    expected={0x20:('mov','x19, x2'),0x48:('ldr','x2, [x0, #0x108]'),
        0x9c:('ldr','x22, [x8, #0x20]'),0xa4:('ldr','x8, [x22, #0x10]'),
        0xb0:('ldr','x23, [x8, #0xa8]'),0xf8:('and','x20, x21, #0xfffffffffffffff8'),
        0x104:('ldr','x8, [x23, #0x10]'),0x108:('mov','x2, xzr'),
        0x10c:('mov','x0, x22'),0x110:('mov','x1, x20'),0x114:('ldr','x8, [x8, #0x50]'),
        0x118:('mov','x3, x23'),0x11c:('blr','x8'),0x120:('mov','v8.16b, v0.16b'),
        0x128:('mov','v0.16b, v8.16b'),0x14c:('ret','')}
    require(len(raw)==344 and all(tokens.get(at)==token for at,token in expected.items()),
            'Actual getter sum call/Array/Enemy/MethodEnv/Number ABI differs; do not accept a folded return stub')
    # The class lookup offset is a FinddefTable entry, not a pool-string index.
    movz,movk=struct.unpack_from('<II',raw,0x74)
    require(movz&0x7f80001f==0x52800009 and movk&0x7f80001f==0x72800009,'Sum class cache immediate shape changed')
    initial=((movz>>5)&65535)<<(((movz>>21)&3)*16);shift=((movk>>21)&3)*16
    cache=(initial&~(65535<<shift))|(((movk>>5)&65535)<<shift)
    require(cache==PROOF['leaf_abc']['sum_finddef_byte_offset']==0x53408,'Actual finddef lookup does not select sum class')
    require(PROOF['leaf_abc']['sum_static_slot']['vtable_offset']==0xa8,'Actual sum MethodEnv slot mismatch')
    return dict(method=NEW_MID,bytes=len(raw),call_address=row['address']+0x11c,
        route='FinddefTable MN42622 -> DuringCheckerWithDecimal ClassClosure -> VTable+0xa8 -> MID55720 native handler',
        actual_sum_pointer_preserved=SUM_VA,argument_registers=dict(x0='ClassClosure',x1='untagged Array',x2='NULL Enemy',x3='sum MethodEnv'),
        new_getter_MethodEnv_register='x2',Number_return_register='d0',old_sum_not_inlined_or_constant_folded=True,
        checked_instructions=[dict(offset=hex(at),op=token[0],args=token[1]) for at,token in expected.items()])

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--package-report',type=Path)
    parser.add_argument('--output',type=Path);parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    require(__debug__,'Assertions must remain enabled')
    if args.self_test:
        _,shapes=adapt();print(json.dumps(dict(adapter_shapes=shapes,prefix_controls=package_tools.prefix_selftest())));return
    require(args.package_report and args.output,'Package report/output required')
    require(args.output.resolve().is_relative_to((TASK/'verify-review').resolve()) and not args.output.exists(),'Fresh task output required')
    job=job_guard();package=read(args.package_report);linked=read(package['link_report'])
    models=linked.get('signing_models',[])
    require(len(models)==6 and {(r['mode'],r['signature_size']) for r in models}
        =={(mode,size) for mode in ('signature','ldid') for size in (0x80000,0x200000,0x400000)}
        and all(r['loader_metadata_preserved'] and r['all_loader_range_bytes_compared'] and r['rebase_entries_equal'] for r in models),
        'Finalized native lacks six matching signing/ldid models')
    stage.package_readback=lambda package,linked,previous_package:package_tools.readback(package,linked,previous_package,
        PREVIOUS/'verify-review/final-run01.json',stage.Image)
    verifier,shapes=adapt()
    options=SimpleNamespace(package_report=args.package_report,
        equipment_link=Path(str(fc.private('outputs_ios_r11_port_20261025_equipment_link_report_json'))),
        libraries=Path(str(fc.private('libraries'))),output=args.output,
        detail_output=args.output.with_name(args.output.stem+'-details.json'))
    result=verifier(options);abi=actual_getter_abi(linked)
    summary=dict(result,leaf_abc_contract=PROOF['leaf_abc'],old_native_preservation=PROOF['native_preservation'],
        actual_getter_sum_abi=abi,actual_unwind_page_storage=PROOF['unwind_storage'],
        bounded_native_prefix=PROOF['prefix'],adapter_shapes=shapes,bounded_job=job,
        current_endpoint_and_admission_preserved=True,keys_logged=False,
        verifier_source_sha256=sha(Path(__file__).read_bytes()),
        reused_module_sha256={Path(m.__file__).name:sha(Path(m.__file__).read_bytes()) for m in (dispatch,package_tools,old_native)},
        signing_models='matching exact-native finalizer evidence reused; actual metadata/ldid boundaries independently rechecked',
        validation_boundary='Desktop AIR and static AOT/package readback; iOS native/device execution remains untested')
    dump(args.output.with_name(args.output.stem+'-battle-summary.json'),summary)
    print(json.dumps(dict(status=result['status'],ipa_sha256=result['ipa_sha256'],native_sha256=result['native_sha256'],
        compiled_functions=result['compiled_functions'],relocations=result['relocations_checked'],
        old359_preserved=True,sum55720_actual_abi_verified=True,device_tested=False)))

if __name__=='__main__':main()
