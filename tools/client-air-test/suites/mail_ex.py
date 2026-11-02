"""Real mail EX snapshot/difference/callback/presentation algorithms; build only."""
from __future__ import annotations
from pathlib import Path
import json,subprocess,time,shutil,re
import abc_tools as abc
import common,flows

CASE_IDS=['mail-ex-single-duplicate','mail-ex-batch-same-character','mail-ex-batch-mixed-characters']
STEP_IDS=['mail-ex-single-zero','mail-ex-single-zero-retry','mail-ex-single-positive','mail-ex-single-positive-retry','mail-ex-single-new-identity']+[prefix+'-'+step for prefix in CASE_IDS[1:] for step in ['claim','retry','new-identity']]
CONTRACT_ID='mail-ex-difference-contract'
CONTRACT_STEPS=['mail-ex-diff-zero-positive','mail-ex-diff-existing-positive','mail-ex-diff-unchanged','mail-ex-diff-decreased','mail-ex-diff-omitted','mail-ex-diff-unrelated','mail-ex-diff-invalid-map']

def build(ctx,out:Path):
 out=abc.output_directory(ctx,out);out.mkdir(parents=True,exist_ok=True)
 shared=common.prepare_sources(ctx,out/'common');common_src=Path(shared['source_dir'])
 builder,source,sv,identity=abc.load_current();src=out/'src';src.mkdir(exist_ok=False)
 template_root=Path(ctx['tool_root'])/'templates/mail-ex'
 for p in template_root.rglob('*.as'):
  target=src/p.relative_to(template_root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
 master_path=template_root/'client-master-input.json';master=json.loads(master_path.read_text(encoding='utf-8'))
 harness=src/'MailExHarness.as';text=harness.read_text(encoding='utf-8')
 if text.count('__CLIENT_MASTER_JSON__')!=1:raise ValueError('Master fixture marker must be unique')
 harness.write_text(text.replace('__CLIENT_MASTER_JSON__',json.dumps(json.dumps(master,separators=(',',':')),ensure_ascii=True)),encoding='utf-8')
 selections=list(shared['selections']);extra=[]
 def declaration(owner,name,static=False,target_owner=None):
  label=flows._label(source,sv,owner,name);bi,=sv.by_label[label];mid=source.bodies[bi][0];info=source.methods[mid]
  typ=lambda t:source.mn_name(t).replace('::','.') if t else '*'
  options=len(info[4] or []);params=','.join('p'+str(i)+':'+typ(t)+('=undefined' if i>=len(info[1])-options else '') for i,t in enumerate(info[1]))
  target_owner=target_owner or owner
  if name=='<ctor>':decl='public function '+target_owner.rsplit('::',1)[-1]+'('+params+'){throw new Error("ungrafted constructor");}';target=target_owner+'/<ctor>'
  else:decl='public '+('static ' if static else '')+'function '+name+'('+params+'):'+typ(info[0])+'{throw new Error("ungrafted '+owner+'.'+name+'");}';target=target_owner+('$/' if static else '/')+name+'|1'
  spec=label if label==target else {'source':label,'target':target};selections.append(spec);extra.append(spec);return decl
 def source_text(owner,body,extra_decl=''):
  package,_,name=owner.rpartition('::');imports=''
  references=sorted(set(re.findall(r'(?<![\w.])(?:[a-z]\w*\.)+[A-Z]\w*',body+extra_decl)),key=len,reverse=True)
  for full in references:
   if full!=package+'.'+name:imports+='import '+full+';'
   body=re.sub(r'(?<![\w.])'+re.escape(full)+r'\b',full.rsplit('.',1)[-1],body)
   extra_decl=re.sub(r'(?<![\w.])'+re.escape(full)+r'\b',full.rsplit('.',1)[-1],extra_decl)
  return 'package '+package+' {'+imports+'public dynamic class '+name+extra_decl+' {'+body+'}}'
 def put(owner,fields,methods,static=False,extra_decl=''):
  package,_,name=owner.rpartition('::');body=fields+''.join(declaration(owner,n,static and n!='<ctor>') for n in methods)
  p=src/(package.replace('.','/')+'/'+name+'.as');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(source_text(owner,body,extra_decl),encoding='utf-8')
 put('pinball.common.data.exBoost::ExBoostItemAcquisitionRepository','public var tableData:pinball.master.runtime.MasterMap;public var logicAssets:pinball.asset.logic.ILogicAssetContainer;',['<ctor>','getOwnedExBoostItemMap','getExBoostItemIds','getExBoostItemCount','getExBoostItem'])
 put('pinball.common.data.exBoost::ExBoostRepository','', ['getIncreasedExBoostItems'])
 put('pinball.master.generated::ExBoostItemAcquisitionValues','public var item_id:int;public var item_count:int;',['<ctor>'])
 put('haxe.iterators::MapKeyValueIterator','public var map:haxe.IMap;public var keys:Object;',['<ctor>','next','hasNext'])
 put('pinball.scene.mailList::MailListScene','public var mailList:fixture.MailExMailList;',['getExBoostItemMap'])
 put('pinball.scene.characterGet::CharacterGetCharacterInfoTools','',['fromSingleCharacters','from'],True)
 put('pinball.common.data.mail::MailKind','public var tag:String;public var index:int;public var params:Array;public const __enum__:Boolean=true;public static const __isenum:Boolean=true;',['<ctor>','Character'],True)
 put('pinball.common.data.character.joinMovie::JoinMovieKind','public var tag:String;public var index:int;public var params:Array;public const __enum__:Boolean=true;public static const __isenum:Boolean=true;public static var NewEntry:JoinMovieKind=new JoinMovieKind("NewEntry",0,null);public static var Reentry:JoinMovieKind=new JoinMovieKind("Reentry",2,null);',['<ctor>','Duplicated'],True)
 owner='pinball.common.data.character::GeneralCharacterLogic'
 body='public var squadMemberSourceValues:Object;public function GeneralCharacterLogic(id:int=0,a:pinball.asset.logic.ILogicAssetContainer=undefined){if(!fixture.MailExAssets.characterRows.hasOwnProperty(String(id)))throw new Error("Missing selected native character row "+id);squadMemberSourceValues=fixture.MailExAssets.characterRows[String(id)];}'
 body+=''.join(declaration('pinball.common.data.battle.squadMember::CharacterBaseImpl',n,target_owner=owner) for n in ['get_rarity','get_element'])
 (src/'pinball/common/data/character/GeneralCharacterLogic.as').write_text(source_text(owner,body,' implements GeneralCharacterPeek'),encoding='utf-8')
 # Supplement only this build's generated common declarations, never shared files.
 peek=common_src/'pinball/common/data/player/PlayerPeek.as';peek.write_text('package pinball.common.data.player {public interface PlayerPeek {function getItemNumber(id:int):int;}}',encoding='utf-8')
 owned=common_src/'pinball/common/data/character/OwnedCharacterLogic.as';text=owned.read_text(encoding='utf-8');at=text.rfind('}}')
 if at<0:raise ValueError('OwnedCharacter shell terminator missing')
 owned.write_text(text[:at]+declaration('pinball.common.data.character::OwnedCharacterLogic','get_entryCount')+text[at:],encoding='utf-8')
 for owner,name in [('pinball.remote.mail.receive::MailReceiveRealRemote','successHandler'),('pinball.remote.mail.receiveAll::MailReceiveAllRealRemote','successHandler'),('pinball.remote.mail::MailRemoteInput','<ctor>'),('pinball.remote.mail::MailRemoteInput','ReceiveFinished'),('pinball.remote.mail::MailRemoteInput','ReceiveAllFinished'),('pinball.remote.mail::MailReceiveRemoteUtil','getCharacterIdAndCount'),('pinball.remote.mail::MailReceiveRemoteUtil','getjoinedCharacterIds')]:
  label=flows._label(source,sv,owner,name);selections.append(label);extra.append(label)
 includes=sorted(set(shared['includes']+[str(p.relative_to(src)).replace('\\','/').removesuffix('.as').replace('/','.') for p in src.rglob('*.as') if p.stem!='MailExHarness']))
 adaptation=['Generated PlayerPeek includes the actual getItemNumber interface signature only within this suite.','MasterMap and ILogicAssetContainer expose used native signatures; typed external data access records provide the captured client rows, not a new lookup algorithm.','GeneralCharacterLogic heavy asset constructor is fixture initialization; actual CharacterBaseImpl rarity/element getters are grafted under its owner with the original squadMemberSourceValues field.','Mail scene constructor/UI/list storage are fixture boundaries; actual complete getExBoostItemMap and CharacterGetCharacterInfoTools methods execute unchanged.','Common response capture, time, account storage, ANE and final visual presentation remain existing external recording boundaries.']
 flows._save(out/'source-manifest.json',{'identity':identity,'selections':selections,'extra_selections':extra,'includes':includes,'native_master_input_sha256':abc.sha(master_path.read_bytes()),'native_master_source':master['source'],'adaptations':adaptation,'sources':{str(p.relative_to(out)):abc.sha(p.read_bytes()) for root in (src,common_src) for p in root.rglob('*.as')}})
 sdk=Path(ctx['sdk']);command=[str(ctx['java']),'-Xmx1g','-Dflexlib='+str(sdk/'frameworks'),'-jar',str(sdk/'lib/mxmlc-cli.jar'),'+configname=air','-compiler.float=false','-swf-version=44','-target-player=32.0','-debug=true','-compress=false','-compiler.source-path='+str(src)+','+str(common_src),'-includes='+','.join(includes),'-output='+str(out/'template.swf'),str(harness)]
 started=time.perf_counter();run=subprocess.run(command,cwd=out,capture_output=True,timeout=120);(out/'compile.log').write_bytes(run.stdout+run.stderr)
 flows._save(out/'compile-receipt.json',{'command':command,'exit_code':run.returncode,'elapsed_ms':round((time.perf_counter()-started)*1000,3)})
 if run.returncode:raise RuntimeError('Mail EX compilation failed: '+str(out/'compile.log'))
 template=(out/'template.swf').read_bytes();units=list(abc.raw_units(template))
 if len(units)!=1:raise ValueError('Expected one carrier ABC')
 target=builder.abcfmt.ABC(units[0][1]);tv=abc.view(target)
 for spec in selections:
  label=spec if isinstance(spec,str) else spec.get('target',spec['source'])
  if label not in tv.by_label:raise ValueError('Required carrier target missing: '+label)
 mapping=abc.graft(target,source,selections);payload=abc.replace_abc(template,target);swf=out/'Harness.swf';swf.write_bytes(payload)
 parsed=builder.abcfmt.ABC(list(abc.raw_units(payload))[0][1]);proof=abc.verify_grafts(parsed,source,mapping);proof_path=out/'proof.json'
 flows._save(proof_path,{'suite':'mail-ex','identity':identity,'real_methods':proof,'execution_swf_sha256':abc.sha(payload),'native_master_input_sha256':abc.sha(master_path.read_bytes()),'native_master_source':master['source'],'adaptations':adaptation,'missing_required_methods':[],'required_case_ids':CASE_IDS+[CONTRACT_ID],'required_step_ids':STEP_IDS+CONTRACT_STEPS})
 application=out/'application.xml';application.write_text('<application xmlns="http://ns.adobe.com/air/application/51.2"><id>local.starpoint.clientair.mailex</id><versionNumber>1.0.0</versionNumber><filename>mail-ex</filename><initialWindow><content>Harness.swf</content><visible>false</visible></initialWindow></application>',encoding='utf-8')
 return {'application':application,'swf':swf,'proof':proof_path,'required_case_ids':CASE_IDS+[CONTRACT_ID],'required_step_ids':STEP_IDS+CONTRACT_STEPS}
