"""Run the prepared iOS getter and real shared source bodies in isolated AIR.

The receiver is a sealed class with its real QName and Array field contract.
Only battle-condition inputs, Enemy's unused type shell, Boot's constructor
flag, and global Decimal initialization are supplied by this fixture.
"""
from __future__ import annotations
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
import argparse,copy,json,struct,subprocess,sys,zlib
from pathlib import Path
sys.dont_write_bytecode=True
from prepare_getter import p,view,sha,save,bounded_job,TASK,CLIENT,ANDROID,OWNER,LABEL
from swfabc import swftags

SDK=Path(str(fc.private('sdk')))
BACKGROUND=Path(str(fc.tool('support/process/run_background.py')))
PREPARED=TASK/'prepared01'
REAL_METHODS=[
    'pinball.scene.battle.battle.ability::DuringCheckerWithDecimal/<ctor>',
    'pinball.scene.battle.battle.ability::DuringCheckerWithDecimal/getActiveCount|1',
    'pinball.scene.battle.battle.ability::DuringCheckerWithDecimal$/sum|1',
    'pinball.common.math._Decimal::Decimal_Impl_$/fromInt|1',
    'pinball.common.math._Decimal::Decimal_Impl_$/_new|1',
    'pinball.common.math._FloatInt::FloatInt_Impl_$/toFloat|1'
]

SOURCES={
 'pinball/scene/battle/battle/ability/BattleAbilityTotalizerImpl.as':'''package pinball.scene.battle.battle.ability {
 public class BattleAbilityTotalizerImpl {
  public var duringDashParameters:Array;
  public function getTotalDashParameter(index:int):Number { throw new Error("ungrafted getter"); }
 }
}''',
 'pinball/scene/battle/battle/ability/DuringCheckerWithDecimal.as':'''package pinball.scene.battle.battle.ability {
 import pinball.scene.battle.battle.enemy.Enemy;
 public class DuringCheckerWithDecimal {
  public var value:Number;
  public var ownerIndex:int;
  public var checker:DuringChecker;
  public var abilityOrigin:int;
  public function DuringCheckerWithDecimal(ownerIndex:int=0,abilityOrigin:int=0,checker:DuringChecker=null,value:Number=0) {}
  public function getActiveCount(enemy:Enemy):int { throw new Error("ungrafted activeCount"); }
  public static function sum(values:Array,enemy:Enemy):Number { throw new Error("ungrafted sum"); }
 }
}''',
 'pinball/scene/battle/battle/ability/DuringChecker.as':'''package pinball.scene.battle.battle.ability {
 import pinball.scene.battle.battle.enemy.Enemy;
 public interface DuringChecker { function getActiveCount(enemy:Enemy):int; }
}''',
 'pinball/scene/battle/battle/enemy/Enemy.as':'''package pinball.scene.battle.battle.enemy { public class Enemy {} }''',
 'pinball/common/math/_Decimal/Decimal_Impl_.as':'''package pinball.common.math._Decimal {
 public final class Decimal_Impl_ {
  public static var RESOLTION:Number;
  public static function fromInt(value:int):Number { throw new Error("ungrafted fromInt"); }
  public static function _new(value:Number):Number { throw new Error("ungrafted new"); }
 }
}''',
 'pinball/common/math/_FloatInt/FloatInt_Impl_.as':'''package pinball.common.math._FloatInt {
 public final class FloatInt_Impl_ { public static function toFloat(value:Number):Number { throw new Error("ungrafted toFloat"); } }
}''',
 'flash/Boot.as':'''package flash { public final class Boot { public static var skip_constructor:Boolean=false; } }''',
 'fixture/FixtureChecker.as':'''package fixture {
 import pinball.scene.battle.battle.ability.DuringChecker;
 import pinball.scene.battle.battle.enemy.Enemy;
 public final class FixtureChecker implements DuringChecker {
  public var activeCount:int; public var calls:int=0; public var lastEnemy:Enemy;
  public function FixtureChecker(value:int) { activeCount=value; }
  public function getActiveCount(enemy:Enemy):int { calls++;lastEnemy=enemy;return activeCount; }
 }
}'''
}

