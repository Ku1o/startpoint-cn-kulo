"""Reusable source declarations + exact production graft for UI/store integration."""
from pathlib import Path
import copy,re,json
from inventory import ROOT,GROUPS,selections
from input_config import work_path

def sources(source,sv):
 names=set(GROUPS)|{'flash::Boot','::Std','pinball.error::ClientError','jp.sipo.util::SipoError','pinball.common.data.localStore::LocalStoreForLogic','pinball.context.input::HookEntrance','fixture::NativeStorage','fixture::StorageHook','pinball.config.core::DevConfig'}
 labels=selections(sv)
 for label in labels:
  bi,=sv.by_label[label];info=source.methods[source.bodies[bi][0]]
  for t in [info[0]]+info[1]:
   if t and '::' in source.mn_name(t):names.add(source.mn_name(t))
  import inventory
  for x in inventory.a.builder.asm.decode(source.bodies[bi][5]):
   if x.name in ('coerce','astype','getlex','findpropstrict','constructprop') and source.multinames[x.args[0]][0]==7:
    n=source.mn_name(x.args[0]);
    if '::' in n:names.add(n)
 names={n for n in names if not n.startswith('flash.') or n=='flash::Boot'}
 names|={'jp.sipo.gipo.core.handler::GenericGearDispatcher','jp.sipo.gipo.core.handler::GearDispatcherHandler'}
 imports=''.join('import '+n.replace('::','.').lstrip('.')+';' for n in sorted(names))+'import flash.filesystem.*;import flash.utils.*;'
 simple=lambda q:q.split('::')[-1] if '::' in q else q
 specials={
 'Boot':'public static var skip_constructor:Boolean=false;public static var lastError:*;',
 'Std':'public static function string(v:*):String{return String(v);}',
 'GenericGearDispatcher':'public var handlers:Array=[];public var executingHandlers:Array;public var executingIndex:int=-1;public var once:Boolean;public function get_executing():Boolean{return executingHandlers!=null;}public function clear():void{handlers=null;}',
 'GearDispatcherHandler':'public var func:Function;',
 'AddBehaviorPreset':'public static function addHead(a:Array,v:Object):void{a.unshift(v);}public static function addTail(a:Array,v:Object):void{a.push(v);}',
 'BindImpl3_0':'public var f:Function;public var a:*;public var b:*;public var c:*;public function execute():void{f(a,b,c);}',
 'DevConfig':'public var storageRoot:File;public var initialBgmVolume:Number=0.7;public function getStorageDirectory():File{return storageRoot;}',
 'CompressUtil':'public static var algorithm:String=CompressionAlgorithm.ZLIB;',
 'FileStreamWithCounter':'public var openWait:WaitInOrderImpl;public static var numberOfOpenFilesAtTheSameTime:int=0;public static var limitNumberOfOpenFilesAtTheSameTime:int=100;',
 'ApplicationOptionLogic':'public var applicationOption:Object;public var localStore:LocalStoreForLogic;public var logicAssets:ILogicAssetContainer;',
 'LocalStore':'public var devConfig:DevConfig;public var hook:Object;',
 'WaitImpl':'public var disposed:Boolean;public var completed:Boolean;public var completedDispatcher:GenericGearDispatcher;',
 }
 enumowners={'Option','SectionCommand','LocalStoreLoadInput'}
 files={}
 for owner in sorted(names):
  pkg,cls=owner.split('::');code=specials.get(cls,'');parent='';ctor='public function '+cls+'(...a){}'
  if cls in enumowners:code+='public var tag:String;public var index:int;public var params:Array;'
  if cls=='Option':code+='public static var None:Option=new Option("None",1,null);'
  if cls in ('ClientError','SipoError'):parent=' extends Error';ctor='public function '+cls+'(...a){super(String(a[0])+":"+String(a[1]));}'
  if cls=='GenericGearDispatcher':ctor='public function GenericGearDispatcher(...a){once=a.length>1?Boolean(a[1]):false;}'
  if cls=='GearDispatcherHandler':ctor='public function GearDispatcherHandler(...a){func=a[0];}'
  if cls=='BindImpl3_0':ctor='public function BindImpl3_0(...v){f=v[0];a=v[1];b=v[2];c=v[3];}'
  if cls=='FileStreamWithCounter':parent=' extends FileStream';ctor='public function FileStreamWithCounter(){super();}'
  if cls=='WaitInOrderImpl':parent=' extends WaitImpl';ctor='public function WaitInOrderImpl(){super();}'
  if cls=='LocalStore':parent=' implements LocalStoreForLogic'
  for name in GROUPS.get(owner,[]):
   static=name.startswith('$');name=name.lstrip('$')
   if name=='<ctor>':continue
   prefix=owner+('$' if static else '')+'/'+name;label,=[l for l in labels if l==prefix or l.startswith(prefix+'|')];bi,=sv.by_label[label];info=source.methods[source.bodies[bi][0]]
   args=[]
   for i,t in enumerate(info[1]):
    decl='v'+str(i)+':'+simple(source.mn_name(t) if t else '*')
    if cls=='FileStreamWithCounter' and name=='writeBytes' and i>0:decl+='=0'
    args.append(decl)
   override=(cls=='FileStreamWithCounter' and name in ('open','writeBytes','close')) or (cls=='WaitInOrderImpl' and name=='getCompleteDispatcherAddBehavior')
   code+=('override ' if override else '')+'public '+('static ' if static else '')+'function '+name+'('+','.join(args)+'):'+simple(source.mn_name(info[0]) if info[0] else '*')+'{throw new Error("ungrafted '+name+'");}'
  if cls=='LocalStoreForLogic':text='package '+pkg+' {public interface LocalStoreForLogic {function saveApplicationOption(v:Object):void;}}'
  elif cls=='HookEntrance':text='package '+pkg+' {public interface HookEntrance {function instant(v:Object,c:Object=null):void;}}'
  elif cls in ('NativeStorage','StorageHook'):continue
  else:text='package '+pkg+' {'+imports+'public class '+cls+parent+' {'+ctor+code+'}}'
  files[(pkg.replace('.','/')+'/' if pkg else '')+cls+'.as']=text
 files['fixture/StorageHook.as']=STORAGE_HOOK
 files['fixture/NativeStorage.as']=NATIVE_STORAGE
 return files

