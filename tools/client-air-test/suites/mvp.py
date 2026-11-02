"""Actual scoring, MVP selection and statistics methods; isolated battle inputs."""
from pathlib import Path
import json,shutil,subprocess,time
import abc_tools as abc
from flows import _label,_save

CASE_IDS=['mvp-healer-false','mvp-damage-true','mvp-tie-self','mvp-weakpoint','mvp-chain','mvp-single-field-absent','mvp-rtt']

def _weights(source,builder):
 owner='pinball.scene.battle.battle::BattleConstants'
 scripts=[row[0] for row in source.scripts if any(source.mn_name(t.name)==owner for t in row[1])]
 if len(scripts)!=1:raise ValueError('BattleConstants initialization script is missing or ambiguous')
 body=source.bodies[abc.body_index(source,scripts[0])];instructions=builder.asm.decode(body[5]);expected={'WEAK_POINT_BREAK_MVP_WEIGHT':10000,'SKILL_CHAIN_CONTRIBUTION_MVP_WEIGHT':5000,'DAMAGE_MVP_WEIGHT':1};found={};assignments=[]
 for index,ins in enumerate(instructions):
  if ins.op not in (0x61,0x68):continue
  name=source.mn_name(ins.args[0])
  if name not in expected:continue
  if name in found or index==0:raise ValueError('Duplicate or malformed MVP weight assignment: '+name)
  previous=instructions[index-1]
  if previous.op==0x2d:value=source.ints[previous.args[0]]
  elif previous.op in (0x24,0x25):value=previous.args[0]
  else:raise ValueError('MVP weight must use a directly auditable integer initializer: '+name)
  found[name]=value;assignments.append({'name':name,'value':value,'push_opcode':previous.op,'push_operand':previous.args[0],'assignment_opcode':ins.op})
 if found!=expected:raise ValueError('Pinned SWF MVP weights differ from this suite contract: '+str(found))
 return {'owner':owner,'script_method_id':scripts[0],'script_code_sha256':abc.sha(body[5]),'assignments':assignments,'verified_against_suite_inputs':True}

def _put(root,qname,text):
 path=root/(qname.replace('::','/').replace('.','/')+'.as');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')

def build(ctx,out):
 out=abc.output_directory(ctx,out);out.mkdir(parents=True,exist_ok=True)
 src=out/'src';src.mkdir(parents=True,exist_ok=True)
 templates=Path(ctx['tool_root'])/'templates/mvp'
 shutil.copy2(templates/'MvpHarness.as',src/'MvpHarness.as')
 _put(src,'haxe.ds::Option','package haxe.ds {public class Option {public var index:int;public var params:Array;public static var None:Option=new Option(1,null);public function Option(i:int,p:Array){index=i;params=p;}public static function Some(v:Object):Option{return new Option(0,[v]);}}}')
 _put(src,'pinball.common.math._FloatInt::FloatInt_Impl_','package pinball.common.math._FloatInt {public class FloatInt_Impl_ {public static function fromInt(v:int):Number {throw new Error("ungrafted fromInt");}public static function _new(v:Number):Number {throw new Error("ungrafted _new");}}}')
 _put(src,'pinball.scene.battle.battle::BattleConstants','package pinball.scene.battle.battle {public class BattleConstants {public static var WEAK_POINT_BREAK_MVP_WEIGHT:int=10000;public static var SKILL_CHAIN_CONTRIBUTION_MVP_WEIGHT:int=5000;public static var DAMAGE_MVP_WEIGHT:int=1;}}')
 _put(src,'pinball.scene.battle.battle::ScoreCalculatorBaseImpl','package pinball.scene.battle.battle {public class ScoreCalculatorBaseImpl {public var weakPointCount:int;public var skillChainContribution:int;public var damageContribution:Number;public var cureContribution:Number;public function getMvpScore():Number{throw new Error("ungrafted getMvpScore");}public function getContributionScore():Number{throw new Error("ungrafted getContributionScore");}}}')
 _put(src,'pinball.common.data.quest.battle::RoundtripStatistics','package pinball.common.data.quest.battle {public class RoundtripStatistics {public var maxTime:Number;public var averageTime:Number;}}')
 _put(src,'pinball.common.data.quest.battle::BattleClearParameter','package pinball.common.data.quest.battle {public dynamic class BattleClearParameter {public var mvpScore:Number;public var contributionScore:Number;public var isHost:Boolean;public var phaseResults:Array;public var maxPower:int;public var maxSkillChainSize:int;public var maxComboCount:int;public var overflowDamageTimes:int;public var zoneStatistics:Array;public var party:Object;public var clientChecks:Array;public var phaseStatistics:Array;public var raidPartySubId:Object;public function getStatistics():Object {throw new Error("ungrafted BattleClearParameter.getStatistics");}}}')
 _put(src,'pinball.common.data.quest.battle::BattleQuestClearParameter','package pinball.common.data.quest.battle {import haxe.ds.Option;public class BattleQuestClearParameter {public var myBattle:BattleClearParameter;public var multiOtherBattle:Option;public var roundtripStatistics:Option;public var isMultiPlayBatttle:Boolean;public function getMvpBattle():BattleClearParameter{throw new Error("ungrafted getMvpBattle");}public function getStatistics():Object{throw new Error("ungrafted BattleQuestClearParameter.getStatistics");}}}')
 includes=[str(p.relative_to(src)).replace('\\','/').removesuffix('.as').replace('/','.') for p in src.rglob('*.as') if p.stem!='MvpHarness']
 sdk=Path(ctx['sdk']);command=[ctx['java'],'-Dflexlib='+str(sdk/'frameworks'),'-jar',str(sdk/'lib/mxmlc-cli.jar'),'+configname=air','-compiler.float=false','-swf-version=44','-target-player=32.0','-debug=true','-compress=false','-compiler.source-path='+str(src),'-includes='+','.join(includes),'-output='+str(out/'template.swf'),str(src/'MvpHarness.as')]
 started=time.perf_counter();run=subprocess.run(command,cwd=out,capture_output=True,timeout=120);(out/'compile.log').write_bytes(run.stdout+run.stderr)
 _save(out/'compile-receipt.json',{'command':command,'exit_code':run.returncode,'elapsed_ms':round((time.perf_counter()-started)*1000,3),'sources':{str(p.relative_to(src)):abc.sha(p.read_bytes()) for p in src.rglob('*.as')}})
 if run.returncode:raise RuntimeError('MVP compile failed; see '+str(out/'compile.log'))
 b,s,v,identity=abc.load_current(('pinball.scene.battle.battle::ScoreCalculatorBaseImpl','pinball.common.data.quest.battle::BattleQuestClearParameter'))
 weights=_weights(s,b)
 required=[('pinball.scene.battle.battle::ScoreCalculatorBaseImpl','getMvpScore'),('pinball.scene.battle.battle::ScoreCalculatorBaseImpl','getContributionScore'),('pinball.common.data.quest.battle::BattleQuestClearParameter','getMvpBattle'),('pinball.common.data.quest.battle::BattleQuestClearParameter','getStatistics'),('pinball.common.data.quest.battle::BattleClearParameter','getStatistics'),('pinball.common.math._FloatInt::FloatInt_Impl_','fromInt'),('pinball.common.math._FloatInt::FloatInt_Impl_','_new')]
 template=(out/'template.swf').read_bytes();target=b.abcfmt.ABC(list(abc.raw_units(template))[0][1]);mapping=abc.graft(target,s,[_label(s,v,*r) for r in required]);payload=abc.replace_abc(template,target)
 swf=out/'Harness.swf';swf.write_bytes(payload);parsed=b.abcfmt.ABC(list(abc.raw_units(payload))[0][1]);proof=abc.verify_grafts(parsed,s,mapping)
 proof_path=out/'proof.json';_save(proof_path,{'identity':identity,'real_methods':proof,'execution_swf_sha256':abc.sha(payload),'required_case_ids':CASE_IDS,'missing_required_methods':[],'constant_inputs':weights,'limits':['Synthetic typed battle/party/statistics data; production constructors and full battle event dispatch are not executed.','The three MVP weights are read directly from the selected SWF script initializer and checked against shell inputs; the full BattleConstants initialization is not executed.','Option is a typed enum shape substitute; real scoring conversion, selection and statistics serialization bodies execute.','Finish responses are decoded fixture JSON, not production finish remote parsing, UI or network.']})
 application=out/'application.xml';application.write_text('<application xmlns="http://ns.adobe.com/air/application/51.2"><id>local.starpoint.clientair.mvp</id><versionNumber>1.0.0</versionNumber><filename>mvp</filename><initialWindow><content>Harness.swf</content><visible>false</visible></initialWindow></application>',encoding='utf-8')
 fixture_cases=json.loads(Path(ctx['fixtures']).read_text(encoding='utf-8-sig'))['cases'] if ctx.get('fixtures') else []
 return {'application':application,'swf':swf,'proof':proof_path,'required_case_ids':CASE_IDS,'required_step_ids':[],'min_assertions':96 if fixture_cases else 56}

