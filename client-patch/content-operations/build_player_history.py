"""Bounded R9 PlayerHistory permanence and truthful unknown-date rendering.

Append an independent helper; preserve every existing tag except seven named
main-ABC bodies. No package, signing, CDN, registry, or server writes.
"""
import argparse, copy, hashlib, json, struct, subprocess, sys, zipfile, zlib
from pathlib import Path
sys.dont_write_bytecode = True
import build_bridge as b
from build_exchange_repair import qname, physical_labels

R9_SWF = '606cd2dc5c85953f0f7125511cb3a6bbc0284752339e45887ee2d8ea14923ca8'
HELPER = '''package cn.profile {
import flash.utils.getDefinitionByName;
public final class PlayerHistoryState {
 public static function permanent(v:Object):Boolean {
  return v!=null && v.id===1 && v.values!=null && v.values.string_id==="player_history";
 }
 public static function dates(topic:Object, original:Array):Array {
  if(original==null || topic==null || topic.sourceKind==null || topic.sourceKind.index!==1)return original;
  var kind:int=int(topic.sourceKind.params[0].index);
  if([0,2,3,4,7,8,26].indexOf(kind)<0)return original;
  var raw:Object=topic.getValues(), flags:Object=raw.int_values;
  var values:Array=flags!=null && flags.index===0 ? flags.params[0] as Array : null;
  var changed:Array=null;
  for(var i:int=0;i<original.length;i++) {
   var date:Object=original[i], flag:Object=values!=null && i<values.length ? values[i] : null;
   var achieved:Boolean=flag!=null && flag.index===0 && flag.params[0]===1;
   if(date!=null && date.index===1 && (achieved || kind===0)) {
    if(changed==null)changed=original.concat();
    var option:Class=getDefinitionByName("haxe.ds.Option") as Class;
    changed[i]=option.Some("");
   }
  }
  return changed==null ? original : changed;
 }
 public static function period(topic:Object, original:String):String {
  return topic!=null && topic.id===1 ? "常驻资料" : original;
 }
 public static function share(card:Object, original:String):String {
  return card!=null && card.id===1 ? "我的世界弹射物语资料卡\\n一起回顾冒险旅程！\\n#世界弹射物语 #我的资料卡" : original;
 }
} }
'''

def sha(raw): return hashlib.sha256(raw).hexdigest()

