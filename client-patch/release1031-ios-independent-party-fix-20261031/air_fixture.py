"""Execute six exact production ABC methods in a bounded desktop AIR fixture."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
import argparse,json,struct,subprocess,sys,types,zlib
from pathlib import Path
import common as c
p=c.framework()
from swfabc import swftags
LABELS=list(c.TARGETS.values())+['cn.mod::IndependentRushParty$/'+s+'|1' for s in ('setEventId','getEventId','category')]
SOURCES={
'cn/mod/IndependentRushParty.as':'''package cn.mod { public class IndependentRushParty {
 private static var _eventId:int=0;
 public static function setEventId(value:int):void { _eventId=value; }
 public static function getEventId():int { return _eventId; }
 public static function category():int { return 4; }
}}''',
'flash/Boot.as':'''package flash { public class Boot { public static var skip_constructor:Boolean=false; }}''',
'haxe/ds/Option.as':'''package haxe.ds { public class Option {} }''',
'pinball/common/data/scene/SceneKind.as':'''package pinball.common.data.scene { public class SceneKind {} }''',
'pinball/context/global/GlobalLogic.as':'''package pinball.context.global { public class GlobalLogic {} }''',
'pinball/common/data/quest/event/rush/RushEventLogic.as':'''package pinball.common.data.quest.event.rush {
 public class RushEventLogic { public var applied:Array=[]; public function applySummaryResponse(o:Object):void {trace("FIXTURE summary");applied.push(o);} }
}''',
'pinball/remote/event/rush/summary/EventRushSummaryRemoteInput.as':'''package pinball.remote.event.rush.summary {
 public class EventRushSummaryRemoteInput { public var index:int; public var params:Array;
 public function EventRushSummaryRemoteInput(i:int=0,p:Array=null) {index=i;params=p;} }
}''',
'jp/sipo/gipo/core/Gear.as':'''package jp.sipo.gipo.core { public class Gear {
 public var children:Array=[]; public function addChild(child:Gear,where:Object):void {trace("FIXTURE addChild");children.push(child);} }
}''',
'jp/sipo/gipo/core/GearHolderImpl.as':'''package jp.sipo.gipo.core {
 public class GearHolderImpl { public var gear:Gear=new Gear(); } }''',
'pinball/context/input/HookEntrance.as':'''package pinball.context.input { public interface HookEntrance {} }''',
'pinball/context/input/HookDispatcher.as':'''package pinball.context.input { import jp.sipo.gipo.core.Gear;
 public class HookDispatcher extends Gear implements HookEntrance {} }''',
'pinball/context/input/HookDispatcherProvider.as':'''package pinball.context.input { public class HookDispatcherProvider {
 public var alive:Boolean=true; public var made:Array=[];
 public function isAlive():Boolean {trace("FIXTURE alive "+alive);return alive;}
 public function createHookDispatcher(callback:Function,section:Function):HookDispatcher {
  trace("FIXTURE dispatcher");var d:HookDispatcher=new HookDispatcher(); made.push(d);return d;
 }
} }''',
'pinball/dialog/processing/ServiceLauncher.as':'''package pinball.dialog.processing {
 import jp.sipo.gipo.core.GearHolderImpl; import pinball.context.input.HookDispatcherProvider;
 public class ServiceLauncher extends GearHolderImpl {
 public var hookDispatcherProvider:HookDispatcherProvider=new HookDispatcherProvider(); }
}''',
'pinball/context/SectionCommand.as':'''package pinball.context { public class SectionCommand {
 public static var EventRushPartyRemote:Function=function():void {}; } }''',
'pinball/context/remote/RemoteForLogic.as':'''package pinball.context.remote {
 import pinball.context.input.HookDispatcher; public interface RemoteForLogic {
 function eventRushParty(d:HookDispatcher):void; } }''',
'pinball/context/remote/real/RealRemote.as':'''package pinball.context.remote.real { public class RealRemote {} }''',
'pinball/context/remote/real/RealRemoteService.as':'''package pinball.context.remote.real {
 public class RealRemoteService { public static var requests:Array=[];
 public var realRemote:RealRemote;
 public function RealRemoteService(r:RealRemote=null) {realRemote=r;}
 public function startUserRequest(endpoint:String,payload:Object,success:Function):void {
  requests.push({endpoint:endpoint,payload:payload,success:success,service:this});
 }
} }''',
'pinball/remote/event/rush/party/EventRushPartyRealRemote.as':'''package pinball.remote.event.rush.party {
 import pinball.context.remote.real.*; import pinball.context.input.HookEntrance;
 public class EventRushPartyRealRemote extends RealRemoteService {
 public var dispatcher:HookEntrance;
 public function EventRushPartyRealRemote(r:RealRemote=null,d:HookEntrance=null) {super(r);dispatcher=d;}
 public function successHandler(o:Object=null):void {}
} }''',
'pinball/scene/loading/LoadingTask.as':'''package pinball.scene.loading {
 import pinball.dialog.processing.ServiceLauncher;
 import jp.sipo.gipo.core.GearHolderImpl;
 public class LoadingTask extends GearHolderImpl { public var serviceLauncher:ServiceLauncher=new ServiceLauncher();
 public var outside:int=0; public function openOutOfPeriodDialog():void {outside++;} }
}''',
'pinball/loading/rush/RushEventLoadingTask.as':'''package pinball.loading.rush {
 import pinball.scene.loading.LoadingTask; import pinball.context.remote.RemoteForLogic;
 import pinball.common.data.scene.SceneKind; import pinball.context.global.GlobalLogic;
 import pinball.common.data.quest.event.rush.RushEventLogic;
 import pinball.remote.event.rush.summary.EventRushSummaryRemoteInput;
 public class RushEventLoadingTask extends LoadingTask {
 public var remote:RemoteForLogic; public var nextScene:SceneKind; public var globalLogic:GlobalLogic;
 public var eventId:int; public var event:RushEventLogic;
 public function partyRemoteInput(o:Object=null):void {}
 public function summaryRemoteInput(input:EventRushSummaryRemoteInput):void {}
} }''',
'pinball/common/data/party/event/EventPartyGroupHolder.as':'''package pinball.common.data.party.event {
 public class EventPartyGroupHolder { public function getPartyCategory():int {return 4;} } }''',
'pinball/common/data/party/event/rush/RushEventPartyGroupHolder.as':'''package pinball.common.data.party.event.rush {
 import pinball.common.data.party.event.EventPartyGroupHolder;
 import pinball.common.data.quest.event.rush.RushEventLogic; import haxe.ds.Option;
 public class RushEventPartyGroupHolder extends EventPartyGroupHolder {
 public var questKind:Option; public var event:RushEventLogic;
 override public function getPartyCategory():int {return 4;}
} }''',
'FixtureRemote.as':'''package { import pinball.context.remote.RemoteForLogic;
 import pinball.context.remote.real.RealRemote; import pinball.context.input.HookDispatcher;
 import pinball.remote.event.rush.party.EventRushPartyRealRemote;
 public class FixtureRemote implements RemoteForLogic {
 public var source:RealRemote=new RealRemote(); public var last:EventRushPartyRealRemote;
 public function eventRushParty(d:HookDispatcher):void {trace("FIXTURE remote");last=new EventRushPartyRealRemote(source,d);}
} }'''
}
MAIN='''package { import flash.display.Sprite; import flash.desktop.NativeApplication; import flash.utils.getQualifiedClassName;
 import pinball.context.SectionCommand;
 import cn.mod.IndependentRushParty; import flash.Boot;
 import pinball.loading.rush.RushEventLoadingTask;
 import pinball.remote.event.rush.summary.EventRushSummaryRemoteInput;
 import pinball.common.data.party.event.rush.RushEventPartyGroupHolder;
 import pinball.common.data.quest.event.rush.RushEventLogic;
 import pinball.context.remote.real.RealRemoteService;
 import pinball.remote.event.rush.party.EventRushPartyRealRemote;
 public class Main extends Sprite {
 private var checks:int=0;
 private function check(ok:Boolean,label:String):void {checks++;if(!ok) throw new Error(label);}
 public function Main() {
  try {
   check(SectionCommand.EventRushPartyRemote is Function,"section callback dependency");
   var ids:Array=[700099,700100,700098,700001,0,799999,700100,700099];
   var categories:Array=[5,6,7,4,4,4,6,5];
   var holder:RushEventPartyGroupHolder=new RushEventPartyGroupHolder();
   check(getQualifiedClassName(holder)=="pinball.common.data.party.event.rush::RushEventPartyGroupHolder","holder QName");
   for(var i:int=0;i<ids.length;i++) {
    var remote:FixtureRemote=new FixtureRemote();var task:RushEventLoadingTask=new RushEventLoadingTask();
    task.remote=remote;task.eventId=ids[i];task.event=new RushEventLogic();
    var response:Object={marker:i};var before:int=RealRemoteService.requests.length;
    task.summaryRemoteInput(new EventRushSummaryRemoteInput(0,[response]));
    check(task.event.applied.length==1 && task.event.applied[0]===response,"summary applied "+i);
    check(IndependentRushParty.getEventId()==ids[i],"event forwarded "+i);
    check(holder.getPartyCategory()==categories[i],"category "+i);
    check(RealRemoteService.requests.length==before+1,"one request "+i);
    var request:Object=RealRemoteService.requests[before];
    check(request.endpoint=="event/rush/party" && request.payload.event_id==ids[i],"request event id "+i);
    check(request.service===remote.last && remote.last.realRemote===remote.source,"base remote "+i);
    check(remote.last.dispatcher===task.serviceLauncher.hookDispatcherProvider.made[0],"dispatcher "+i);
    check(task.gear.children.length==1 && task.gear.children[0]===remote.last.dispatcher,"child attachment "+i);
    check(request.success is Function,"success callback "+i);
   }
   IndependentRushParty.setEventId(700100);before=RealRemoteService.requests.length;
   var optional:EventRushPartyRealRemote=new EventRushPartyRealRemote();
   check(optional.realRemote===null && optional.dispatcher===null,"optional null ctor");
   check(RealRemoteService.requests.length==before+1 && RealRemoteService.requests[before].payload.event_id==700100,"optional ctor EX request");
   Boot.skip_constructor=true;before=RealRemoteService.requests.length;new EventRushPartyRealRemote();Boot.skip_constructor=false;
   check(RealRemoteService.requests.length==before,"Boot skip retained");
   task=new RushEventLoadingTask();task.eventId=700099;task.event=new RushEventLogic();task.remote=new FixtureRemote();
   task.serviceLauncher.hookDispatcherProvider.alive=false;
   task.summaryRemoteInput(new EventRushSummaryRemoteInput(0,[{}]));
   check(task.event.applied.length==1 && IndependentRushParty.getEventId()==700100 && RealRemoteService.requests.length==before,"dead dispatcher stops request");
   task.summaryRemoteInput(new EventRushSummaryRemoteInput(1,[]));
   check(task.outside==1 && IndependentRushParty.getEventId()==700100,"out-of-period branch retained");
   task.summaryRemoteInput(new EventRushSummaryRemoteInput(99,[]));
   check(task.outside==1 && RealRemoteService.requests.length==before,"unknown summary branch retained");
   trace("PARTY_AIR_OK "+checks);
  } catch(e:Error) {trace("PARTY_AIR_ERROR "+e.errorID+" "+e.message+" "+e.getStackTrace());}
  NativeApplication.nativeApplication.exit();
 }
} }'''

def view(a):return p.View(types.SimpleNamespace(abc=a),p.asm)

def graft(a,source,labels):
    target=view(a);imp=p.Importer(target,source);jobs=[];proof=[]
    for label in labels:
        ti,=target.by_label[label];si,=source.by_label[label];old=a.bodies[ti];imp.methods[source.a.bodies[si][0]]=old[0]
        jobs.append((label,ti,si,old))
    for label,ti,si,old in jobs:
        sb=source.a.bodies[si];a.methods[old[0]]=imp.info(sb[0]);body=imp.body(si,old[0],scope=old[3])
        c.require(not body[6] and not body[7],'Unexpected fixture exception/activation traits')
        a.bodies[ti]=body
        c.require(p.freeze(view(a).normalized(ti))==p.freeze(source.normalized(si)),'Graft is not normalized exact: '+label)
        proof.append(dict(label=label,source_method=sb[0],fixture_method=old[0],normalized_exact=True,
            source_code_sha256=c.sha(sb[5]),fixture_code_sha256=c.sha(body[5]),validation=p.check_body(body,a)))
    return proof

def transform(raw,source,negative):
    sig=raw[:3];payload=zlib.decompress(raw[8:]) if sig==b'CWS' else raw[8:];changes=[];proof=[]
    wanted=set(LABELS)-({LABELS[-1]} if negative else set())
    for kind,at,head,length in swftags.iter_tags(payload):
        if kind!=82:continue
        data=payload[at+head:at+head+length];end=data.index(b'\0',4);a=p.abcfmt.ABC(data[end+1:]);v=view(a)
        labels=[label for label in LABELS if label in wanted and label in v.by_label]
        if not labels:continue
        proof+=graft(a,source,labels);serialized=a.serialize();c.require(p.abcfmt.ABC(serialized).serialize()==serialized,'Fixture ABC roundtrip')
        data=data[:end+1]+serialized;changes.append((at,head+length,struct.pack('<HI',(82<<6)|63,len(data))+data))
    c.require({r['label'] for r in proof}==wanted,'Missing production body graft')
    for at,length,data in reversed(changes):payload=payload[:at]+data+payload[at+length:]
    return sig+raw[3:4]+struct.pack('<I',len(payload)+8)+(zlib.compress(payload) if sig==b'CWS' else payload),proof

def run(out,guard):
    c.fresh(out);out.mkdir(parents=True);src=out/'src'
    for name,code in dict(SOURCES,**{'Main.as':MAIN}).items():
        path=src/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(code,encoding='utf-8')
    skeleton=out/'skeleton.swf'
    cmd=['java','-Dflexlib='+str(c.SDK/'frameworks'),'-jar',str(c.SDK/'lib/mxmlc-cli.jar'),'+configname=air',
        '-swf-version=44','-target-player=32.0','-compiler.float=false','-debug=true',
        '-compiler.source-path='+str(src),'-output='+str(skeleton),str(src/'Main.as')]
    with (out/'mxmlc.log').open('wb') as log:result=subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=60)
    c.require(result.returncode==0,'Fixture skeleton compilation failed; see mxmlc.log')
    production=c.ABC.read_bytes();c.require(c.sha(production)==c.ABC_SHA,'Production ABC input changed')
    source=view(p.abcfmt.ABC(production));raw=skeleton.read_bytes();runs=[]
    for mode,negative in [('negative',True),('positive',False)]:
        swf,proof=transform(raw,source,negative);(out/(mode+'.swf')).write_bytes(swf)
        app=out/(mode+'.xml');app.write_text('''<?xml version="1.0" encoding="utf-8"?>
<application xmlns="http://ns.adobe.com/air/application/51.2"><id>cn.release.partyfixture</id><versionNumber>1.0</versionNumber>
<filename>partyfixture</filename><initialWindow><content>'''+mode+'''.swf</content><visible>false</visible><width>10</width><height>10</height></initialWindow></application>''',encoding='utf-8')
        r=subprocess.run([str(c.SDK/'bin/adl.exe'),'-nodebug',str(app)],cwd=out,capture_output=True,timeout=35)
        log=(r.stdout+r.stderr).decode('utf-8',errors='replace');(out/(mode+'.log')).write_text(log,encoding='utf-8')
        runs.append(dict(mode=mode,exit_code=r.returncode,log=log,swf_sha256=c.sha(swf),production_body_grafts=proof))
    c.require(runs[0]['exit_code']==0 and 'PARTY_AIR_ERROR 0 category 0' in runs[0]['log'],'Negative fixed-category control did not fail as expected')
    c.require(runs[1]['exit_code']==0 and 'PARTY_AIR_OK 80' in runs[1]['log'] and 'PARTY_AIR_ERROR' not in runs[1]['log'],
        'Production body AIR regression failed; see positive.log')
    c.dump(out/'air-report.json',dict(status='six_actual_production_bodies_air_passed',full_abc_sha256=c.ABC_SHA,runs=runs,
        cases=['normal 5','EX 6','fantasy 7','legacy Rush 4','zero/unknown fallback 4','activity switches','optional null constructor',
            'Boot skip','dead dispatcher','out-of-period','unknown summary input'],
        fixture_boundary='Real target and helper method bodies on sealed QName receivers; networking, scene service lifecycle and server persistence are controlled test doubles.',
        negative_control='Fixture-only category helper returning 4; not an execution of the old iOS native image.',
        runtime='AIR SDK 51.2.1.5 Windows AVM2',bounded_parent_job=guard,ios_native_executed=False,device_tested=False,
        source_sha256=c.sha(Path(__file__).read_bytes())))
    print('AIR actual production bodies passed:',runs[1]['log'].strip())

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True,type=Path);ap.add_argument('--background-child',action='store_true')
    ap.add_argument('--parent-guard',type=Path);args=ap.parse_args()
    if args.background_child:run(args.output,c.read(args.parent_guard));return
    guard=c.bounded_job();parent=args.output.with_name(args.output.name+'-parent-job.json');c.dump(parent,guard)
    cmd=[sys.executable,'-B',str(c.BACKGROUND),'--timeout','165','--cwd',str(c.TASK),'--',sys.executable,'-B',str(Path(__file__)),
        '--background-child','--output',str(args.output),'--parent-guard',str(parent)]
    r=subprocess.run(cmd,cwd=c.TASK,timeout=170);c.require(r.returncode==0,'Background AIR fixture failed')
if __name__=='__main__':main()