def generate(ctx,out,node):
 """Run real client first, then drive the source finish endpoint with its output."""
 from run_contract import validate_binding,validate_application,validate_result,expectations,write
 root=Path(ctx['run_root']);preflight=root/'client-payload';preflight.mkdir()
 empty=preflight/'empty-fixtures.json';write(empty,{'schemaVersion':2,'cases':[]})
 built=build(ctx,preflight);binding={**validate_binding(built,ctx),**validate_application(built)}
 contract=expectations('mvp',{'schemaVersion':2,'cases':[]},built);write(preflight/'contract.json',contract)
 command=[str(Path(ctx['sdk'])/'bin/adl.exe'),'-nodebug','-cmd',str(built['application']),'--',str(empty),str(preflight/'result.json')]
 started=time.perf_counter();p=subprocess.run(command,cwd=preflight,capture_output=True,timeout=90);(preflight/'adl.log').write_bytes(p.stdout+p.stderr)
 execution={'command':command,'exit_code':p.returncode,'elapsed_ms':round((time.perf_counter()-started)*1000,3)};write(preflight/'execution.json',execution)
 result=json.loads((preflight/'result.json').read_text(encoding='utf-8'));coverage=validate_result(result,contract,p.returncode)
 write(preflight/'receipt.json',{'status':'passed',**binding,**coverage})
 command=[node,str(Path(ctx['tool_root'])/'fixtures/mvp.cjs'),'--repo',ctx['repo'],'--out',str(out),'--client-result',str(preflight/'result.json')]
 started=time.perf_counter();p=subprocess.run(command,cwd=ctx['repo'],capture_output=True,timeout=180);(root/'generator.log').write_bytes(p.stdout+p.stderr)
 write(root/'generator-execution.json',{'command':command,'exit_code':p.returncode,'elapsed_ms':round((time.perf_counter()-started)*1000,3)})
 if p.returncode:raise RuntimeError('MVP source finish generator failed; see generator.log')
 fixtures=json.loads((out/'fixtures.json').read_text(encoding='utf-8'))
 if fixtures.get('completed') is not True or {c['id'] for c in fixtures['cases']}!={'source-mvp-healer-first','source-mvp-damage-first'}:raise ValueError('MVP generator did not produce both required actual source cases')
 return out/'fixtures.json'
