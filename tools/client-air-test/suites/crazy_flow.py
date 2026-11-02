"""Actual crazy-gacha callback, loading-scene, dialog and reload consumers."""
from __future__ import annotations
from pathlib import Path
import json,re,shutil,subprocess,time
import abc_tools as abc
import common,flows

EXTRA={
 'pinball.loading.gacha::GachaLoadingTaskBase':['createCharacterGachaResult','getShareImageData'],
 'pinball.loading.gacha::GachaLoadingTask':['remoteInput'],
 'pinball.dialog.gacha::GachaResultSaveDialog':['remoteInput','refreshList','setButtonEnabled'],
 'pinball.dialog.gacha::GachaResultSelectDialog':['remoteInput'],
 'pinball.scene.home::HomeScene':['startChangeCrazyGachaResultScene','generateGachaResult','createCharacterGachaResult'],
 'pinball.common.data.player::PlayerLogic':['applyGachaResult','applyGachaCampaignList','applyStarsGachaCampaignList','get_last_crazy_gacha_result_list','get_crazy_gacha_result_list'],
 'pinball.common.data.gacha::GachaDrawKindTools':['isFreeTenTimesCampaign'],
}
ENUMS={
 'pinball.common.data.gacha::GachaResultInfoEntryKind':[],
 'pinball.dialog.processing::CloseBehavior':[],
 'pinball.common.data.scene::SceneKind':['GachaBallMovie','GachaResult','Gacha'],
 'pinball.common.data.scene::ChangeSceneNextKind':['Scene'],
 'pinball.common.data.scene::ChangeSceneBackKind':['Add'],
}
STEP_IDS=['crazy-exec','crazy-exec-retry','crazy-load-after-exec','crazy-save','crazy-save-retry','crazy-load-after-save','crazy-select','crazy-select-retry','crazy-load-after-select']

def _owner(a,q):
 rows=[i for i,r in enumerate(a.instances) if a.mn_name(r[0])==q]
 if len(rows)!=1:raise ValueError('Required unique owner missing: '+q)
 return rows[0]

def _label(a,v,q,n):
 i=_owner(a,q)
 if n=='<cinit>':return v.labels[a.classes[i][0]]
 return flows._label(a,v,q,n)

def _declaration(a,v,q,n):
 label=_label(a,v,q,n);bi,=v.by_label[label];mid=a.bodies[bi][0];info=a.methods[mid]
 typ=lambda x:a.mn_name(x).replace('::','.') if x else '*'
 params=','.join('p'+str(i)+':'+typ(x) for i,x in enumerate(info[1]))
 if n=='<ctor>':return 'public function '+q.rsplit('::',1)[-1]+'('+params+'){}'
 return 'public '+('static ' if '$/' in label else '')+'function '+n+'('+params+'):'+typ(info[0])+'{throw new Error("ungrafted '+q+'.'+n+'");}'

def _put(root,q,body,base=''):
 package,name=q.split('::');references=sorted(set(re.findall(r'(?<![\w.])(?:[a-z]\w*\.)+[A-Z]\w*',body+base)),key=len,reverse=True)
 imports=''
 for full in references:
  imports+='import '+full+';';body=body.replace(full,full.rsplit('.',1)[-1]);base=base.replace(full,full.rsplit('.',1)[-1])
 path=root/(package.replace('.','/')+'/'+name+'.as');path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text('package '+package+' {'+imports+'public dynamic class '+name+base+' {'+body+'}}',encoding='utf-8')

