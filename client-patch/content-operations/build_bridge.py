"""Compile the independent state class and graft bounded Android methods.

Produces compiler/SWF candidates only. No APK, IPA, registry, signing or CDN writes.
"""
import argparse, copy, faulthandler, hashlib, importlib.util, json, struct, subprocess, sys, types, zipfile, zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE.parent/'lens0907-0908'))
import build_swf as p
from swfabc import swftags, PoolEditor

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
sc=load('content_startup_swf',HERE.parent/'startup-cache/build_swf.py')
def sha(raw):return hashlib.sha256(raw).hexdigest()
ADDITIONAL_TARGETS = [
    ('pinball.common.data.mission.repository::PassCardEventRepository','getCurrentPassId','selectPass','id','option'),
    ('pinball.common.data.mission.repository::PassCardEventRepository','getCurrentPassEvent','selectPass','event','option'),
    ('pinball.common.data.mission.activeMission::ActiveMissionEventLogic','isWithinPeriod','contentDecision','visible','int'),
    ('pinball.common.data.mission.activeMission::ActiveMissionEventLogic','getPeriod','contentPeriod','visible','option'),
    ('pinball.common.data.mission.activeMission::ActiveMissionEventLogic','getPlayablePeriod','contentPeriod','enter','option'),
    ('pinball.common.data.mission.activeMission::ActiveMissionEventLogic','getRewardReceivePeriod','contentPeriod','claim','option'),
    ('pinball.common.data.mission.activeMission::ActiveMissionEventLogic','get_endTime','contentEnd','visible','option'),
    ('pinball.common.data.mission.activeMission::ActiveMissionEventLogic','getLotteryPeriod','activeLotteryPeriod',None,'option'),
    ('pinball.common.data.mission.activeMission::ActiveMissionEventLogic','getRealIncentiveMissionEventTimeKind','activeTimeKind',None,'option'),
    ('pinball.common.data.mission.activeMission::ActiveMissionLogic','duringShowPeriod','contentDecision','visible','int'),
    ('pinball.common.data.mission.activeMission::ActiveMissionLogic','duringEnablePeriod','contentDecision','enter','int'),
    ('pinball.common.data.mission.common::MissionLogicImpl','duringShowPeriod','contentDecision','visible','int'),
    ('pinball.common.data.mission.common::MissionLogicImpl','duringEnablePeriod','contentDecision','enter','int'),
    ('pinball.common.data.boxGacha::BoxGachaLogic','isWithinPeriod','contentDecision','visible','int'),
    ('pinball.common.data.boxGacha::BoxGachaLogic','getPeriod','contentPeriod','visible','option'),
    ('pinball.common.data.boxGacha::BoxLogic','isWithinPeriod','contentDecision','enter','int'),
    ('pinball.common.data.boxGacha::BoxLogic','getPeriod','contentPeriod','enter','option'),
    ('pinball.common.data.shop::ShopProductLogic','isWithinPeriod','contentDecision','visible','int'),
    ('pinball.common.data.shop::ShopProductLogic','canBuyDetail','shopBuyGate',None,'option'),
    ('pinball.common.data.shop::ShopProductLogic','get_endTime','shopSharedEnd',None,'option'),
    ('pinball.common.data.shop::StarCrumbExchangeProductLogic','isWithinPeriod','starCrumbDecision',None,'int'),
    ('pinball.common.data.shop::EventItemShopProductLogic','getShopEndTime','contentEnd','exchange','option'),
    ('pinball.common.data.collectItem::CollectItemEventLogic','isWithinPeriod','contentDecision','visible','int'),
    ('pinball.common.data.collectItem::CollectItemEventLogic','getPeriod','contentPeriod','visible','option'),
    ('pinball.common.data.collectItem::CollectItemEventLogic','get_exchangableEndTime','contentEnd','exchange','option'),
    ('pinball.common.data.collectItem::CollectItemEventLogic','isExchangingAvailable','collectExchangeDecision',None,'int'),
    ('pinball.common.data.collectItem::CollectItemEventLogic','getRemainingTimeLabel','collectExchangeLabel',None,'option'),
    ('pinball.common.data.collectItem::CollectItemEventLogic','get_startTime','contentStart','enter','option'),
    ('pinball.common.data.collectItem::CollectItemEventLogic','get_endTime','contentNumericEnd','enter','option'),
    ('pinball.common.data.mission.common::MissionLogicImpl','getRemainingTime','missionRemaining','event','option'),
    ('pinball.common.data.mission.activeMission::ActiveMissionLogic','getRemainingTime','missionRemaining','event','option'),
    ('pinball.common.data.mission.daily::PassCardDailyMissionLogic','getRemainingTime','missionRemaining','daily','option'),
    ('pinball.common.data.mission.daily::PassCardWeekMissionLogic','getRemainingTime','missionRemaining','week','option'),
    ('pinball.common.data.mission.daily::PassCardEventMissionLogic','getRemainingTime','missionRemaining','event','option'),
    ('pinball.scene.passCard::PassCardView','draw','updatePassView',None,'void'),
    ('pinball.common.data.quest.event.common::EventLogicBase','getPlayableTimeRange','contentPeriod','enter','option'),
    ('pinball.common.data.quest.event.common::EventLogicBase','getExchangeableTimeRange','contentPeriod','exchange','option'),
    ('pinball.common.data.quest.event.common::EventLogicBase','getBrowsableTimeRange','contentPeriod','visible','option'),
    ('pinball.common.data.quest.event.common::EventLogicBase','getBrowsableEndTime','contentEnd','visible','option'),
    ('pinball.common.data.quest.event.common::EventLogicBase','getDisplayRemainingExchangeableTime','contentRemaining','exchange','option'),
    ('pinball.common.data.quest.event.ranking::RankingEventSingleQuestLogic','isWithinViewablePeriod','questDecision','visible','int'),
    ('pinball.common.data.quest.event.raid::RaidEventQuestLogic','isWithinViewablePeriod','questDecision','visible','int'),
    ('pinball.common.data.quest.event.challengeDungeon::CampaignAppliedChallengeDungeonEventLogic','get_exchangeableEndTime','contentEnd','exchange','option'),
    ('pinball.common.data.quest.common::CommonQuestBase','isEarlierThanPeriodEnd','questDecision','visible','int'),
    ('pinball.common.data.quest.event.ranking::RankingEventLogic','getNowRankingEventTimeKind','rankingTimeKind',None,'option'),
    ('pinball.scene.campaign.specialExchange::SpecialExchangeCampaignScene','getDateText','specialExchangeDateText',None,'option'),
    ('pinball.common.data.campaign.startDashExchange::StartDashExchangeCampaignLogic','get_buyEndTime','startDashBuyEnd',None,'option'),
    ('pinball.scene.gacha.top.common::GachaSceneViewBase','setupText','gachaDateText',None,'handled'),
    ('pinball.common.data.quest.event.scoreAttack::ScoreAttackEventLogic','getRemainingTimeUntilNextEvent','scoreRemaining',None,'option'),
    ('pinball.scene.event.ranking.questSelect::RankingEventQuestSelectScene','getEventPeriodInfo','rankingPeriodInfo',None,'option'),
    ('pinball.scene.gacha.exchange::GachaExchangeCharacterScene','getExchangeProducts','gachaExchangeProducts',None,'option'),
    ('pinball.scene.gacha.exchange::GachaExchangeEquipmentScene','getExchangeProducts','gachaExchangeProducts',None,'option'),
]
for _family in ['expertSingleEvent::ExpertSingleEventLogic','ranking::RankingEventLogic','raid::RaidEventLogic',
                'soloTimeAttack::SoloTimeAttackEventLogic','scoreAttack::ScoreAttackEventLogic','towerDungeon::TowerDungeonEventLogic']:
    ADDITIONAL_TARGETS.append(('pinball.common.data.quest.event.'+_family,'getRemainingTimeLabel','contentLabel',None,'option'))