MAIN='''package {
 import flash.display.Sprite;
 import flash.desktop.NativeApplication;
 import flash.utils.describeType;
 import flash.utils.getQualifiedClassName;
 import flash.Boot;
 import fixture.FixtureChecker;
 import pinball.scene.battle.battle.ability.BattleAbilityTotalizerImpl;
 import pinball.scene.battle.battle.ability.DuringCheckerWithDecimal;
 import pinball.common.math._Decimal.Decimal_Impl_;
 import pinball.common.math._FloatInt.FloatInt_Impl_;
 public class Main extends Sprite {
  private var assertions:int=0;
  private function check(value:Boolean,label:String):void { if(!value)throw new Error("assertion: "+label);assertions++; }
  private function invoke(t:BattleAbilityTotalizerImpl,index:int):Number { return t.getTotalDashParameter(index); }
  public function Main() {
   try {
    Boot.skip_constructor=false;
    Decimal_Impl_.RESOLTION=100000;
    var t:BattleAbilityTotalizerImpl=new BattleAbilityTotalizerImpl();
    var desc:XML=describeType(t);
    check(getQualifiedClassName(t)=="pinball.scene.battle.battle.ability::BattleAbilityTotalizerImpl","real receiver QName");
    check(String(desc.@isDynamic)=="false","sealed receiver");
    check(String(desc.variable.(@name=="duringDashParameters").@type)=="Array","real Array field contract");
    check(Decimal_Impl_.fromInt(1)==100000,"real Decimal.fromInt");
    check(Decimal_Impl_._new(1.6)==2,"real Decimal._new");
    check(FloatInt_Impl_.toFloat(17)==17,"real FloatInt.toFloat");
    var i:int;
    for(i=0;i<7;i++)check(invoke(t,i)==0,"no array "+i);
    t.duringDashParameters=[];
    for(i=0;i<7;i++)check(invoke(t,i)==0,"missing channel "+i);
    t.duringDashParameters=[null,null,null,null,null,null,null];
    for(i=0;i<7;i++)check(invoke(t,i)==0,"null channel "+i);
    t.duringDashParameters=[[],[],[],[],[],[],[]];
    for(i=0;i<7;i++)check(invoke(t,i)==0,"empty real sum "+i);
    for(i=0;i<7;i++) {
     var condition:FixtureChecker=new FixtureChecker(i+1);
     var raw:Number=100000*(i+1);
     var row:DuringCheckerWithDecimal=new DuringCheckerWithDecimal(i,77,condition,raw);
     check(row.ownerIndex==i && row.abilityOrigin==77 && row.value==raw && row.checker===condition,"real constructor "+i);
     t.duringDashParameters[i]=[row];
     check(invoke(t,i)==raw*(i+1),"channel value "+i);
     check(condition.calls==1 && condition.lastEnemy===null,"real getActiveCount with null Enemy "+i);
    }
    var a:FixtureChecker=new FixtureChecker(2);
    var b:FixtureChecker=new FixtureChecker(0);
    var c:FixtureChecker=new FixtureChecker(-3);
    var d:FixtureChecker=new FixtureChecker(1);
    t.duringDashParameters[3]=[
     new DuringCheckerWithDecimal(0,7,a,100000),
     new DuringCheckerWithDecimal(1,7,b,999000),
     new DuringCheckerWithDecimal(2,7,c,888000),
     new DuringCheckerWithDecimal(3,7,d,-50000)
    ];
    check(invoke(t,3)==150000,"real sum positive/zero/negative count and signed values");
    check(a.calls==1 && b.calls==1 && c.calls==1 && d.calls==1,"all checker conditions visited");
    check(a.lastEnemy===null && b.lastEnemy===null && c.lastEnemy===null && d.lastEnemy===null,"null Enemy forwarded");
    check(invoke(t,-1)==0 && invoke(t,7)==0,"missing out of range channels retain zero contract");
    t.duringDashParameters[0]=[{}];
    var rejected:Boolean=false;
    try { invoke(t,0); } catch(e:TypeError) { rejected=e.errorID==1034; }
    check(rejected,"real sum preserves bad-element type failure");
    trace("GETTER_AIR_OK "+assertions);
   } catch(error:Error) { trace("GETTER_AIR_ERROR "+error.errorID+" "+error.name+" "+error.message); }
   NativeApplication.nativeApplication.exit(0);
  }
 }
}'''