def _enum(root,a,v,q,names,evidence):
 ci=_owner(a,q);body=[];constants={}
 # Haxe places enum constants in the owning script initializer; the class cinit
 # itself is returnvoid. Derive literal bootstrap data from the actual script,
 # rather than grafting that empty cinit over the carrier's initializers.
 if not names:
  scripts=[s[0] for s in a.scripts if any(a.mn_name(t.name)==q for t in s[1])]
  if len(scripts)!=1:raise ValueError('Enum owning script is not unique: '+q)
  script_body=a.bodies[abc.body_index(a,scripts[0])];code=abc.builder.asm.decode(script_body[5])
  for i,x in enumerate(code):
   if x.op!=0x68 or a.mn_name(x.args[0]).rsplit('::',1)[-1].startswith('__'):continue
   window=code[max(0,i-4):i]
   if len(window)==4 and window[0].op==0x2c and window[1].op in (0x24,0x25) and window[2].op==0x20 and window[3].op==0x4a and a.mn_name(window[3].args[0])==q and window[3].args[1]==3:
    constants[a.mn_name(x.args[0]).rsplit('::',1)[-1]]=(a.s(window[0].args[0]),window[1].args[0])
  evidence.append({'owner':q,'source_script_method':scripts[0],'source_script_code_sha256':abc.sha(script_body[5]),'constant_tag_index':constants,'class_cinit_is_returnvoid':a.bodies[abc.body_index(a,a.classes[ci][0])][5]==b'\x47','fixture_bootstrap_only':True,'real_enum_constructor_grafted':True})
 for prefix,traits in [('',a.instances[ci][6]),('static ',a.classes[ci][1])]:
  for t in traits:
   if t.data[0]!='slot':continue
   name=a.mn_name(t.name).rsplit('::',1)[-1];kind=a.mn_name(t.data[2]).replace('::','.') or '*'
   initial='=true' if name in ('__enum__','__isenum__') else ''
   if prefix and kind==q.replace('::','.') and not names:
    if name not in constants:raise ValueError('Enum constant not recovered from actual script: '+q+'.'+name)
    tag,index=constants[name];initial='=new '+q.rsplit('::',1)[-1]+'('+json.dumps(tag)+','+str(index)+',null)'
   body.append('public '+prefix+'var '+name+':'+kind+initial+';')
 body += [_declaration(a,v,q,'<ctor>')]+[_declaration(a,v,q,n) for n in names]
 _put(root,q,''.join(body))
 return [_label(a,v,q,'<ctor>')]+[_label(a,v,q,n) for n in names]