def write_sources(src,files):
 src=Path(src).resolve()
 for name,text in files.items():
  dest=(src/name).resolve()
  if not dest.is_relative_to(src):raise ValueError('source path escape '+name)
  dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text,encoding='utf-8')

def graft(target,source,builder,a):
 sv=a.view(source);tv=a.view(target);chosen=selections(sv);aliases=[]
 for label in chosen:
  ti,=tv.by_label[label];mid=target.bodies[ti][0]
  for row in target.instances:
   for t in row[6]:
    if t.data[0]=='method' and t.data[2]==mid:aliases.append((row,copy.deepcopy(t)))
 proof=a.graft(target,source,chosen)
 # Any public QName retained for compiled fixture calls receives a NEW MethodInfo/body.
 # AVM2 rejects sharing the same MethodInfo between independent method traits.
 for row,trait in aliases:
  if any(t.name==trait.name for t in row[6]):continue
  oldmid=trait.data[2];mid=len(target.methods);target.methods.append(copy.deepcopy(target.methods[oldmid]));body=copy.deepcopy(target.bodies[a.body_index(target,oldmid)]);body[0]=mid;target.bodies.append(body);trait.data=list(trait.data);trait.data[2]=mid;row[6].append(trait)
 return proof

STORAGE_HOOK="""package fixture {import pinball.context.input.HookEntrance;public class StorageHook implements HookEntrance {public var loaded:Object;public var broken:Boolean;public var notifications:int=0;public function instant(v:Object,c:Object=null):void{if(v.tag!="LocalStoreLoad"||v.params[0].tag!="ApplicationOptionLoaded")throw new Error("wrong native load notification");loaded=v.params[0].params[0];broken=v.params[0].params[1];notifications++;}}}"""
NATIVE_STORAGE="""package fixture {import flash.filesystem.File;import flash.utils.ByteArray;import haxe.ds.Option;import pinball.asset.file.FileUtil;import pinball.remote.util.CompressUtil;import pinball.config.core.DevConfig;import pinball.context.localStore.LocalStore;import pinball.context.localStore._ApplicationOptionLocalStore.ApplicationOptionLocalStore_Impl_;import pinball.common.data.localStore.ApplicationOptionLogic;public class NativeStorage {
 public static const ALLOWED:String="__STORAGE_TEST_ROOT__/";
 public static function makeLocalStore(root:File):LocalStore{var normalized:String=root.nativePath.split(String.fromCharCode(92)).join("/").toLowerCase();if(normalized.indexOf(ALLOWED.toLowerCase())!=0)throw new Error("storage test root outside dedicated directory");root.createDirectory();var cfg:DevConfig=new DevConfig();cfg.storageRoot=root;var local:LocalStore=new LocalStore();local.devConfig=cfg;local.hook={dispatcher:new StorageHook()};return local;}
 public static function makeReadOnlyLocalStore(root:File):LocalStore{var normalized:String=root.nativePath.split(String.fromCharCode(92)).join("/").toLowerCase();if(normalized!="__UI_COLD_ROOT__"||!root.exists||!root.isDirectory)throw new Error("unapproved/missing readonly UI root");var o:Option=FileUtil.readFileAsByteArray(root.resolvePath("application_option"));if(o.index!=0)throw new Error("UI file missing");var decoded:ByteArray=CompressUtil.uncompress(o.params[0]);var checked:Object=JSON.parse(decoded.readUTF());if(checked.version!==13||!(checked.cnTeammateEffectsVisible is Boolean))throw new Error("readonly UI requires verified valid v13 Boolean");var cfg:DevConfig=new DevConfig();cfg.storageRoot=root;var local:LocalStore=new LocalStore();local.devConfig=cfg;local.hook={dispatcher:new StorageHook()};return local;}
 public static function load(local:LocalStore):Object{var hook:StorageHook=local.hook.dispatcher as StorageHook;var before:int=hook.notifications;ApplicationOptionLocalStore_Impl_.startLoad(local);if(hook.notifications!=before+1||hook.loaded==null||hook.broken)throw new Error("native load missing/broken");return hook.loaded;}
 public static function createOption(raw:Object,local:LocalStore):ApplicationOptionLogic{return new ApplicationOptionLogic(raw,local,null);}
 public static function dataFile(local:LocalStore):File{return ApplicationOptionLocalStore_Impl_.getApplicationOptionDataFile(local);}
}}"""