def graft(target,source,labels):
    """Import actual body and MethodInfo, retaining only fixture class declarations."""
    tv=view(target);sv=source;importer=p.Importer(tv,sv);jobs=[]
    for label in labels:
        ti,=tv.by_label[label];si,=sv.by_label[label]
        old=target.bodies[ti];source_body=sv.a.bodies[si];mid=old[0]
        importer.methods[source_body[0]]=mid;jobs.append((label,ti,si,mid,old))
    proof=[]
    for label,ti,si,mid,old in jobs:
        sb=sv.a.bodies[si]
        target.methods[mid]=importer.info(sb[0])
        body=importer.body(si,mid,scope=old[3])
        assert not body[6] and not body[7]
        target.bodies[ti]=body
        fresh=view(target)
        assert p.freeze(fresh.normalized(ti))==p.freeze(sv.normalized(si)),label
        proof.append(dict(label=label,source_method=sb[0],fixture_method=mid,
            source_code_sha256=sha(sb[5]),fixture_code_sha256=sha(body[5]),
            source_body_bytes=len(sb[5]),fixture_body_bytes=len(body[5]),
            source_scope=sb[3:5],fixture_scope=body[3:5],normalized_exact=True,
            validation=p.check_body(body,target)))
    return proof

def transform_swf(raw,production,shared,negative):
    signature=raw[:3];payload=zlib.decompress(raw[8:]) if signature==b'CWS' else raw[8:]
    changes=[];all_proofs=[]
    for kind,at,header,length in swftags.iter_tags(payload):
        if kind!=82:continue
        data=payload[at+header:at+header+length];end=data.index(b'\0',4)
        a=p.abcfmt.ABC(data[end+1:]);v=view(a)
        wanted=[label for label in REAL_METHODS if label in v.by_label]
        proofs=graft(a,shared,wanted) if wanted else []
        if LABEL in v.by_label:
            proofs+=graft(a,production,[LABEL])
            if negative:
                ci=next(i for i,r in enumerate(a.instances) if a.mn_name(r[0])==OWNER)
                traits=a.instances[ci][6]
                removed=[t for t in traits if t.kind==1 and a.mn_name(t.name)=='getTotalDashParameter']
                assert len(removed)==1
                a.instances[ci][6]=[t for t in traits if t not in removed]
        if not proofs:continue
        serialized=a.serialize();assert p.abcfmt.ABC(serialized).serialize()==serialized
        content=data[:end+1]+serialized
        changes.append((at,header+length,struct.pack('<HI',(82<<6)|63,len(content))+content))
        all_proofs+=proofs
    assert {r['label'] for r in all_proofs}==set(REAL_METHODS+[LABEL]),'not every real production method was grafted'
    for at,length,tag in reversed(changes):payload=payload[:at]+tag+payload[at+length:]
    result=signature+raw[3:4]+struct.pack('<I',len(payload)+8)+(zlib.compress(payload) if signature==b'CWS' else payload)
    return result,all_proofs

