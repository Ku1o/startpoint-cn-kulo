"""Current native availability plus the complete real R11 operations helper ABC."""
from __future__ import annotations
from pathlib import Path
import json,subprocess,time,struct,zlib,shutil
import abc_tools as abc
import common,flows

CASE_IDS=['gacha100-native-window-ticket','gacha100-native-expired-ticket','gacha100-managed-open-ticket','gacha100-managed-open-no-ticket','gacha100-enter-closed','gacha100-enter-not-qualified-by-default','gacha100-hidden','gacha100-enter-expired']
GACHA_METHODS=['isAvailable','isWithinPeriod','isComeback','isStarsGacha','get_pageKind','get_crazyTenTimesTicketItemId','get_startTime','get_endTime','getExtendedEndTime','get_onceTicketItemId','get_tenTimesTicketItemId','get_ticketExpiryTime']

def _inject(template,helper):
 body=zlib.decompress(template[8:]) if template[:3]==b'CWS' else template[8:]
 first=next(at for code,at,head,size in abc.swftags.iter_tags(body) if code==82)
 payload=struct.pack('<I',1)+b'actual_content_operations\0'+helper
 tag=struct.pack('<HI',(82<<6)|63,len(payload))+payload
 final=body[:first]+tag+body[first:]
 return b'FWS'+template[3:4]+struct.pack('<I',len(final)+8)+final

def _put(root,qname,text):
 path=root/(qname.replace('::','/').replace('.','/')+'.as');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')

