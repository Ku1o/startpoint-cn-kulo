"""Display-only R7 LAN increment. Does not package or modify an APK."""
import argparse, copy, hashlib, json, struct, sys, zipfile, zlib
from pathlib import Path
sys.dont_write_bytecode = True
import build_bridge as bridge
from build_request_identity import label_helper_targets

APK_SHA = '34a8acb7ace069485596e4f31309dd9d8a19c7c56ada7cf279d27c5f3999a2b2'
SWF_SHA = 'd6c32b5a1b910e89e6f30950e7c226b4be5c49c45bcf694209ab635c7bd6ab48'
BASELINE_SHA = '1a731486c2256052011226faf17582251a1030965698fa16b6596669e8c9a922'
HELPER_TARGETS = {'campaignExchangeText', 'updatePassView', 'updateBoxPeriod', 'gachaDateText', 'formatActionLabel', 'eventDate', 'sanitizeDateConfig', 'rankingPeriodInfo'}
sha = lambda data: hashlib.sha256(data).hexdigest()

def patch(work, apk, baseline, sdk, java):
    if sha(apk.read_bytes()) != APK_SHA: raise ValueError('requires exact R7 LAN APK')
    with zipfile.ZipFile(apk) as archive: raw = archive.read('assets/worldflipper_android_release.swf')
    if sha(raw) != SWF_SHA: raise ValueError('R7 embedded LAN SWF differs')
    if sha(baseline.read_bytes()) != BASELINE_SHA: raise ValueError('original native method donor differs')
    work.mkdir(parents=True, exist_ok=True)
    source = work / 'R7-LAN-input.swf'; source.write_bytes(raw)
    version, header, tags = bridge.sc.parts(source)
    original_tags=[bytes(tag[1]) for tag in tags]
    main_tag, = [tag for tag in tags if tag[3] and any(tag[3].mn_name(i[0]) == 'pinball.context.remote::RequestQueue' for i in tag[3].instances)]
    helper_tag, = [tag for tag in tags if tag[3] and any(tag[3].mn_name(i[0]) == 'cn.content::ContentOperationsState' for i in tag[3].instances)]
    helper = bridge.compile_helper(work, sdk, java)
    helper_labels = label_helper_targets(helper)
    original_helper = helper_tag[3]; old_helper_view, helper_view = bridge.view(original_helper), bridge.view(helper)
    helper_preserved, helper_changed = [], []
    for label, indexes in old_helper_view.by_label.items():
        if len(indexes) != 1 or len(helper_view.by_label.get(label, [])) != 1: raise ValueError(('helper identity changed', label))
        old_index, = indexes; new_index, = helper_view.by_label[label]
        if old_helper_view.normalized(old_index) == helper_view.normalized(new_index): helper_preserved.append(label)
        elif label.rsplit('/', 1)[-1].split('|')[0].rsplit('::',1)[-1] in HELPER_TARGETS: helper_changed.append(label)
        else: raise ValueError(('unrelated helper body changed', label))
    def fields(abc):
        return [{ 'owner': abc.mn_name(instance[0]), 'instance': [(abc.mn_name(t.name),t.kind,t.data) for t in instance[6] if t.kind in (0,6)],
            'static': [(abc.mn_name(t.name),t.kind,t.data) for t in cls[1] if t.kind in (0,6)] } for instance,cls in zip(abc.instances,abc.classes)]
    # Compare field names, explicit slot ids, types and order semantically across pools.
    def semantic_fields(abc):
        result = []
        for instance, cls in zip(abc.instances, abc.classes):
            for scope, traits in [('instance', instance[6]), ('static', cls[1])]:
                result.append((abc.mn_name(instance[0]),scope,[(abc.mn_name(t.name),t.kind,t.data[1],abc.mn_name(t.data[2])) for t in traits if t.kind in (0,6)]))
        return result
    if semantic_fields(original_helper) != semantic_fields(helper): raise ValueError('helper field/slot layout changed')
    abc = main_tag[3]; original = copy.deepcopy(abc); target = bridge.view(abc)
    donor_tags = bridge.sc.parts(baseline)[2]
    donor = next(tag[3] for tag in donor_tags if tag[3] and any(tag[3].mn_name(i[0]) == 'pinball.context.remote::RequestQueue' for i in tag[3].instances))
    donor_view = bridge.view(donor)
    edits = []; allowed = set(); pool = bridge.PoolEditor(abc)
    def q(namespace, name):
        for index,value in enumerate(abc.multinames):
            if value[0] == 7 and abc.s(value[2]) == name and abc.namespaces[value[1]][0] == 22 and abc.ns_name(value[1]) == namespace and abc.namespaces[value[1]][1] != 0: return index
        string = pool.string(namespace) if namespace else next((i for i,v in enumerate(abc.strings) if i and v == b''), None)
        if string is None: abc.strings.append(b''); string = len(abc.strings)-1
        abc.namespaces.append((22,string)); abc.multinames.append((7,len(abc.namespaces)-1,pool.string(name))); return len(abc.multinames)-1
    state = q('cn.content','ContentOperationsState')
    for owner in ['towerDungeon::TowerDungeonEventLogic','expertSingleEvent::ExpertSingleEventLogic','soloTimeAttack::SoloTimeAttackEventLogic']:
        label = 'pinball.common.data.quest.event.'+owner+'/getRemainingTimeLabel|1'
        index, = target.by_label[label]; donor_index, = donor_view.by_label[label]
        abc.bodies[index] = bridge.p.Importer(target,donor_view).body(donor_index,abc.bodies[index][0])
        if target.normalized(index) != donor_view.normalized(donor_index): raise ValueError(('native restore mismatch',label))
        allowed.add(index); edits.append({'label':label,'body':index,'method':abc.bodies[index][0],'kind':'restore-original-native-no-date-or-count','originalNativeNormalizedExact':True})
    origin_maps={}
    def graft(label, at, code, expression_end=None, original_offsets=False):
        index, = target.by_label[label]; body = abc.bodies[index]
        before_normalized=target.normalized(index);before_hash=sha(body[5])
        prior_origins=origin_maps.get(index,list(range(len(before_normalized[0]))))
        if original_offsets:
            at=prior_origins.index(at)
            if expression_end is not None:expression_end=prior_origins.index(expression_end)
        block = bridge.p.asm.assemble(code)
        if expression_end is not None:
            for ins in block:
                if ins.op == 0x10 and ins.target == len(block): ins.target += expression_end-at
        original_count = len(bridge.p.asm.decode(body[5])); origins = list(range(original_count))
        body[5],body[6],_ = bridge.p.asm.splice(body,at,block,bridge.p.asm.ENTER); origins[at:at] = [None]*len(block)
        decoded = bridge.p.asm.decode(body[5]); destinations = set()
        for ins in decoded:
            if ins.target is not None: destinations.add(ins.target)
            if ins.cases is not None: destinations.update([ins.default]+ins.cases)
        for site in sorted([i for i in destinations if i == len(decoded) or decoded[i].op != 0x09],reverse=True):
            body[5],body[6],_ = bridge.p.asm.splice(body,site,[bridge.p.asm.Instruction(0x09)],bridge.p.asm.ENTER);origins[site:site]=[None]
        body[1] += 6; bridge.p.check_body(body,abc)
        spans=[]; site=source_site=0
        while site < len(origins):
            if origins[site] is None:
                start=site
                while site<len(origins) and origins[site] is None:site+=1
                spans.append({'at':source_site,'instructions':site-start})
            else:
                if origins[site]!=source_site:raise ValueError('original instruction reordered')
                source_site+=1;site+=1
        proof=bridge.p.insertion_proof(before_normalized,target.normalized(index),spans)
        origin_maps[index]=[None if old is None else prior_origins[old] for old in origins]
        allowed.add(index);edits.append({'label':label,'body':index,'method':body[0],'kind':'display-only-insertion','insertionProof':proof,'beforeCodeSha256':before_hash,'afterCodeSha256':sha(body[5]),'expressionBypass':[at,expression_end] if expression_end else None})
    label='pinball.ui.component.template._QuestLikeSceneTemplateView::TimeRangeText/<ctor>'
    index,=target.by_label[label];rows=target.normalized(index)[0]
    if rows[74][0]!=0xd3 or rows[95][0]!=0x4f or 'set_text' not in str(rows[95]):raise ValueError('native TimeRangeText expression moved')
    graft(label,74,[('getlex',state),('getlocal',9),('callproperty',q('','dateRangeLabel'),1),('dup',),('pushnull',),('ifeq','ORIGINAL_DATE'),('coerce',q('','String')),('jump','DATE_READY'),('label','ORIGINAL_DATE'),('pop',),('label','DATE_READY')],95)
    for owner in ['pinball.scene.passCard::PassCardView','pinball.scene.activeMission::ActiveMissionView','pinball.scene.collectItemEventMission::CollectItemEventMissionView','pinball.scene.event.ranking.questSelect::RankingEventQuestSelectView']:
        label=owner+'/run|1';index,=target.by_label[label];decoded=bridge.p.asm.decode(abc.bodies[index][5])
        sites=[i for i,ins in enumerate(decoded) if ins.op==0x4a and abc.mn_name(ins.args[0])=='pinball.ui.component.template::QuestLikeSceneTemplateView' and ins.args[1]==2]
        if len(sites)!=1:raise ValueError(('native template constructor changed',label,sites))
        graft(label,sites[0],[('getlex',state),('swap',),('getlocal_0',),('swap',),('callproperty',q('','preparePeriodConfig'),2)])
    for owner in ['raid::RaidEventSceneTools$','rush::RushEventSceneTools$']:
        label='pinball.scene.event.'+owner+'/getDate|1'
        graft(label,2,[('getlex',state),('getlocal_1',),('callproperty',q('','eventDate'),1),('dup',),('pushnull',),('ifeq','ORIGINAL_DATE'),('coerce',q('haxe.ds','Option')),('returnvalue',),('label','ORIGINAL_DATE'),('pop',)])
    label='pinball.scene.activeMission::RealIncentiveActiveMissionView/run|1'
    index,=target.by_label[label]; rows=target.normalized(index)[0]
    if rows[279][0]!=0x46 or 'getPlayablePeriod' not in str(rows[279]) or rows[398][0]!=0x5e or 'periodBackLayout' not in str(rows[398]):raise ValueError('native real incentive date precomputation moved')
    # Descending offsets keep the actual R7 instruction identities stable. All
    # original instructions and destinations remain as the unmanaged fallback.
    for at,end,phase in [(643,654,'receive'),(575,586,'lottery'),(507,518,'playable')]:
        if rows[end][0]!=0x4f or 'set_text' not in str(rows[end]):raise ValueError(('native real incentive text moved',phase))
        graft(label,at,[('getlex',state),('getlocal_2',),('pushstring',pool.string(phase)),('callproperty',q('','realIncentiveText'),2),('dup',),('pushnull',),('ifeq','ORIGINAL_TEXT'),('coerce',q('','String')),('jump','TEXT_READY'),('label','ORIGINAL_TEXT'),('pop',),('label','TEXT_READY')],end,True)
    graft(label,278,[('getlex',state),('getlocal_2',),('callproperty',q('','realIncentiveManaged'),1),('iffalse','ORIGINAL_PERIODS'),('getlex',state),('getlocal_2',),('pushfalse',),('callproperty',q('','realIncentiveLotteryDate'),2),('setlocal',13),('getlex',state),('getlocal_2',),('pushtrue',),('callproperty',q('','realIncentiveLotteryDate'),2),('setlocal',16),('jump','PERIODS_READY'),('label','ORIGINAL_PERIODS'),('label','PERIODS_READY')],398,True)
    for index,body in enumerate(original.bodies):
        if index not in allowed and bridge.p.freeze(body)!=bridge.p.freeze(abc.bodies[index]):raise ValueError(('unrelated native body changed',index))
    for name in ['instances','classes','methods','scripts','metadata']:
        if bridge.p.freeze(getattr(original,name))!=bridge.p.freeze(getattr(abc,name)):raise ValueError(('native ABI changed',name))
    for tag,replacement in [(main_tag,bridge.sc.serialize(abc,main_tag[4])),(helper_tag,helper.serialize())]:
        tag[1]=struct.pack('<HI',(82<<6)|63,len(tag[2])+len(replacement))+tag[2]+replacement
    payload=header+b''.join(tag[1] for tag in tags)
    result=b'CWS'+bytes([version])+struct.pack('<I',len(payload)+8)+zlib.compress(payload)
    output=work/'content-operations-android.swf';output.write_bytes(result)
    (work/'production-helper.abc').write_bytes(helper.serialize())
    report={'inputApkSha256':APK_SHA,'inputSwfSha256':SWF_SHA,'outputSha256':sha(result),'helperSourceSha256':sha((bridge.HERE/'src/cn/content/ContentOperationsState.as').read_bytes()),'helperAbcSha256':sha(helper.serialize()),'nativeEdits':edits,'nativeUnchangedBodies':len(original.bodies)-len(allowed),'nativeAbiUnchanged':True,'helperUnchangedMethods':helper_preserved,'helperChangedMethods':helper_changed,'helperFieldsUnchanged':semantic_fields(helper),'helperLabelProof':helper_labels,'packaged':False,'deviceTested':False}
    # Reparse final bytes independently; serialized target identities are authoritative.
    final_tags=bridge.sc.parts(output)[2]
    final_main=next(tag[3] for tag in final_tags if tag[3] and any(tag[3].mn_name(i[0])=='pinball.context.remote::RequestQueue' for i in tag[3].instances))
    final_helper=next(tag[3] for tag in final_tags if tag[3] and any(tag[3].mn_name(i[0])=='cn.content::ContentOperationsState' for i in tag[3].instances))
    if sha(final_helper.serialize())!=sha(helper.serialize()) or bridge.p.freeze(final_main.bodies)!=bridge.p.freeze(abc.bodies):raise ValueError('final SWF readback differs')
    changed_tag_indexes=[i for i,(before,after) in enumerate(zip(original_tags,final_tags)) if before!=after[1]]
    expected_tags=[tags.index(main_tag),tags.index(helper_tag)]
    if sorted(changed_tag_indexes)!=sorted(expected_tags) or len(final_tags)!=len(tags):raise ValueError('unrelated SWF tag changed')
    report['tagProof']={'count':len(tags),'changed':[{'index':i,'type':final_tags[i][0],'name':final_tags[i][2][4:].rstrip(b'\0').decode('utf8'),'beforeSha256':sha(original_tags[i]),'afterSha256':sha(final_tags[i][1])} for i in changed_tag_indexes],'otherTagsByteExact':True}
    report['protectedNativeMethods']=[]
    for label in ['pinball.context.remote::RequestQueue/startRequest|1','pinball.common.data.event::EventListLogic/<ctor>','pinball.common.data.bossBattle::BossBattleHeaderBannerResolver$/resolve|1','pinball.scene.boxGacha::BoxGachaScene/buttonClicked|1']:
        matches=target.by_label.get(label,[])
        if len(matches)!=1:raise ValueError(('protected identity absent',label,matches))
        i,=matches
        if bridge.p.freeze(original.bodies[i])!=bridge.p.freeze(final_main.bodies[i]):raise ValueError(('protected body changed',label))
        report['protectedNativeMethods'].append({'label':label,'body':i,'method':abc.bodies[i][0],'codeSha256':sha(final_main.bodies[i][5]),'byteExact':True})
    report['finalReadbackExact']=True
    (work/'period-display-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['work','input-apk','native-baseline','sdk','java']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();report=patch(args.work,args.input_apk,args.native_baseline,args.sdk,args.java)
    print(json.dumps({key:report[key] for key in ['outputSha256','helperAbcSha256','nativeUnchangedBodies','nativeAbiUnchanged','finalReadbackExact']},indent=2))
