"""Exact R8 LAN -> bounded exchange repair SWF; never packages an APK.

The full bridge reuses repair_native_starts after its existing insertion proofs.
Only the independent helper may append fields. Original game ABI remains exact.
"""
import argparse, copy, hashlib, json, struct, sys, zipfile, zlib
from pathlib import Path
sys.dont_write_bytecode = True
import build_bridge as bridge
from build_request_identity import label_helper_targets

R8_APK_SHA256 = '0d04167402f79bee075d1838a49fc9ef025e3c60a0f836e8201ede1ec5c94e78'
R8_SWF_SHA256 = '404b8a61fc03847516cbd9e1a94bf9c7fc6b1bc7d82904fcb1e77dcf8a340928'
EVENT_BASE = 'pinball.common.data.quest.event.common::EventLogicBase'
STAR_LABEL = 'pinball.common.data.shop::StarCrumbExchangeProductLogic/isWithinPeriod|1'
HELPER_CHANGES = {'captureResponse', 'updatePassView', '<cinit>'}
HELPER_ADDITIONS = {'starCrumbDecision', 'nativeEventPeriodStart'}

def sha(data):return hashlib.sha256(data).hexdigest()

def qname(abc,pool,namespace,name):
    for i,m in enumerate(abc.multinames):
        if m[0]==7 and abc.s(m[2])==name and abc.namespaces[m[1]][0]==22 and abc.ns_name(m[1])==namespace and abc.namespaces[m[1]][1]!=0:return i
    string=pool.string(namespace) if namespace else next((i for i,v in enumerate(abc.strings) if i and v==b''),None)
    if string is None:abc.strings.append(b'');string=len(abc.strings)-1
    abc.namespaces.append((22,string));abc.multinames.append((7,len(abc.namespaces)-1,pool.string(name)));return len(abc.multinames)-1

def physical_labels(abc,body):
    rows=bridge.p.asm.decode(body[5]);destinations=set()
    for ins in rows:
        if ins.target is not None:destinations.add(ins.target)
        if ins.cases is not None:destinations.update([ins.default]+ins.cases)
    missing=sorted((i for i in destinations if i==len(rows) or rows[i].op!=0x09),reverse=True)
    for i in missing:body[5],body[6],_=bridge.p.asm.splice(body,i,[bridge.p.asm.Instruction(0x09)],bridge.p.asm.ENTER)
    final=bridge.p.asm.decode(body[5])
    for ins in final:
        for i in ([ins.target] if ins.target is not None else [])+([ins.default]+ins.cases if ins.cases is not None else []):
            if i>=len(final) or final[i].op!=0x09:raise ValueError(('branch destination is not a physical label',i))
    bridge.p.check_body(body,abc)
    return len(missing)