def merge_ui_files(existing,source,sv):
 """Add real storage declarations without deleting UI-only helpers or transport classes."""
 files=dict(existing);generated=sources(source,sv)
 app='pinball/common/data/localStore/ApplicationOptionLogic.as'
 for name,text in generated.items():
  if name not in files:files[name]=text
 ui=files[app]
 ui=ui.replace('package pinball.common.data.localStore {','package pinball.common.data.localStore {import pinball.asset.logic.ILogicAssetContainer;')
 if 'public var localStore:' not in ui:ui=ui.replace('public var applicationOption:Object;','public var applicationOption:Object;public var localStore:LocalStoreForLogic;public var logicAssets:ILogicAssetContainer;')
 ui,n=re.subn(r'public function ApplicationOptionLogic\([^)]*\)\{[^}]*\}', 'public function ApplicationOptionLogic(o:Object,l:LocalStoreForLogic=null,a:ILogicAssetContainer=null){}',ui)
 if n!=1:raise ValueError('UI ApplicationOptionLogic constructor anchor changed')
 files[app]=ui
 section='pinball/context/SectionCommand.as'
 if section in existing:
  old=existing[section]
  match=re.search(r'public static function SwitchButton\([^}]+\}',old)
  if match:
   base=generated[section];files[section]=base[:-2]+match.group(0)+'}}'
 return files

# Path-only fixture adaptation; the original native storage bodies are grafted unchanged.
NATIVE_STORAGE=NATIVE_STORAGE.replace('__STORAGE_TEST_ROOT__',str(work_path('storage-validation/data')).replace(chr(92),'/')).replace('__UI_COLD_ROOT__',str(work_path('ui/storage-data/air15-linked')).replace(chr(92),'/').lower())