def run_fixture(out,guard):
    assert out.is_relative_to(TASK.resolve()) and not out.exists(),'fresh fixture output required'
    out.mkdir(parents=True);src=out/'src'
    for name,text in {**SOURCES,'Main.as':MAIN}.items():
        dest=src/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text,encoding='utf-8')
    skeleton=out/'skeleton.swf'
    cmd=['java','-Dflexlib='+str(SDK/'frameworks'),'-jar',str(SDK/'lib/mxmlc-cli.jar'),'+configname=air',
         '-swf-version=44','-target-player=32.0','-compiler.float=false','-debug=true',
         '-compiler.source-path='+str(src),'-output='+str(skeleton),str(src/'Main.as')]
    with (out/'mxmlc.log').open('wb') as log:
        result=subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=60)
    assert result.returncode==0,('fixture skeleton compilation failed',result.returncode)
    port=json.loads((PREPARED/'port.json').read_text('utf-8-sig'));prod_raw=(PREPARED/'full.abc').read_bytes()
    assert sha(prod_raw)==port['full_abc_sha256']
    production=view(p.abcfmt.ABC(prod_raw));shared=p.View(p.SwfAbc(ANDROID),p.asm)
    raw=skeleton.read_bytes();runs=[]
    for mode,negative in [('negative',True),('positive',False)]:
        swf,proof=transform_swf(raw,production,shared,negative);swf_path=out/(mode+'.swf');swf_path.write_bytes(swf)
        app=out/(mode+'.xml');app.write_text('''<?xml version="1.0" encoding="utf-8"?>
<application xmlns="http://ns.adobe.com/air/application/51.2"><id>cn.release.dashgetterfixture</id>
<versionNumber>1.0</versionNumber><filename>dashgetterfixture</filename>
<initialWindow><content>'''+swf_path.name+'''</content><visible>false</visible><width>10</width><height>10</height></initialWindow></application>''',encoding='utf-8')
        command=[str(SDK/'bin/adl.exe'),'-nodebug',str(app)]
        result=subprocess.run(command,cwd=out,capture_output=True,timeout=35)
        log=result.stdout+result.stderr;(out/(mode+'.log')).write_bytes(log)
        runs.append(dict(mode=mode,exit_code=result.returncode,swf_sha256=sha(swf),
            log=log.decode('utf-8',errors='replace'),production_body_grafts=proof))
    assert runs[0]['exit_code']==0 and 'GETTER_AIR_ERROR 1069 ReferenceError' in runs[0]['log'],runs[0]
    assert runs[1]['exit_code']==0 and 'GETTER_AIR_OK ' in runs[1]['log'] and 'GETTER_AIR_ERROR' not in runs[1]['log'],runs[1]
    report=dict(status='actual_prepared_getter_air_negative_positive_passed',
        prepared_full_abc_sha256=sha(prod_raw),prepared_method=101872,negative_error_id=1069,
        runtime='SDK51.2.1.5 desktop AIR AVM2',runs=runs,parent_bounded_job=guard,
        real_production_bodies=[LABEL,*REAL_METHODS],
        fixture_inputs=[
            'Sealed receiver uses actual BattleAbilityTotalizerImpl QName and duringDashParameters:Array field contract; unrelated receiver fields and lifecycle are not modeled.',
            'FixtureChecker implements the actual DuringChecker interface with configurable activeCount and records the Enemy argument; battle condition evaluation itself is not executed.',
            'Enemy is an unused type shell; getter must forward null.',
            'Boot.skip_constructor=false and Decimal.RESOLTION=100000 are controlled initialization inputs; full game static initialization is not executed.'
        ],
        old_ios_native_sum_executed=False,ios_native_executed=False,device_tested=False)
    save(out/'air-report.json',report)
    save(out/'source-manifest.json',dict(files=[dict(path=str(path),sha256=sha(path.read_bytes())) for path in sorted(Path(__file__).resolve().parent.glob('*')) if path.is_file()],
        prepared_report_sha256=sha((PREPARED/'port.json').read_bytes()),fixture_sources=[dict(path=str(path),sha256=sha(path.read_bytes())) for path in sorted(src.rglob('*.as'))]))
    print(json.dumps(dict(status=report['status'],output=str(out),negative_error_id=1069,positive_log=runs[1]['log'].strip())))

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True,type=Path)
    ap.add_argument('--background-child',action='store_true');ap.add_argument('--parent-guard',type=Path)
    args=ap.parse_args();out=args.output.resolve()
    if args.background_child:
        assert args.parent_guard and args.parent_guard.is_file()
        guard=json.loads(args.parent_guard.read_text('utf-8'))
        run_fixture(out,guard);return
    guard=bounded_job();parent_guard=out.with_name(out.name+'-parent-job.json')
    assert not parent_guard.exists();parent_guard.parent.mkdir(parents=True,exist_ok=True);save(parent_guard,guard)
    command=[sys.executable,'-B',str(BACKGROUND),'--timeout','165','--cwd',str(TASK),'--',
        sys.executable,'-B',str(Path(__file__).resolve()),'--background-child','--output',str(out),'--parent-guard',str(parent_guard)]
    result=subprocess.run(command,cwd=TASK,check=False,timeout=170)
    assert result.returncode==0,('background AIR fixture failed',result.returncode)

if __name__=='__main__':main()