def build(work, apk, sdk, java):
    work.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apk) as z: raw = z.read('assets/worldflipper_android_release.swf')
    if sha(raw) != R9_SWF: raise ValueError('requires exact R9 SWF')
    source = work/'R9-input.swf'; source.write_bytes(raw)
    src = work/'profile-src/cn/profile/PlayerHistoryState.as'
    src.parent.mkdir(parents=True, exist_ok=True); src.write_text(HELPER, encoding='utf8')
    swc = work/'player-history-state.swc'
    cmd = [str(java), '-Dflexlib='+str(sdk/'frameworks'), '-jar', str(sdk/'lib/compc-cli.jar'),
           '+configname=air', '-swf-version=44', '-target-player=32.0', '-compiler.float=false',
           '-debug=false', '-compiler.source-path='+str(work/'profile-src'),
           '-include-classes=cn.profile.PlayerHistoryState', '-output='+str(swc)]
    r = subprocess.run(cmd, capture_output=True, timeout=120)
    (work/'compile-profile.log').write_bytes(r.stdout+r.stderr)
    if r.returncode: raise RuntimeError('profile helper compile failed')
    helper = b.sc.helper_abc(swc)
    for body in helper.bodies: physical_labels(helper, body)
    (work/'player-history-helper.abc').write_bytes(helper.serialize())
    version, header, tags = b.sc.parts(source)
    originals = [bytes(t[1]) for t in tags]
    tag, = [t for t in tags if t[3] and any(t[3].mn_name(i[0])=='pinball.context.remote::RequestQueue' for i in t[3].instances)]
    a = tag[3]; old = copy.deepcopy(a); target = b.view(a); ov = b.view(old)
    pool = b.PoolEditor(a); q = lambda ns,n:qname(a,pool,ns,n)
    state = q('cn.profile','PlayerHistoryState')
    # String pool slot zero is a sentinel, never a valid pushstring operand.
    empty = next((i for i,s in enumerate(a.strings) if i>0 and s==b''),None)
    if empty is None:a.strings.append(b'');empty=len(a.strings)-1
    edits = []

    def graft(label, code, at=2):
        index, = target.by_label[label]; body = a.bodies[index]; before = copy.deepcopy(body)
        block = b.p.asm.assemble(code)
        body[5],body[6],_ = b.p.asm.splice(body,at,block,b.p.asm.ENTER)
        if b.p.asm.unsplice(body[5],at,len(block)) != before[5]: raise ValueError(('inverse differs',label))
        body[1] += 4
        origins = list(range(len(b.p.asm.decode(before[5])))); origins[at:at] = [None]*len(block)
        rows = b.p.asm.decode(body[5]); destinations = set()
        for x in rows:
            if x.target is not None: destinations.add(x.target)
            if x.cases is not None: destinations.update([x.default]+x.cases)
        missing = [i for i in destinations if i==len(rows) or rows[i].op!=0x09]
        for i in sorted(missing,reverse=True):
            body[5],body[6],_ = b.p.asm.splice(body,i,[b.p.asm.Instruction(0x09)],b.p.asm.ENTER)
            origins[i:i] = [None]
        physical_labels(a,body)
        spans=[];pos=0;source_at=0
        while pos<len(origins):
            if origins[pos] is None:
                begin=pos
                while pos<len(origins) and origins[pos] is None:pos+=1
                spans.append({'at':source_at,'instructions':pos-begin})
            else:
                assert origins[pos]==source_at;source_at+=1;pos+=1
        proof = b.p.insertion_proof(ov.normalized(index), b.view(a).normalized(index), spans)
        # Reverse all inserted instructions including materialized target labels.
        candidate_rows=b.p.asm.decode(body[5]);kept=[i for i,o in enumerate(origins) if o is not None]
        assert len(kept)==len(b.p.asm.decode(before[5]))
        edits.append({'label':label,'body':index,'method':body[0],
            'inputCodeSha256':sha(before[5]),'candidateCodeSha256':sha(body[5]),
            'insertionProof':proof,'inverseOriginalCodeExact':True,
            'branchTargetsPhysical':True,'backwardTargetsPhysical':True,
            'physicalLabelsAdded':len(missing)})

    base='pinball.common.data.player_history::PlayerHistoryLogic/'
    graft(base+'isWithinPeriod|1',[('getlex',state),('getlocal_0',),('callproperty',q('','permanent'),1),
        ('iffalse','OLD'),('pushtrue',),('returnvalue',),('label','OLD')])
    logic='pinball.scene.playerHistory.card::PlayerHistoryCardTopicLogic/getDateValues|1'
    rows=b.p.asm.decode(a.bodies[target.by_label[logic][0]][5]);returns=[i for i,x in enumerate(rows) if x.op==0x48]
    assert len(returns)==1,returns
    graft(logic,[('getlex',state),('swap',),('getlocal_0',),('swap',),('callproperty',q('','dates'),2),('coerce',q('','Array'))],returns[0])
    view='pinball.scene.playerHistory.card::PlayerHistoryCardTopicView/'
    graft(view+'getDateString|1',[('getlocal_1',),('pushstring',empty),('ifne','OLD'),
        ('pushstring',pool.string('日期未知')),('returnvalue',),('label','OLD')])

    def text_consumer(label,key,code):
        rows=b.p.asm.decode(a.bodies[target.by_label[label][0]][5])
        sites=[i for i,x in enumerate(rows) if x.op==0x2c and a.s(x.args[0])==key]
        assert len(sites)==1,(label,key,sites)
        calls=[i for i in range(sites[0]+1,len(rows)) if rows[i].op==0x46 and a.mn_name(rows[i].args[0]) in ('getUiString','getUiStringWithContext')]
        assert calls,(label,key)
        graft(label,code,calls[0]+1)

    text_consumer('pinball.scene.playerProfile::PlayerProfileView/drawPlayerInfoForPlayerHistory|1','player_history_period_text',
        [('getlex',state),('swap',),('getlocal',11),('swap',),('callproperty',q('','period'),2)])
    text_consumer('pinball.scene.playerHistory.card::PlayerHistoryCardLogic/createShareText|1','player_history_share_text',
        [('getlex',state),('swap',),('getlocal_0',),('swap',),('callproperty',q('','share'),2)])
    for method,key,text in [
        ('complete_mana_board_2','player_history_topic_complete_mana_board_2_title','已完成第二枚玛纳板强化的角色'),
        ('defeat_expert_single_boss','player_history_topic_defeat_expert_single_boss_title','已通关单人挑战讨伐战斗地狱级领主')]:
        text_consumer(view+method+'|1',key,[('pop',),('pushstring',pool.string(text))])

    changed={e['body'] for e in edits}
    assert len(changed)==7
    for index in changed:
        for ins in b.p.asm.decode(a.bodies[index][5]):
            if ins.op==0x2c:assert ins.args[0]>0,('pushstring sentinel',index)
    for i,body in enumerate(old.bodies):
        if i not in changed: assert b.p.freeze(body)==b.p.freeze(a.bodies[i]),i
    abi={field:b.p.freeze(getattr(old,field))==b.p.freeze(getattr(a,field)) for field in ['methods','instances','classes','scripts','metadata']}
    assert all(abi.values())
    pools={field:b.p.freeze(getattr(old,field))==b.p.freeze(getattr(a,field)[:len(getattr(old,field))]) for field in ['strings','ints','uints','doubles','namespaces','ns_sets','multinames']}
    assert all(pools.values())
    data=tag[2]+b.sc.serialize(a,tag[4]);tag[1]=struct.pack('<HI',(82<<6)|63,len(data))+data
    payload=struct.pack('<I',1)+b'player_history_permanent\0'+helper.serialize()
    extra=struct.pack('<HI',(82<<6)|63,len(payload))+payload
    old_index=tags.index(tag);tagbytes=[t[1] for t in tags];tagbytes.insert(old_index,extra)
    raw_out=header+b''.join(tagbytes)
    output=work/'content-operations-android.swf'
    output.write_bytes(b'CWS'+bytes([version])+struct.pack('<I',len(raw_out)+8)+zlib.compress(raw_out))
    final=b.sc.parts(output)[2]
    assert len(final)==len(tags)+1
    for i,t in enumerate(tags):
        fi=i+(i>=old_index)
        if i!=old_index:assert bytes(final[fi][1])==originals[i],i
    fm=final[old_index+1][3];fh=final[old_index][3]
    assert fm.serialize()==a.serialize() and fh.serialize()==helper.serialize()
    # Keep the selected existing complete helper and its compiler library for mature regressions.
    old_helper,=[t[3] for t in tags if t[3] and any(t[3].mn_name(i[0])=='cn.content::ContentOperationsState' for i in t[3].instances)]
    (work/'production-helper.abc').write_bytes(old_helper.serialize())
    record={'schema':'player-history-permanent/v1','inputApk':str(apk),'inputSwfSha256':sha(raw),
        'candidateSwfSha256':sha(output.read_bytes()),'edits':edits,'changedNativeBodies':7,
        'nonTargetMethodsPreserved':True,'nativeAbiPreserved':True,'abi':abi,'appendOnlyPools':pools,
        'nonTargetTagsByteExact':True,'existingContentHelperAbcSha256':sha(old_helper.serialize()),
        'newProfileHelperAbcSha256':sha(helper.serialize()),'finalReadbackExact':True,
        'packaged':False,'deviceTested':False}
    (work/'cumulative-method-preservation.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in record.items() if k not in ['edits','abi','appendOnlyPools']},ensure_ascii=False))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['work','apk','sdk','java']:p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();build(args.work,args.apk,args.sdk,args.java)

if __name__=='__main__':main()