for _cls in ['pinball.common.data.campaign.specialExchange::SpecialExchangeCampaignLogic',
             'pinball.common.data.campaign.multiSpecialExchange::MultiSpecialExchangeCampaignLogic']:
    ADDITIONAL_TARGETS += [(_cls,'isWithinExchangePeriod','campaignDecision','exchange','int'),
                          (_cls,'isWithinCampaignPeriod','contentDecision','visible','int')]
ADDITIONAL_TARGETS += [('pinball.common.data.campaign.startDashExchange::StartDashExchangeCampaignLogic',
                       'isWithinCampaignPeriod','contentDecision','visible','int'),
                      ('pinball.common.data.campaign.startDashExchange::StartDashExchangeCampaignLogic',
                       'isWithinPeriod','campaignDecision','exchange','int')]
for _cls,_getter in [
    ('pinball.common.data.campaign.specialExchange::SpecialExchangeCampaignLogic','get_exchangeEndTime'),
    ('pinball.common.data.campaign.multiSpecialExchange::MultiSpecialExchangeCampaignLogic','get_exchangeEndTime'),
    ('pinball.common.data.campaign.startDashExchange::StartDashExchangeCampaignLogic','get_periodEndTime')]:
    ADDITIONAL_TARGETS += [(_cls,'isOverExchangePeriod','campaignOver',None,'int'),
                          (_cls,_getter,'campaignEnd',None,'option')]