def _prepare(ctx,out):
 shared=common.prepare_sources(ctx,out/'common');src=out/'src';src.mkdir(parents=True,exist_ok=True)
 template_root=Path(ctx['tool_root'])/'templates/flows'
 for p in template_root.rglob('*.as'):
  if p.stem in ('FlowHarness','ExHarness'):continue
  target=src/p.relative_to(template_root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
 b,a,v,identity=abc.load_current()
 selected=list(shared['selections'])+[_label(a,v,r['owner'],r['name']) for r in json.loads((template_root/'selections.json').read_text(encoding='utf-8'))]
 methods=lambda q:''.join(_declaration(a,v,q,n) for n in EXTRA[q])
 _put(src,'pinball.loading.gacha::GachaLoadingTaskBase','public var globalLogic:pinball.context.global.GlobalLogic;'+methods('pinball.loading.gacha::GachaLoadingTaskBase'))
 _put(src,'pinball.loading.gacha::GachaLoadingTask','public var scene:pinball.scene.loading.ILoadingScene;public var id:int=100;public var drawKind:int=14;public var completeCalls:int=0;public var analyticsCalls:int=0;public function sendFoxAnalyticsEvent():void{analyticsCalls++;}public function complete():void{completeCalls++;}public function gotoGachaTop():void{throw new Error("error flow not exercised");}'+methods('pinball.loading.gacha::GachaLoadingTask'),' extends pinball.loading.gacha.GachaLoadingTaskBase')
 _put(src,'pinball.dialog.gacha::GachaResultSaveDialog','public var globalLogic:pinball.context.global.GlobalLogic;public var buttonCharacterGroup:pinball.ui.component.button.ButtonGroupLogic;public var viewOrder:pinball.dialog.gacha.GachaResultSaveDialogViewOrder;'+methods('pinball.dialog.gacha::GachaResultSaveDialog'))
 _put(src,'pinball.dialog.gacha::GachaResultSelectDialog','public var globalLogic:pinball.context.global.GlobalLogic;public var selectIndex:int=1;public var navigationCalls:int=0;public function tryGotoGachaTop():void{navigationCalls++;}'+methods('pinball.dialog.gacha::GachaResultSelectDialog'))
 _put(src,'pinball.scene.home::HomeScene','public var globalLogic:pinball.context.global.GlobalLogic;public var transitions:Array=[];public var nextStartupCalls:int=0;public function startNextStartupProcess():void{nextStartupCalls++;}public function changeSceneWithDetail(n:pinball.common.data.scene.ChangeSceneNextKind,b:pinball.common.data.scene.ChangeSceneBackKind):void{transitions.push({next:n,back:b});}'+methods('pinball.scene.home::HomeScene'))
 _put(src,'pinball.common.data.gacha::GachaDrawKindTools',methods('pinball.common.data.gacha::GachaDrawKindTools'))
 # These data access/navigation dependencies are deliberately records; target
 # candidate conversion, mutations, flags and branch selection stay production.
 _put(src,'pinball.context.global::GlobalLogic','''public var player:pinball.common.data.player.PlayerLogic;public var characterReads:Array=[];public var repository:pinball.common.data.gacha.GachaRepository=new pinball.common.data.gacha.GachaRepository();public function get_player():pinball.common.data.player.PlayerLogic{return player;}public function getPlayer():pinball.common.data.player.PlayerPeek{return player;}public function getGeneralCharacter(id:int):Object{characterReads.push(id);return {};}public function getGachaRepository():pinball.common.data.gacha.GachaRepository{return repository;}public function getTime():Number{return 0;}public function getExBoostRepository():pinball.common.data.exBoost.ExBoostRepository{return new pinball.common.data.exBoost.ExBoostRepository();}''',' implements pinball.context.global.GlobalLogicForSection')
 _put(src,'pinball.common.data.gacha::GachaRepository','public function getGachaIdsAvailableForPlayer(p:pinball.common.data.player.PlayerLogic,t:Number):Array{return [];}')
 _put(src,'pinball.common.data.gacha::GachaCampaignLogic','')
 _put(src,'pinball.dialog.general::OkDialog','public function OkDialog(v:Array=null,f:Function=null){}')
 enum_bootstrap=[]
 for q,names in ENUMS.items():selected+=_enum(src,a,v,q,names,enum_bootstrap)
 # The public player container supplies only declarations for added consumers.
 path=Path(shared['source_dir'])/'pinball/common/data/player/PlayerLogic.as';text=path.read_text(encoding='utf-8');extra=''
 for n in EXTRA['pinball.common.data.player::PlayerLogic']:
  label=_label(a,v,'pinball.common.data.player::PlayerLogic',n)
  if label not in selected:extra+=_declaration(a,v,'pinball.common.data.player::PlayerLogic',n)
 at=text.rfind('}}');text=text[:at]+extra+text[at:];path.write_text(text,encoding='utf-8')
 status_interface=Path(shared['source_dir'])/'pinball/common/data/player/LogicStatusForPlayerLogic.as'
 text=status_interface.read_text(encoding='utf-8');at=text.rfind('}}');text=text[:at]+'function applyGachaCampaignList(v:Array):void;function applyStarsGachaCampaignList(v:Array):void;'+text[at:];status_interface.write_text(text,encoding='utf-8')
 status_recorder=Path(shared['source_dir'])/'fixture/RecordingLogicStatus.as';text=status_recorder.read_text(encoding='utf-8');at=text.rfind('}}')
 additions=''.join('public function '+n+'(v:Array):void{if(v.length)throw new Error("nonempty campaign state is outside crazy fixture");CommonHarness.events.push({kind:"recorded-'+n+'",count:v.length});}' for n in ['applyGachaCampaignList','applyStarsGachaCampaignList'])
 text=text[:at]+additions+text[at:];status_recorder.write_text(text,encoding='utf-8')
 config=src/'pinball/config/core/DevConfig.as';text=config.read_text(encoding='utf-8');at=text.rfind('}}');text=text[:at]+'public static var isCrazySelect:Boolean=false;'+text[at:];config.write_text(text,encoding='utf-8')
 for q,names in EXTRA.items():selected += [_label(a,v,q,n) for n in names if _label(a,v,q,n) not in selected]
 own=Path(ctx['tool_root'])/'templates/crazy-flow'
 for p in own.rglob('*.as'):
  target=src/p.relative_to(own);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
 includes=sorted(set(shared['includes']+[str(p.relative_to(src)).replace('\\','/').removesuffix('.as').replace('/','.') for p in src.rglob('*.as') if p.stem!='CrazyFlowHarness']))
 generated_manifest=Path(shared['source_dir']).parent/'source-manifest.json';manifest=json.loads(generated_manifest.read_text(encoding='utf-8'))
 manifest['sources']={str(p.relative_to(shared['source_dir'])):abc.sha(p.read_bytes()) for p in Path(shared['source_dir']).rglob('*.as')}
 manifest['suite_adaptations']=['Declarations for five additional actual PlayerLogic methods.','LogicStatus interface and recording implementation accept only empty campaign arrays in this fixture.']
 flows._save(generated_manifest,manifest)
 return shared,src,selected,includes,identity,enum_bootstrap

def build(ctx,out:Path):
 out=abc.output_directory(ctx,out);out.mkdir(parents=True,exist_ok=True)
 shared,src,selections,includes,identity,enum_bootstrap=_prepare(ctx,out);sdk=Path(ctx['sdk'])
 command=[str(ctx['java']),'-Xmx1g','-Dflexlib='+str(sdk/'frameworks'),'-jar',str(sdk/'lib/mxmlc-cli.jar'),'+configname=air','-compiler.float=false','-swf-version=44','-target-player=32.0','-debug=true','-compress=false','-compiler.source-path='+str(src)+','+str(shared['source_dir']),'-includes='+','.join(includes),'-output='+str(out/'template.swf'),str(src/'CrazyFlowHarness.as')]
 started=time.perf_counter();run=subprocess.run(command,cwd=out,capture_output=True,timeout=120);(out/'compile.log').write_bytes(run.stdout+run.stderr)
 flows._save(out/'compile-receipt.json',{'command':command,'exit_code':run.returncode,'elapsed_ms':round((time.perf_counter()-started)*1000,3),'source_sha256':{str(p):abc.sha(p.read_bytes()) for root in (src,Path(shared['source_dir'])) for p in root.rglob('*.as')}})
 if run.returncode:raise RuntimeError('Crazy-flow compiler failed: '+str(out/'compile.log'))
 b,source,sv,_=abc.load_current();template=(out/'template.swf').read_bytes();target=b.abcfmt.ABC(list(abc.raw_units(template))[0][1]);tv=abc.view(target)
 for spec in selections:
  label=spec if isinstance(spec,str) else spec.get('target',spec['source'])
  if label not in tv.by_label:raise ValueError('Required downstream declaration not linked: '+label)
 mapping=abc.graft(target,source,selections);payload=abc.replace_abc(template,target);swf=out/'Harness.swf';swf.write_bytes(payload)
 parsed=b.abcfmt.ABC(list(abc.raw_units(payload))[0][1]);proof=abc.verify_grafts(parsed,source,mapping)
 proof_path=out/'proof.json';flows._save(proof_path,{'identity':identity,'execution_swf_sha256':abc.sha(payload),'real_methods':proof,'enum_bootstrap':enum_bootstrap,'required_case_ids':['crazy-gacha-100'],'required_step_ids':STEP_IDS,'source_chain':['GachaExecRealRemote.successHandler -> GachaLoadingTask.remoteInput -> createCharacterGachaResult -> SceneKind.GachaBallMovie','save callback -> GachaResultSaveDialog.remoteInput -> refreshList -> setButtonEnabled','complete Initialize load -> player.lastCrazyGachaDrawResult -> HomeScene.startChangeCrazyGachaResultScene -> SceneKind.GachaResult','select callback -> GachaResultSelectDialog.remoteInput -> actual lastCrazy setter(null), selectIndex=-1, isCrazySelect=true'],'notes':['Fresh draw passes candidates through events and scene data; no invented write to lastCrazyGachaDrawResult.','Load reconstructs that field through the complete actual Initialize methods; select clears it with the actual dialog handler.','Asset lookup, analytics, scene loading/navigation and save-dialog view refresh are typed recording boundaries; no GPU or real disk/player state.','The Home back-navigation catalog dependency returns an empty list for the depleted-ticket fixture; it is not an availability gate test.','Campaign delegation accepts empty arrays only; nonempty input fails explicitly.','The negative control proves the candidate-continuity assertion detects a changed ID after the real loading consumer; it is not a production master-data validation claim.']})
 app=out/'application.xml';app.write_text('<application xmlns="http://ns.adobe.com/air/application/51.2"><id>local.starpoint.clientair.crazyflow</id><versionNumber>1.0.0</versionNumber><filename>crazy-flow</filename><initialWindow><content>Harness.swf</content><visible>false</visible></initialWindow></application>',encoding='utf-8')
 return {'application':app,'swf':swf,'proof':proof_path,'required_case_ids':['crazy-gacha-100'],'required_step_ids':STEP_IDS,'min_assertions':150}