def repair_native_starts(abc,target,q,state):
    """Change only the start call in each original action-fallback expression.

    Preserve its receiver and virtual end getter. Inverse the call substitution
    and two inserted receiver-adapter instructions to prove original code exact.
    """
    result=[]
    for method,end_name in [('getExchangeableTimeRange','get_exchangeableEndTime'),('getBrowsableTimeRange','getBrowsableEndTime')]:
        label=EVENT_BASE+'/'+method+'|1';index,=target.by_label[label];body=abc.bodies[index];before=copy.deepcopy(body)
        if before[6]:raise ValueError(('unexpected exception table',label))
        rows=bridge.p.asm.decode(body[5])
        sites=[i for i,x in enumerate(rows) if x.op==0x46 and abc.mn_name(x.args[0])=='get_startTime' and x.args[1]==0]
        end_sites=[i for i,x in enumerate(rows) if x.op==0x46 and abc.mn_name(x.args[0])==end_name and x.args[1]==0]
        if len(sites)!=1 or len(end_sites)!=1 or end_sites[0]<=sites[0]:raise ValueError(('native fallback expression moved',label,sites,end_sites))
        at=sites[0];prior_call=copy.deepcopy(rows[at])
        if at==0 or rows[at-1].op not in (0x5e,0xd0):raise ValueError(('unexpected native start receiver',label))
        block=bridge.p.asm.assemble([('getlex',state),('swap',)])
        body[5],body[6],_=bridge.p.asm.splice(body,at,block,bridge.p.asm.ENTER)
        rows=bridge.p.asm.decode(body[5]);rows[at+len(block)].args=[q('','nativeEventPeriodStart'),1]
        body[5]=bridge.p.asm.encode(rows)[0];body[1]+=2
        audit=copy.deepcopy(rows);audit[at+len(block)]=prior_call
        audit_raw=bridge.p.asm.encode(audit)[0]
        if bridge.p.asm.unsplice(audit_raw,at,len(block))!=before[5]:raise ValueError(('native start inverse differs',label))
        labels=physical_labels(abc,body)
        # No new branch is introduced; existing labels must therefore suffice.
        if labels:raise ValueError(('unexpected branch-label rewrite in start adapter',label,labels))
        result.append({'label':label,'body':index,'method':body[0],'kind':'native-action-fallback-start-only','originalStartCallInstruction':at,'receiverAdapterInstructions':len(block),'originalCodeSha256':sha(before[5]),'candidateCodeSha256':sha(body[5]),'inverseOriginalCodeExact':True,'virtualEndGetterPreserved':end_name,'branchTargetsPhysical':True})
    return result

def helper_fields(abc):
    result=[]
    def default_value(t):
        index,kind=t.data[3:5]
        if index==0:return None
        if kind==1:return ('string',abc.s(index))
        if kind in (3,4,6):return (kind,getattr(abc,{3:'ints',4:'uints',6:'doubles'}[kind])[index])
        return (kind,index)
    for instance,cls in zip(abc.instances,abc.classes):
        for scope,traits in [('instance',instance[6]),('static',cls[1])]:
            effective_slot=0
            for t in traits:
                if t.kind in (0,6):
                    effective_slot=t.data[1] or effective_slot+1
                    result.append((abc.mn_name(instance[0]),scope,abc.mn_name(t.name),t.kind,t.data[1],abc.mn_name(t.data[2]),effective_slot,default_value(t)))
    return result

def verify_helper(old,new):
    ov,nv=bridge.view(old),bridge.view(new);preserved=[];changed=[];added=[]
    for label,indices in ov.by_label.items():
        if len(indices)!=1 or len(nv.by_label.get(label,[]))!=1:raise ValueError(('helper method identity changed',label))
        oi,=indices;ni,=nv.by_label[label]
        if ov.normalized(oi)==nv.normalized(ni):preserved.append(label)
        elif label.rsplit('/',1)[-1].split('|')[0].rsplit('::',1)[-1] in HELPER_CHANGES:changed.append(label)
        else:raise ValueError(('unrelated helper method changed',label))
    for label in nv.by_label:
        if label not in ov.by_label:
            if label.rsplit('/',1)[-1].split('|')[0].rsplit('::',1)[-1] not in HELPER_ADDITIONS:raise ValueError(('unexpected helper addition',label))
            added.append(label)
    if {x.rsplit('/',1)[-1].split('|')[0].rsplit('::',1)[-1] for x in added}!=HELPER_ADDITIONS:raise ValueError('both new helper functions are required')
    before,after=helper_fields(old),helper_fields(new)
    if [x for x in after if any(x[0:3]==v[0:3] for v in before)]!=before:raise ValueError('old helper field slot/order/type changed')
    extra=[x for x in after if not any(x[0:3]==v[0:3] for v in before)]
    if {x[2].rsplit('::',1)[-1] for x in extra}!={'retainedStarCrumb','hasRetainedStarCrumb'}:raise ValueError(('unexpected new helper state fields',extra))
    for x in extra:
        if x[1]!='static' or x[6]<=max((v[6] for v in before if v[:2]==x[:2]),default=0):raise ValueError(('helper field must append independent static slot',x))
    return {'unchangedMethods':preserved,'changedMethods':changed,'addedMethods':added,'appendedStaticFields':extra,'oldFieldSlotsAndOrderExact':True}