for _scene in ['base::EventQuestSelectBaseScene','carnival::CarnivalEventFolderSelectScene',
               'carnival.questSelect::CarnivalEventQuestSelectScene','expert.bossSelect::ExpertSingleEventBossSelectScene',
               'expert.questSelect::ExpertSingleEventQuestSelectScene','scoreAttack.questSelect::ScoreAttackEventQuestSelectScene',
               'soloTimeAttack.questSelect::SoloTimeAttackEventQuestSelectScene']:
    ADDITIONAL_TARGETS.append(('pinball.scene.event.'+_scene,'getDate','eventDate',None,'option'))
ADDITIONAL_TARGETS += [('pinball.common.data.quest.event.common::EventLogicBase','get_startTime','contentStart','enter','option')]
def view(a):return p.View(types.SimpleNamespace(abc=a),p.asm)
def compile_helper(work,sdk,java):
    out=work/'content-state.swc'
    cmd=[str(java),'-Dflexlib='+str(sdk/'frameworks'),'-Xmx512m','-jar',str(sdk/'lib/compc-cli.jar'),
        '+configname=air','-swf-version=44','-target-player=32.0','-debug=false',
        '-compiler.source-path='+str(HERE/'src'),'-include-classes=cn.content.ContentOperationsState','-output='+str(out)]
    process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    try:
        result,_=process.communicate(timeout=180);(work/'compile-bridge.log').write_bytes(result)
        if process.returncode:raise RuntimeError('bridge compiler failed: '+result.decode('utf8','replace')[-2500:])
    finally:
        if process.poll() is None:subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=15)
    return sc.helper_abc(out)