def build(ctx,out:Path):
 out=abc.output_directory(ctx,out);out.mkdir(parents=True,exist_ok=True);shared=common.prepare_sources(ctx,out/'common')
 # Source-path declarations take precedence over external-library declarations.
 # This generated recording stub must not shadow the compiler-only external API.
 stub=Path(shared['source_dir'])/'cn/content/ContentOperationsState.as'
 if not stub.resolve().is_relative_to(out.resolve()):raise ValueError('Generated stub escapes suite output')
 if stub.exists():stub.unlink()
 builder,source,sv,identity=abc.load_current()
 _,helper,hv,helper_identity=abc.load_current(('cn.content::ContentOperationsState',))
 # Preserve every class/body/cinit in the actual standalone helper unit.
 units=[raw for name,raw in abc.raw_units(Path(ctx['swf']).read_bytes()) if abc.sha(raw)==helper_identity['main_abc_sha256']]
 if len(units)!=1:raise ValueError('Actual operations helper must be a unique ABC')
 helper_bytes=units[0]
 if {helper.mn_name(r[0]) for r in helper.instances}!={'cn.content::ContentOperationsState'}:raise ValueError('Unexpected classes in standalone operations ABC')
 src=out/'src';src.mkdir(parents=True,exist_ok=True)
 _put(src,'pinball.common.data.gacha::GachaLogic','''package pinball.common.data.gacha {import haxe.ds.Option;import pinball.common.data.player.PlayerLogic;import pinball.common.time.TimeRange;public dynamic class GachaLogic {public var id:int;public var values:Object;public var period:TimeRange;public var comebackGachaPeriod:Option;public var starsGachaPeriod:Option;__METHODS__}}'''.replace('__METHODS__','\n'.join(_declaration(source,sv,'pinball.common.data.gacha::GachaLogic',n) for n in GACHA_METHODS)))
 _put(src,'pinball.common.data.gacha::GachaPageKind','''package pinball.common.data.gacha {public class GachaPageKind {public var tag:String;public var index:int;public var params:Array;public function GachaPageKind(t:String,i:int,p:Array){tag=t;index=i;params=p;}}}''')
 _put(src,'pinball.common.time::TimeRange','''package pinball.common.time {import haxe.ds.Option;public class TimeRange {public var startTime:Number;public var endTime:Option;public function TimeRange(t:Number=0,e:Option=null){}public function isWithin(t:Number):Boolean{throw new Error("ungrafted TimeRange.isWithin");}public function isEarlierThanEnd(t:Number):Boolean{throw new Error("ungrafted TimeRange.isEarlierThanEnd");}}}''')
 # hasItem is an actual production method; add only its declaration to the
 # generated typed common carrier, never alter repository or shared templates.
 player=Path(shared['source_dir'])/'pinball/common/data/player/PlayerLogic.as';text=player.read_text(encoding='utf-8')
 if 'function hasItem(' not in text:
  at=text.rfind('}}');text=text[:at]+'public function hasItem(p0:int):Boolean{throw new Error("ungrafted hasItem");}'+text[at:];player.write_text(text,encoding='utf-8')
 app_time=Path(shared['source_dir'])/'pinball/common/time/_AppTime/AppTime_Impl_.as';text=app_time.read_text(encoding='utf-8')
 if 'function toSecondsAccuracy(' not in text:
  at=text.rfind('}}');text=text[:at]+'public static function toSecondsAccuracy(p0:Number):Number{throw new Error("ungrafted time precision");}'+text[at:];app_time.write_text(text,encoding='utf-8')
 manifest=Path(shared['source_dir']).parent/'source-manifest.json'
 prepared_manifest=json.loads(manifest.read_text(encoding='utf-8'))
 prepared_manifest['sources']={str(p.relative_to(shared['source_dir'])):abc.sha(p.read_bytes()) for p in Path(shared['source_dir']).rglob('*.as')}
 prepared_manifest['includes']=[name for name in prepared_manifest['includes'] if name!='cn.content.ContentOperationsState']
 prepared_manifest['suite_adaptations']=['Removed the generated recording operations declaration; compiler uses an external API and runtime injects the actual helper ABC.','Added declarations for actual PlayerLogic.hasItem and AppTime_Impl_.toSecondsAccuracy; their real bodies are grafted and read back.']
 flows._save(manifest,prepared_manifest)
 harness=Path(ctx['tool_root'])/'templates/gacha-entry/GachaEntryHarness.as';shutil.copy2(harness,src/harness.name)
 # Compiler-only API declaration is external: actual runtime is the pinned ABC.
 api=out/'api';_put(api,'cn.content::ContentOperationsState','''package cn.content {public class ContentOperationsState {public static function applySnapshot(v:Object):void{}public static function captureResponse(v:Object):void{}public static function gachaEnterGate(l:Object,p:Object,n:Number,e:Boolean):int{return -999;}}}''')
 sdk=Path(ctx['sdk']);java=str(ctx['java']);support=out/'operations-api.swc'
 command=[java,'-Dflexlib='+str(sdk/'frameworks'),'-jar',str(sdk/'lib/compc-cli.jar'),'+configname=air','-compiler.float=false','-compiler.source-path='+str(api),'-include-classes=cn.content.ContentOperationsState','-output='+str(support)]
 run=subprocess.run(command,cwd=out,capture_output=True,timeout=120);(out/'api-compile.log').write_bytes(run.stdout+run.stderr)
 flows._save(out/'api-compile-receipt.json',{'command':command,'exit_code':run.returncode,'compiler_only':True,'runtime_abc_injected_unchanged':True})
 if run.returncode:raise RuntimeError('API compilation failed: '+str(out/'api-compile.log'))
 includes=[n for n in shared['includes'] if n!='cn.content.ContentOperationsState']+['pinball.common.data.gacha.GachaLogic','pinball.common.data.gacha.GachaPageKind','pinball.common.time.TimeRange']
 command=[java,'-Xmx1g','-Dflexlib='+str(sdk/'frameworks'),'-jar',str(sdk/'lib/mxmlc-cli.jar'),'+configname=air','-compiler.float=false','-swf-version=44','-target-player=32.0','-debug=true','-compress=false','-compiler.source-path='+str(src)+','+str(shared['source_dir']),'-external-library-path+='+str(support),'-includes='+','.join(includes),'-output='+str(out/'template.swf'),str(src/'GachaEntryHarness.as')]
 started=time.perf_counter();run=subprocess.run(command,cwd=out,capture_output=True,timeout=120);(out/'compile.log').write_bytes(run.stdout+run.stderr)
 flows._save(out/'compile-receipt.json',{'command':command,'exit_code':run.returncode,'elapsed_ms':round((time.perf_counter()-started)*1000,3),'source_sha256':{str(p):abc.sha(p.read_bytes()) for root in (src,Path(shared['source_dir']),api) for p in root.rglob('*.as')}})
 if run.returncode:raise RuntimeError('Gate carrier compilation failed: '+str(out/'compile.log'))
 template=(out/'template.swf').read_bytes();target=builder.abcfmt.ABC(list(abc.raw_units(template))[0][1])
 native_definitions={'flash.display::Sprite','flash.utils::Dictionary','flash.desktop::NativeApplication'} & {target.mn_name(r[0]) for r in target.instances}
 if native_definitions:raise ValueError('Native AIR APIs were linked into the carrier: '+str(sorted(native_definitions))+'; append the external API library instead of replacing SDK externals')
 if any(target.mn_name(r[0])=='cn.content::ContentOperationsState' for r in target.instances):raise ValueError('Compiler-only operations API was embedded in runtime')
 specs=list(shared['selections'])+[flows._label(source,sv,'pinball.common.data.gacha::GachaLogic',n) for n in GACHA_METHODS]+[flows._label(source,sv,'pinball.common.data.gacha::GachaPageKind','<ctor>'),flows._label(source,sv,'pinball.common.time::TimeRange','<ctor>'),flows._label(source,sv,'pinball.common.time::TimeRange','isWithin'),flows._label(source,sv,'pinball.common.time::TimeRange','isEarlierThanEnd'),flows._label(source,sv,'pinball.common.time._AppTime::AppTime_Impl_','toSecondsAccuracy'),flows._label(source,sv,'pinball.common.data.player::PlayerLogic','hasItem')]
 mapping=abc.graft(target,source,specs);carrier=abc.replace_abc(template,target);parsed=builder.abcfmt.ABC(list(abc.raw_units(carrier))[0][1]);proof=abc.verify_grafts(parsed,source,mapping)
 final=_inject(carrier,helper_bytes);swf=out/'Harness.swf';swf.write_bytes(final)
 actual_units=list(abc.raw_units(final))
 if sum(raw==helper_bytes for _,raw in actual_units)!=1:raise ValueError('Actual helper bytes not preserved exactly once')
 proof_path=out/'proof.json';flows._save(proof_path,{'identity':identity,'operations_helper_identity':helper_identity,'operations_helper_byte_identical':True,'operations_helper_class_count':1,'operations_helper_methods':len(helper.bodies),'real_methods':proof,'execution_swf_sha256':abc.sha(final),'required_case_ids':CASE_IDS,'synthetic_inputs':{'page_kind_index':5,'ticket_item_id':999012,'comeback':False,'stars':False,'native_period_ms':[0,1000],'managed_snapshots':'valid synthetic schema-2 full snapshots, monotonic revisions, explicit default permission closure'},'limits':['No complete production master-table parse or UI flow.','No invented personal qualification flag: this page kind requires ticket possession plus the actual native/operations visibility and entry rules.']})
 application=out/'application.xml';application.write_text('<application xmlns="http://ns.adobe.com/air/application/51.2"><id>local.starpoint.clientair.gachaentry</id><versionNumber>1.0.0</versionNumber><filename>gacha-entry</filename><initialWindow><content>Harness.swf</content><visible>false</visible></initialWindow></application>',encoding='utf-8')
 return {'application':application,'swf':swf,'proof':proof_path,'required_case_ids':CASE_IDS,'required_step_ids':[],'min_assertions':24}

def _declaration(source,view,owner,name):
 label=flows._label(source,view,owner,name);bi,=view.by_label[label];mid=source.bodies[bi][0];info=source.methods[mid]
 typ=lambda t:source.mn_name(t).replace('::','.') if t else '*'
 # Fully qualified types in generated declaration need imports in the AS file;
 # the shared compiler includes those definitions, and we use short names for
 # the two custom dependency types already explicitly imported by this shell.
 def simple(t):
  value=typ(t)
  return value.rsplit('.',1)[-1] if value in ['haxe.ds.Option','pinball.common.data.player.PlayerLogic','pinball.common.data.gacha.GachaPageKind'] else value
 return 'public function '+name+'('+','.join('p'+str(i)+':'+simple(t) for i,t in enumerate(info[1]))+'):'+simple(info[0])+'{throw new Error("ungrafted GachaLogic.'+name+'");}'