def patch(work,apk,sdk,java):
    raw_apk=apk.read_bytes()
    if sha(raw_apk)!=R8_APK_SHA256:raise ValueError('requires exact selected R8 LAN APK')
    with zipfile.ZipFile(apk) as z:raw=z.read('assets/worldflipper_android_release.swf')
    if sha(raw)!=R8_SWF_SHA256:raise ValueError('R8 SWF identity differs')
    work.mkdir(parents=True,exist_ok=True);source=work/'R8-LAN-input.swf';source.write_bytes(raw)
    version,header,tags=bridge.sc.parts(source);original_tags=[bytes(t[1]) for t in tags]
    main_tag,=[t for t in tags if t[3] and any(t[3].mn_name(i[0])=='pinball.context.remote::RequestQueue' for i in t[3].instances)]
    helper_tag,=[t for t in tags if t[3] and any(t[3].mn_name(i[0])=='cn.content::ContentOperationsState' for i in t[3].instances)]
    source_hash=sha((bridge.HERE/'src/cn/content/ContentOperationsState.as').read_bytes())
    helper=bridge.compile_helper(work,sdk,java);helper_labels=label_helper_targets(helper)
    if sha((bridge.HERE/'src/cn/content/ContentOperationsState.as').read_bytes())!=source_hash:raise ValueError('helper source changed during compile')
    helper_proof=verify_helper(helper_tag[3],helper)
    abc=main_tag[3];old=copy.deepcopy(abc);target=bridge.view(abc);pool=bridge.PoolEditor(abc)
    q=lambda ns,name:qname(abc,pool,ns,name)
    state=q('cn.content','ContentOperationsState');edits=repair_native_starts(abc,target,q,state)
    index,=target.by_label[STAR_LABEL];body=abc.bodies[index];before=copy.deepcopy(body);before_normalized=bridge.view(old).normalized(index)
    if [x.op for x in bridge.p.asm.decode(body[5])[:2]]!=[0xd0,0x30]:raise ValueError('star period prologue moved')
    code=bridge.p.asm.assemble([('getlex',state),('getlocal_0',),('callproperty',q('','starCrumbDecision'),1),('dup',),('pushbyte',0),('iflt','ORIGINAL'),('convert_b',),('returnvalue',),('label','ORIGINAL'),('pop',)])
    at=2;body[5],body[6],_=bridge.p.asm.splice(body,at,code,bridge.p.asm.ENTER);body[1]=max(body[1],12)
    origins=list(range(len(bridge.p.asm.decode(before[5]))));origins[at:at]=[None]*len(code)
    rows=bridge.p.asm.decode(body[5]);destinations=set()
    for x in rows:
        if x.target is not None:destinations.add(x.target)
        if x.cases is not None:destinations.update([x.default]+x.cases)
    missing=sorted((i for i in destinations if i==len(rows) or rows[i].op!=0x09),reverse=True)
    for site in missing:
        body[5],body[6],_=bridge.p.asm.splice(body,site,[bridge.p.asm.Instruction(0x09)],bridge.p.asm.ENTER);origins[site:site]=[None]
    physical_labels(abc,body)
    spans=[];i=source_i=0
    while i<len(origins):
        if origins[i] is None:
            start=i
            while i<len(origins) and origins[i] is None:i+=1
            spans.append({'at':source_i,'instructions':i-start})
        else:
            if origins[i]!=source_i:raise ValueError('original star instruction reordered')
            source_i+=1;i+=1
    proof=bridge.p.insertion_proof(before_normalized,target.normalized(index),spans)
    edits.append({'label':STAR_LABEL,'body':index,'method':body[0],'kind':'retained-star-product-decision-gate','originalCodeSha256':sha(before[5]),'candidateCodeSha256':sha(body[5]),'insertionProof':proof,'branchTargetsPhysical':True})
    allowed={x['body'] for x in edits}
    if len(allowed)!=3:raise ValueError('exactly three native bodies must change')
    for i,b in enumerate(old.bodies):
        if i not in allowed and bridge.p.freeze(b)!=bridge.p.freeze(abc.bodies[i]):raise ValueError(('unrelated native body changed',i))
    abi={}
    for field in ['instances','classes','methods','scripts','metadata']:
        abi[field]=bridge.p.freeze(getattr(old,field))==bridge.p.freeze(getattr(abc,field))
        if not abi[field]:raise ValueError(('native ABI changed',field))
    pools={}
    for field in ['ints','uints','doubles','strings','namespaces','ns_sets','multinames']:
        original=getattr(old,field);pools[field]=bridge.p.freeze(original)==bridge.p.freeze(getattr(abc,field)[:len(original)])
        if not pools[field]:raise ValueError(('native constant pool prefix changed',field))
    for tag,replacement in [(main_tag,bridge.sc.serialize(abc,main_tag[4])),(helper_tag,helper.serialize())]:
        tag[1]=struct.pack('<HI',(82<<6)|63,len(tag[2])+len(replacement))+tag[2]+replacement
    payload=header+b''.join(t[1] for t in tags);out=b'CWS'+bytes([version])+struct.pack('<I',len(payload)+8)+zlib.compress(payload)
    output=work/'content-operations-android.swf';output.write_bytes(out);(work/'production-helper.abc').write_bytes(helper.serialize())
    final=bridge.sc.parts(output)[2]
    fm=next(t[3] for t in final if t[3] and any(t[3].mn_name(i[0])=='pinball.context.remote::RequestQueue' for i in t[3].instances))
    fh=next(t[3] for t in final if t[3] and any(t[3].mn_name(i[0])=='cn.content::ContentOperationsState' for i in t[3].instances))
    if fm.serialize()!=abc.serialize() or bridge.p.freeze(fm.bodies)!=bridge.p.freeze(abc.bodies) or fh.serialize()!=helper.serialize():raise ValueError('final main/helper readback differs')
    for field in abi:
        if bridge.p.freeze(getattr(fm,field))!=bridge.p.freeze(getattr(old,field)):raise ValueError(('final ABI differs',field))
    changed=[i for i,t in enumerate(final) if i>=len(original_tags) or t[1]!=original_tags[i]]
    expected=[tags.index(main_tag),tags.index(helper_tag)]
    if len(final)!=len(tags) or sorted(changed)!=sorted(expected):raise ValueError('unrelated SWF tags changed')
    report={'inputApkSha256':R8_APK_SHA256,'inputSwfSha256':R8_SWF_SHA256,'outputSha256':sha(out),'helperSourceSha256':source_hash,'helperAbcSha256':sha(helper.serialize()),'helperChanges':helper_proof,'helperLabelProof':helper_labels,'nativeEdits':edits,'nativeUnchangedBodies':len(old.bodies)-3,'nativeAbiExact':abi,'nativeOriginalConstantPoolPrefixesExact':pools,'tagProof':{'count':len(tags),'changed':[{'index':i,'type':final[i][0],'name':final[i][2][4:].rstrip(b'\0').decode('utf-8'),'beforeSha256':sha(original_tags[i]),'afterSha256':sha(final[i][1])} for i in changed],'otherTagsByteExact':True},'finalReadbackExact':True,'packaged':False,'deviceTested':False}
    (work/'exchange-repair-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'outputSha256':sha(out),'nativeChangedBodies':3,'nativeUnchangedBodies':len(old.bodies)-3,'helperChangedMethods':helper_proof['changedMethods'],'helperAddedMethods':helper_proof['addedMethods'],'finalReadbackExact':True}))

def main():
    p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);p.add_argument('--apk',type=Path,required=True);p.add_argument('--sdk',type=Path,required=True);p.add_argument('--java',type=Path,required=True);a=p.parse_args();patch(a.work,a.apk,a.sdk,a.java)

if __name__=='__main__':main()