def android(work, registry, helper):
    raw=json.loads(registry.read_text(encoding='utf-8-sig'))['variants']['public']
    apk=Path(raw.get('apk') or raw.get('path') or raw.get('apk_path'))
    if sha(apk.read_bytes())!=raw['apk_sha256']:raise ValueError('Android input hash changed')
    with zipfile.ZipFile(apk) as z:swf=z.read('assets/worldflipper_android_release.swf')
    if sha(swf)!=raw['swf_sha256']:raise ValueError('Android SWF hash changed')
    source=work/'baseline-android.swf';source.write_bytes(swf)
    version,header,tags=sc.parts(source)
    candidates=[t for t in tags if t[3] and any(t[3].mn_name(i[0])=='pinball.common.data.gacha::GachaLogic' for i in t[3].instances)]
    if len(candidates)!=1:raise ValueError('cannot locate main ABC')
    tag=candidates[0];a=tag[3];old=copy.deepcopy(a);target=view(a)
    # Append the helper as another DoABC; no existing class gets a new field.
    pool=PoolEditor(a)
    def q(ns,name):
        for i,m in enumerate(a.multinames):
            if m[0]==7 and a.s(m[2])==name and a.namespaces[m[1]][0]==22 and a.ns_name(m[1])==ns and a.namespaces[m[1]][1]!=0:return i
        if ns=='':
            si=next((i for i,value in enumerate(a.strings) if i>0 and value==b''),None)
            if si is None:a.strings.append(b'');si=len(a.strings)-1
        else:si=pool.string(ns)
        a.namespaces.append((22,si));a.multinames.append((7,len(a.namespaces)-1,pool.string(name)));return len(a.multinames)-1
    state=q('cn.content','ContentOperationsState');option=q('haxe.ds','Option')
    edits=[]
    def body_label(class_name,method):
        matches=[label for label in target.by_label if label.startswith(class_name+'/') and label.rsplit('/',1)[-1].split('|')[0]==method]
        if len(matches)!=1:raise ValueError((class_name,method,matches))
        return matches[0]
    def graft(label,code,insertion=None,assembled=False):
        print('graft',label,flush=True)
        bi,=target.by_label[label];body=a.bodies[bi];before=copy.deepcopy(body)
        instructions=p.asm.decode(body[5])
        if insertion is None:insertion = 2 if len(instructions) >= 2 and instructions[0].op==0xd0 and instructions[1].op==0x30 else 0
        block=copy.deepcopy(code) if assembled else p.asm.assemble(code)
        bytecode,exceptions,decoded=p.asm.splice(body,insertion,block,p.asm.ENTER)
        body[5]=bytecode;body[6]=exceptions
        body[1]=max(body[1],12)
        p.check_body(body,a)
        if p.asm.unsplice(body[5],insertion,len(block))!=before[5]:raise ValueError('graft did not preserve original code')
        edits.append({'label':label,'body':bi,'method':body[0],'insertion':insertion,'instructions':len(block),'originalCodeSha256':sha(before[5]),'candidateCodeSha256':sha(body[5])})
    def call(name,action=None):
        if name=='gachaEnterGate':
            return [('getlex',state),('getlocal_0',),('getlocal_1',),('getlocal_2',),('getlocal_3',),('callproperty',q('',name),4)]
        return [('getlex',state),('getlocal_0',)]+([('pushstring',pool.string(action))] if action else [])+[('callproperty',q('',name),2 if action else 1)]
    def comparable_ends(label,expected):
        bi,=target.by_label[label];body=a.bodies[bi];before=copy.deepcopy(body)
        instructions=p.asm.decode(body[5])
        sites=[i+1 for i,ins in enumerate(instructions) if ins.op==0x46 and a.mn_name(ins.args[0]).rsplit('::',1)[-1]=='get_playableEndTime']
        assert len(sites)==expected,(label,sites)
        before_call=p.asm.assemble([('getlex',state),('swap',),('dup',)])
        after_call=p.asm.assemble([('callproperty',q('','nativeComparableEnd'),2),('coerce',option)])
        insertions=sorted([(site-1,before_call) for site in sites]+[(site,after_call) for site in sites])
        for site,block in reversed(insertions):
            previous=body[5]
            body[5],body[6],_=p.asm.splice(body,site,copy.deepcopy(block),p.asm.ENTER)
            assert p.asm.unsplice(body[5],site,len(block))==previous
        body[1]=max(body[1],12);p.check_body(body,a)
        edits.append({'label':label,'body':bi,'method':body[0],'insertion':sites[0]-1,'instructions':sum(len(block) for site,block in insertions),
            'originalInsertionSpans':[{'at':site,'instructions':len(block)} for site,block in insertions],
            'nativeComparableEndSites':len(sites),'originalCodeSha256':sha(before[5]),'candidateCodeSha256':sha(body[5])})
    # This ABC writer stores signed int pools as their unsigned wire encoding.
    # Compare against zero instead of appending a negative Python int.
    def decision(code):return code+[('dup',),('pushbyte',0),('iflt','OLD'),('convert_b',),('returnvalue',),('label','OLD'),('pop',)]
    def optional(code,result_type=option):
        cast=('coerce',result_type) if result_type else ('coerce_a',)
        return code+[('dup',),('pushnull',),('ifeq','OLD'),cast,('returnvalue',),('label','OLD'),('pop',)]
    def expression(label,start,end,code):
        # Preserve the native expression and all surrounding view updates. Only
        # a non-null controlled string bypasses the original formatter expression.
        block=p.asm.assemble(code+[('dup',),('pushnull',),('ifeq','OLD'),('coerce',q('','String')),
            ('jump','RESUME'),('label','OLD'),('pop',),('label','RESUME')])
        for ins in block:
            if ins.op==0x10 and ins.target==len(block):ins.target+=end-start
        graft(label,block,insertion=start,assembled=True)
        edits[-1]['nativeExpressionBypass']={'from':start,'resume':end,'nullPreservesOriginalExpression':True}
    g='pinball.common.data.gacha::GachaLogic'
    graft(body_label(g,'isWithinPeriod'),decision(call('gachaDecision','visible')))
    graft(body_label(g,'isAvailable'),call('gachaEnterGate')+[('pushbyte',0),('ifne','OLD'),('pushfalse',),('returnvalue',),('label','OLD')])
    for name,bridge in [('get_startTime','gachaStart'),('get_endTime','gachaEnd'),('getPeriod','gachaPeriod')]:graft(body_label(g,name),optional(call(bridge)))
    graft(body_label(g,'hasEndTime'),decision(call('gachaHasEnd')))
    event='pinball.common.data.quest.event.common::EventLogicBase'
    for name,action in [('isWithinPeriod','enter'),('isWithinBrowsablePeriod','visible'),('isWithinExchangeablePeriod','exchange')]:graft(body_label(event,name),decision(call('towerDecision',action)))
    graft(body_label(event,'get_playableEndTime'),optional(call('eventPlayableEnd')))
    graft(body_label(event,'get_exchangeableEndTime'),optional(call('contentEnd','exchange')))
    graft(body_label(event,'getRemainingTimeLabel'),optional(call('contentLabel')))
    constructor=[label for label in target.by_label if label == 'pinball.remote.common::ResponseData/<ctor>']
    if len(constructor)!=1:
        raise ValueError(('ResponseData ctor labels',[s for s in target.by_label if s.startswith('pinball.remote.common::ResponseData/')]))
    graft(constructor[0],[('getlex',state),('getlocal_1',),('callpropvoid',q('','captureResponse'),1)])
    # Keep the original crash/attention error notifications and RequestQueue route.
    # Only the reserved maintenance-kind message reuses the existing date-change dialog.
    remote_label=body_label('pinball.context::Logic','remoteCommonInput')
    remote_body=a.bodies[target.by_label[remote_label][0]]
    remote_ins=p.asm.decode(remote_body[5])
    assert remote_ins[11].op==0x4f and a.mn_name(remote_ins[11].args[0])=='saveServerError'
    assert remote_ins[15].op==0x4f and a.mn_name(remote_ins[15].args[0])=='notifyRemoteError'
    assert remote_ins[19].op==0xd7 and remote_ins[20].op==0xd3
    graft(remote_label,[('getlex',state),('getlocal_2',),('callproperty',q('','isContentReload'),1),('iffalse','OLD'),
        ('getlocal_0',),('getlocal_0',),('getproperty',q('','globalLogic')),('callproperty',q('','getTime'),0),('dup',),
        ('callpropvoid',q('','openDateChangedDialog'),2),('returnvoid',),('label','OLD')],insertion=20)
    graft(body_label('pinball.context.scene::LogicScene','sceneUpdate'), [('getlex',state),('getlocal_0',),('callpropvoid',q('','tick'),1)])
    graft(body_label('pinball.common.data.event::EventListLogic','getAllEventIds'), call('eventIds')+[('coerce',q('','Array')),('returnvalue',)])
    graft(body_label('pinball.common.data.gacha::GachaRepository','getGacha'), [('getlex',state),('getlocal_0',),('callpropvoid',q('','gachaCache'),1)])
    for method,action in [('isWithinPeriod','enter'),('isWithinViewablePeriod','visible')]:
        graft(body_label('pinball.common.data.quest.common::CommonQuestBase',method),decision(call('questDecision',action)))
    for method in ['getGachaRepository','getQuestRepository','getSpecialExchangeCampaignRepository','getShopProductRepository']:
        graft(body_label('pinball.context.global::GlobalLogic',method), [('getlex',state),('getlocal_0',),('callpropvoid',q('','invalidateGlobal'),1)])
    for cls,method,bridge,action,kind in ADDITIONAL_TARGETS:
        label=body_label(cls,method)
        if kind=='void':code=[('getlex',state),('getlocal_0',),('callpropvoid',q('',bridge),1)]
        elif kind=='handled':code=call(bridge)+[('iffalse','OLD'),('returnvoid',),('label','OLD')]
        elif kind=='int':code=decision(call(bridge,action))
        else:
            body_index,=target.by_label[label]
            result_type=a.methods[a.bodies[body_index][0]][0]
            code=optional(call(bridge,action),result_type)
        graft(label,code)
    for method in ['getTime','getOptionTime']:
        graft(body_label('pinball.context.global::GlobalLogic',method), [('getlex',state),('getlocal_0',),('callpropvoid',q('','syncGlobalTime'),1)])
    for method,action in [('startBoxGachaExecRemote','enter'),('startBoxGachaResetRemote','enter'),('startBoxGachaCloseRemote','claim')]:
        graft(body_label('pinball.scene.boxGacha::BoxGachaScene',method), [('getlex',state),('getlocal_0',),('pushstring',pool.string(action)),('callproperty',q('','boxActionGate'),2),('pushbyte',0),('ifne','OLD'),('returnvoid',),('label','OLD')])
    graft(body_label('pinball.scene.boxGacha::BoxGachaView','setupPeriod'), [('getlex',state),('getlocal_0',),('callproperty',q('','updateBoxPeriod'),1),('iffalse','OLD'),('returnvoid',),('label','OLD')])
    # Date panels accept an optional date config; concrete-end sentinels are an
    # accessor contract, not calendar dates to render as a far-future year.
    template='pinball.ui.component.template::QuestLikeSceneTemplateView/<ctor>'
    graft(template,[('getlex',state),('getlocal_2',),('callpropvoid',q('','sanitizeDateConfig'),1)])
    start_dash=body_label('pinball.scene.campaign.startDashExchange::StartDashExchangeCampaignView','refresh')
    start_rows=target.normalized(target.by_label[start_dash][0])[0]
    assert start_rows[88][0]==0xd3 and start_rows[133][0]==0x4f and 'set_text' in str(start_rows[133]),'StartDash date expression moved'
    expression(start_dash,88,133,[('getlex',state),('getlocal_0',),('getlocal_1',),('getlocal_3',),
        ('callproperty',q('','startDashDateText'),3)])
    multi=body_label('pinball.scene.campaign.multiSpecialExchange.exchange::MultiSpecialExchangeCampaignExchangeView','refresh')
    multi_rows=target.normalized(target.by_label[multi][0])[0]
    assert multi_rows[85][0]==0x5e and multi_rows[106][0]==0x4f and 'set_text' in str(multi_rows[106]),'Multi exchange date expression moved'
    expression(multi,85,106,[('getlex',state),('getlocal_1',),('callproperty',q('','campaignExchangeText'),1)])
    for method,count in [('multipleButtonHandler',6),('goToLink',1)]:
        comparable_ends(body_label('pinball.scene.littleAssistant::LittleAssistantScene',method),count)
    # Materialize AVM2 label opcodes at every relocated branch/switch destination.
    # Haxe baseline forward/dead branches may target ordinary instructions or code end.
    # Added labels are no-ops; insertion proof retains every original edge and instruction.
    original_view=view(old)
    final_view=view(a)
    for edit in edits:
        body=a.bodies[edit['body']]
        instructions=p.asm.decode(body[5])
        targets=set()
        for ins in instructions:
            if ins.target is not None: targets.add(ins.target)
            if ins.cases is not None: targets.update([ins.default]+ins.cases)
        origins=list(range(len(p.asm.decode(old.bodies[edit['body']][5]))))
        for span in reversed(edit.get('originalInsertionSpans',[{'at':edit['insertion'],'instructions':edit['instructions']}])):
            origins[span['at']:span['at']]=[None]*span['instructions']
        missing=[index for index in targets if index==len(instructions) or instructions[index].op!=0x09]
        for index in sorted(missing,reverse=True):
            body[5],body[6],_=p.asm.splice(body,index,[p.asm.Instruction(0x09)],p.asm.ENTER)
            origins[index:index]=[None]
        p.check_body(body,a)
        final_instructions=p.asm.decode(body[5])
        for ins in final_instructions:
            for index in ([ins.target] if ins.target is not None else [])+([ins.default]+ins.cases if ins.cases is not None else []):
                if index>=len(final_instructions) or final_instructions[index].op!=0x09:raise ValueError(('missing physical target label',edit['label'],index))
        edit['branchTargetLabelInsertions']=len(missing)
        spans=[];at=0;source_at=0
        while at<len(origins):
            if origins[at] is None:
                begin=at
                while at<len(origins) and origins[at] is None:at+=1
                spans.append({'at':source_at,'instructions':at-begin})
            else:
                assert origins[at]==source_at
                source_at+=1;at+=1
        try:edit['originalInstructionCfgInsertionProof']=p.insertion_proof(original_view.normalized(edit['body']),final_view.normalized(edit['body']),spans)
        except Exception as error:raise ValueError(('insertion proof',edit['label'],spans)) from error
        edit['candidateCodeSha256']=sha(body[5])
    # Preserve original action dates only inside an unmanaged action's native
    # range expression. Other direct start getters retain their operations gate.
    from build_exchange_repair import repair_native_starts
    for repair in repair_native_starts(a,target,q,state):
        edit,=[entry for entry in edits if entry['body']==repair['body']]
        edit['nativeFallbackStartRepair']=repair
        edit['candidateCodeSha256']=repair['candidateCodeSha256']
    changed={row['body'] for row in edits}
    for i,b in enumerate(old.bodies):
        if i not in changed and p.freeze(b)!=p.freeze(a.bodies[i]):raise ValueError(('unrelated body changed',i))
    for field in ['instances','classes','methods','scripts','metadata']:
        if p.freeze(getattr(old,field))!=p.freeze(getattr(a,field)):raise ValueError(('old layout changed',field))
    if any(n<0 for n in a.ints):raise ValueError('negative int pool must use unsigned ABC wire encoding')
    raw=sc.serialize(a,tag[4]);tag[1]=struct.pack('<HI',(82<<6)|63,len(tag[2])+len(raw))+tag[2]+raw
    payload=struct.pack('<I',1)+b'content_operations\0'+helper.serialize()
    extra=struct.pack('<HI',(82<<6)|63,len(payload))+payload
    main_index=tags.index(tag)
    tagbytes=[t[1] for t in tags];tagbytes.insert(main_index,extra)
    body=header+b''.join(tagbytes);output=work/'content-operations-android.swf'
    output.write_bytes(b'CWS'+bytes([version])+struct.pack('<I',len(body)+8)+zlib.compress(body))
    result={'sourceSha256':sha((HERE/'src/cn/content/ContentOperationsState.as').read_bytes()),'inputSha256':sha(swf),'outputSha256':sha(output.read_bytes()),'edits':edits,
        'unrelatedOriginalBodiesUnchanged':True,'existingClassLayoutsUnchanged':True,
        'scope':['login snapshot with local clock/cache/expiry maintenance','filter native event routes without catalog injection','gacha controls/cache with concrete native end contracts',
                 'exact quest/mission scope gates','operator-selected native current pass/date label','active/pass/collect mission periods',
                 'box/gacha periods preserving original policy','individual shop and parent controls','special exchange global periods',
                 'reserved operations reload message through original date-change dialog and title callback'],
        'notYetConnected':['unsupported page families','all resource/device acceptance','iOS integration'],
        'packaged':False,'deviceTested':False}
    (work/'android-bridge-report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print('Android grafted methods',len(edits))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--sdk',type=Path,required=True)
    parser.add_argument('--java',type=Path,required=True)
    args=parser.parse_args();args.work.mkdir(parents=True,exist_ok=True)
    helper=compile_helper(args.work,args.sdk,args.java)
    helper_before=copy.deepcopy(helper);helper_view=view(helper);before_view=view(helper_before)
    label_proofs=[]
    for bi,body in enumerate(helper.bodies):
        instructions=p.asm.decode(body[5]);targets=set()
        for ins in instructions:
            if ins.target is not None:targets.add(ins.target)
            if ins.cases is not None:targets.update([ins.default]+ins.cases)
        missing=[index for index in targets if index==len(instructions) or instructions[index].op!=0x09]
        for index in sorted(missing,reverse=True):
            body[5],body[6],_=p.asm.splice(body,index,[p.asm.Instruction(0x09)],p.asm.ENTER)
        p.check_body(body,helper)
        proof=p.insertion_proof(before_view.normalized(bi),helper_view.normalized(bi))
        label_proofs.append({'body':bi,'labels':len(missing),'insertionProof':proof})
    (args.work/'helper-label-proof.json').write_text(json.dumps(label_proofs,indent=2),encoding='utf-8')
    (args.work/'production-helper.abc').write_bytes(helper.serialize())
    android(args.work,HERE.parent/'android-accepted.json',helper)
if __name__=='__main__':main()
