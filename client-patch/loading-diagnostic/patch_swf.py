"""Insertion-only loading checkpoints plus a measured wrapper of the existing GC callback."""
import copy, json, struct, sys, zlib
from types import SimpleNamespace
from common import *

def patch(source,helper,output):
    assert sha(source.read_bytes())==SWF_SHA
    version,header,tags=s.parts(source)
    abcs=[t for t in tags if t[0]==82]
    assert len(abcs)==292 and sum(len(t[3].bodies) for t in abcs)==96543
    main=abcs[291];a=main[3];before=copy.deepcopy(a)
    assert a.serialize()==main[4]
    v=s.m.View(SimpleNamespace(abc=a),s.m.asm);pool=s.PoolEditor(a)
    def q(ns,name):
        matching=[i for i in range(1,len(a.multinames)) if v.mn(i)==(7,(22,ns),name)]
        if matching:return matching[0]
        spaces=[i for i,n in enumerate(a.namespaces) if i and n[0]==22 and n[1]!=0 and a.strings[n[1]]==ns.encode()]
        if spaces:space=spaces[0]
        else:
            text=pool.string(ns)
            if text==0:a.strings.append(b'');text=len(a.strings)-1
            a.namespaces.append((22,text));space=len(a.namespaces)-1
        a.multinames.append((7,space,pool.string(name)));return len(a.multinames)-1
    helper_q=q('cn.diagnostics','LoadingTrace')
    def call(name,*args):
        code=[('getlex',helper_q)]
        for arg in args:
            if isinstance(arg,list):code+=arg
            elif arg is None:code.append(('pushnull',))
            else:code.append(('pushstring',pool.string(arg)))
        code.append(('callpropvoid',q('',name),len(args)))
        return s.m.asm.assemble(code)
    self_=[('getlocal_0',)];arg1=[('getlocal_1',)]
    hooks={};meanings={}
    def add(bi,at,block,label):
        hooks.setdefault(bi,[]).append((at,block,s.m.asm.ENTER));meanings.setdefault(bi,[]).append({'at':at,'label':label})
    def index(label):
        assert len(v.by_label[label])==1,label
        return v.by_label[label][0]
    def entry(label,block,meaning):
        bi=index(label);rows=s.m.asm.decode(a.bodies[bi][5])
        if rows[0].op==0xd0 and rows[1].op==0x30:at=2
        else:
            # These verified static functions use their captured scope without a local pushscope.
            assert bi in {51008,5209,5259,5263,5264,15140,60835} and '$/' in label
            assert a.bodies[bi][3]==a.bodies[bi][4]
            at=0
        add(bi,at,block,meaning);return bi
    def around(label,phase,detail=None):
        bi=entry(label,call('mark',phase,'begin',self_,detail),phase+' begin')
        for at,ins in enumerate(s.m.asm.decode(a.bodies[bi][5])):
            if ins.op in (0x47,0x48):add(bi,at,call('mark',phase,'end',self_,detail),phase+' normal return')
    title=v.labels[a.bodies[82509][0]]
    assert title.startswith('pinball.scene.title::TitleView/')
    entry(title,call('install',[('getlex',q('flash','Lib')),('getproperty',q('','current'))]),'title log entry')
    entry('pinball.scene.title::TitleScene/disposeTitleScene|1',call('hideEntry'),'hide diagnostic button when leaving title')
    entry('pinball.loading.battle::MultiQuestStartLoadingTask/run|1',call('begin',self_),'start persisted loading session')
    for label,phase in [
        ('pinball.loading.battle::MultiQuestStartLoadingTask/remoteFinishedHandler|1','remote.apply'),
        ('pinball.loading.battle::MultiQuestStartLoadingTask/socketConnectedHandler|1','socket.ready'),
        ('pinball.asset.builder::BattleAssetPathCollectionBuilder/addMultiQuest|1','party.resources'),
        ('pinball.loading.battle::BattleStartProductionViewService/prepare|1','atlas.prepare'),
        ('pinball.loading.battle::BattleStartProductionViewService/pack|1','atlas.collect'),
        ('packing.core::MaxRectsPacker/pack|1','rect.pack'),
        ('packing.texture.starling::StarlingTextureAtlasFactory/initialize|1','atlas.allocate'),
        ('packing.texture.starling::StarlingTextureAtlasFactory/createTextureAtlas|1','atlas.draw'),
        ('pinball.loading.local::LocalLoading/leadingLogicAssetCompleteHandler|1','local.leading.ready'),
        ('pinball.loading.local::LocalLoading/followingLogicAssetCompleteHandler|1','local.following.ready'),
        ('pinball.loading.local::LocalLoading/completeHandler|1','local.complete'),
        ('pinball.scene.loading::LoadingSceneBase/loadedHandler|1','scene.assets.apply'),
        ('pinball.scene.loading::LoadingSceneBase/gotoNextScene|1','scene.transition'),
        ('pinball.scene.battle::BattleScene/run|1','battle.scene.run'),
        ('pinball.scene.battle.battle.hud::HudMemberStatus/run|1','hud.run'),
        ('pinball.scene.battle.battle::BothBossTool$/mapBoss|1','boss.map'),
        ('pinball.scene.battle.battle::BothBossTool$/refreshRoundOfKind|1','boss.round'),
        ('pinball.context.reproduce::LogicStatus/resetAssets|1','asset.groups'),
        ('pinball.asset::AssetGroupResolver$/resolveAssetGroups|1','asset.groups.resolve'),
        ('pinball.asset::AssetResolver$/resolve|1','asset.resolve'),
        ('pinball.asset::AssetResolver$/dispatchLeadingLogicAssetLoaded|1','local.logic.leading.apply'),
        ('pinball.asset::AssetResolver$/dispatchFollowingLogicAssetLoaded|1','local.logic.following.apply'),
        ('pinball.scene.loading::LoadingSceneBase/startNextSceneAssetLoadWithDetail|1','asset.start'),
        ('pinball.context.scene::LogicScene/changeSceneWithDetail|1','scene.change'),
        ('pinball.scene.battle::BattleScene/preparation|1','battle.scene.prepare'),
        ('pinball.scene.battle.battle::Battle/preparation|1','battle.prepare'),
        ('pinball.scene.battle.state::BattleScenePlayingStateImpl/run|1','battle.playing.start'),
        ('pinball.common.data.ability.summary::AbilitySummarizer$/summaryAbilities|1','abilities.summary'),
        ('pinball.common.data.party::BattlePartyLogic/getUnitedCharacters|1','party.calculate'),
        ('pinball.common.data.character::BattleCharacterLogic/getAvailableAbilities|1','abilities.available'),
        ('pinball.scene.battle.battle.terrain::TerrainParser$/parse|1','terrain.parse')]:around(label,phase)
    around('pinball.loading.battle::BattleStartProductionViewService/setupTextureAtlas|1','atlas.layer',arg1)
    around('pinball.loading.local::LocalLoading/startChild|1','local.child',arg1)
    # Keep the original callback count and timing. Only its callable is wrapped to observe System.gc().
    gc_body=index('pinball.loading.local::LocalLoading/startChild|1')
    rows=s.m.asm.decode(a.bodies[gc_body][5])
    assert rows[19].op==0x60 and v.mn(rows[19].args[0])==(7,(22,'flash.system'),'System')
    assert rows[20].op==0x66 and v.mn(rows[20].args[0])==(7,(22,''),'gc')
    rows[19].args[0]=helper_q;rows[20].args[0]=q('','collectGarbage')
    a.bodies[gc_body][5]=s.m.asm.encode(rows)[0]
    gc_wrapped=copy.deepcopy(a.bodies[gc_body])
    finish=index('pinball.scene.battle.state::BattleScenePlayingStateImpl/update|1')
    for at,ins in enumerate(s.m.asm.decode(a.bodies[finish][5])):
        if ins.op in (0x47,0x48):add(finish,at,call('firstFrame'),'first successful playing update; later frames are a guarded no-op')
    entry('pinball.scene.battle::BattleScene/leaveHandler|1',call('cancel'),'classify early scene exit separately')
    changes=[]
    for bi,insertions in sorted(hooks.items()):
        body=a.bodies[bi];original=body[5];prior=v.normalized(bi);insertions.sort(key=lambda x:x[0])
        code,exceptions,instructions,placed=s.m.asm.splice_many(body,insertions)
        assert s.m.asm.unsplice_many(code,placed)==original
        body[5]=code;body[6]=exceptions
        _,offsets=s.m.asm.encode(instructions);positions={p:i for i,p in enumerate(offsets)}
        stack,scope,_=s.m.asm.simulate(instructions,body[3],a.multinames,[positions[e[2]] for e in exceptions])
        body[1]=max(body[1],stack);assert scope<=body[4]
        proof=s.m.insertion_proof(prior,v.normalized(bi),[{'at':at,'instructions':len(block)} for at,block,_ in insertions])
        check=s.m.check_body(body,a)
        changes.append({'body':bi,'label':v.labels[body[0]],'before_sha256':sha(before.bodies[bi][5]),'after_sha256':sha(body[5]),
                        'hooks':meanings[bi],'placed':placed,'insertion_proof':proof,'check':check})
    assert not any(n[0]==22 and n[1]==0 for n in a.namespaces[len(before.namespaces):])
    for bi,body in enumerate(a.bodies):
        if bi not in hooks:assert s.m.freeze(body)==s.m.freeze(before.bodies[bi]),bi
    for name in ('methods','metadata','instances','classes','scripts'):
        assert s.m.freeze(getattr(a,name))==s.m.freeze(getattr(before,name)),name
    for name in ('ints','uints','doubles','strings','namespaces','ns_sets','multinames'):
        old=getattr(before,name);assert s.m.freeze(getattr(a,name)[:len(old)])==s.m.freeze(old),name
    extra=s.helper_abc(helper)
    assert len(extra.instances)==1 and extra.mn_name(extra.instances[0][0])=='cn.diagnostics::LoadingTrace'
    for body in extra.bodies:s.m.check_body(body,extra)
    payload=main[2]+a.serialize();main[1]=struct.pack('<HI',(82<<6)|63,len(payload))+payload
    payload=struct.pack('<I',1)+b'cn.diagnostics.LoadingTrace\0'+extra.serialize()
    extra_tag=struct.pack('<HI',(82<<6)|63,len(payload))+payload
    raw=header+b''.join((extra_tag if row is main else b'')+row[1] for row in tags)
    output.write_bytes(b'CWS'+bytes([version])+struct.pack('<I',len(raw)+8)+zlib.compress(raw))
    result={'status':'static_verified_diagnostic_candidate','input_swf_sha256':SWF_SHA,'output_swf_sha256':sha(output.read_bytes()),
            'main_abc_index':292,'original_method_bodies':96543,'added_helper_bodies':len(extra.bodies),
            'helper_swc_sha256':sha(helper.read_bytes()),'helper_abc_sha256':sha(extra.serialize()),
            'helper_source_sha256':sha((HERE/'src/cn/diagnostics/LoadingTrace.as').read_bytes()),
            'gc_callback_body':gc_body,'gc_wrapper_instruction_indices':[19,20],
            'changed_bodies':[c['body'] for c in changes],'changes':changes,
            'old_fields_and_method_signatures_preserved':True,'all_other_old_bodies_preserved':True,'device_tested':False}
    dump(WORK/'swf-report.json',result)
    return result

if __name__=='__main__':
    r=patch(WORK/'input.swf',WORK/'loading-trace.swc',WORK/'diagnostic.swf')
    print(json.dumps({k:r[k] for k in ('changed_bodies','added_helper_bodies','output_swf_sha256')}))
