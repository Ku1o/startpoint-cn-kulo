"""Small AIR verifier negative/positive test for a moved static method scope."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
from pathlib import Path
import copy,json,struct,subprocess,sys,zlib
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'lens0907-0908'))
import build_swf as p
from swfabc import swftags

SDK=Path(str(fc.private('sdk')))
TASK=Path(str(fc.client() / 'revision-ios-dispatch-fix-20261031'))

SHELL='''package cn.release {
 public final class ProbeHelper {
  public static function plain(receiver:Object):Object { return receiver; }
 }
}'''
MAIN='''package {
 import flash.display.Sprite;
 import flash.desktop.NativeApplication;
 import cn.release.ProbeHelper;
 public class Main extends Sprite {
  public function Main() {
   try {
    var receiver:Object={marker:312};
    var actual:Object=ProbeHelper.plain(receiver);
    if(actual!==receiver || actual.marker!==312)throw new Error("receiver mismatch");
    trace("SCOPE_PROBE_OK");
   }catch(e:Error){trace("SCOPE_PROBE_ERROR "+e.errorID+" "+e.message);}
   NativeApplication.nativeApplication.exit(0);
  }
 }
}'''

def patch_swf(raw, correct):
    signature=raw[:3];body=zlib.decompress(raw[8:]) if signature==b'CWS' else raw[8:]
    changes=[]
    for kind,at,header,length in swftags.iter_tags(body):
        if kind!=82:continue
        data=body[at+header:at+header+length];end=data.index(b'\0',4)
        a=p.abcfmt.ABC(data[end+1:]);ci=[i for i,r in enumerate(a.instances) if a.mn_name(r[0])=='cn.release::ProbeHelper']
        if not ci:continue
        ci,=ci;tr,=[t for t in a.classes[ci][1] if a.mn_name(t.name)=='plain'];mid=tr.data[2]
        b,=[b for b in a.bodies if b[0]==mid];rows=p.asm.decode(b[5]);assert [x.op for x in rows[:2]]==[0xd0,0x30]
        prefix=p.asm.assemble([('getlocal_0',),('pushscope',),('getlocal_1',),('pushscope',)] if correct else [('getlocal_1',),('pushscope',)])
        rows=prefix+rows[2:];b[5]=p.asm.encode(rows)[0];b[4]=b[3]+(2 if correct else 1)
        p.check_body(b,a)
        content=data[:end+1]+a.serialize();tag=struct.pack('<HI',(82<<6)|63,len(content))+content
        changes.append((at,header+length,tag))
    assert len(changes)==1
    for at,length,tag in reversed(changes):body=body[:at]+tag+body[at+length:]
    return signature+raw[3:4]+struct.pack('<I',len(body)+8)+(zlib.compress(body) if signature==b'CWS' else body)

def main():
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'native'));import common
    if '--review-existing' in sys.argv:
        job=common.bounded_job(180)
        out=TASK/'prepare-review/scope-verifier-probe01'
        assert (out/'negative.swf').read_bytes()==patch_swf((out/'original.swf').read_bytes(),False)
        assert (out/'positive.swf').read_bytes()==patch_swf((out/'original.swf').read_bytes(),True)
        negative=(out/'negative.log').read_text('utf-8');positive=(out/'positive.log').read_text('utf-8')
        assert 'SCOPE_PROBE_ERROR 1058' in negative and 'SCOPE_PROBE_OK' in positive
        assert 'SCOPE_PROBE_ERROR' not in positive
        report=dict(status='receiver_scope_negative_and_positive_executed',
            negative_error_id=1058,positive='SCOPE_PROBE_OK',
            execution_receipt=str(TASK/'jobs/scope-probe02.json'),
            prior_harness_assertion='Incorrect expected 1030/1034; actual negative was 1058. Both ADL exited 0.',
            scope_shape=dict(negative=['original_receiver'],positive=['static_helper_class','original_receiver']),
            reinspection_bounded_job=job,game_or_ios_native_executed=False,device_tested=False)
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False));return
    if '--background-child' not in sys.argv:
        job=common.bounded_job(180)
        guard=TASK/'prepare-review/scope-probe-parent-job.json'
        assert not guard.exists();guard.write_text(json.dumps(job)+'\n',encoding='utf-8')
        command=[sys.executable,'-B',str(common.BACKGROUND),'--timeout','165','--cwd',str(TASK),
            '--',sys.executable,'-B',str(Path(__file__).resolve()),'--background-child']
        result=subprocess.run(command,cwd=TASK,timeout=170,check=False)
        assert result.returncode==0,('background fixture failed',result.returncode)
        return
    # Background desktop wrapper owns a nested kill-on-close Job. Its nearest
    # Job query cannot see the verified outer memory Job; retain the parent's
    # explicit pre-background memory guard alongside the launcher receipt.
    job=json.loads((TASK/'prepare-review/scope-probe-parent-job.json').read_text('utf-8'))
    out=TASK/'prepare-review/scope-verifier-probe01';assert not out.exists();out.mkdir()
    source=out/'src';(source/'cn/release').mkdir(parents=True)
    (source/'cn/release/ProbeHelper.as').write_text(SHELL,encoding='utf-8');(source/'Main.as').write_text(MAIN,encoding='utf-8')
    base=out/'original.swf'
    cmd=['java','-Dflexlib='+str(SDK/'frameworks'),'-jar',str(SDK/'lib/mxmlc-cli.jar'),'+configname=air',
        '-swf-version=44','-target-player=32.0','-compiler.float=false','-debug=true',
        '-compiler.source-path='+str(source),'-output='+str(base),str(source/'Main.as')]
    run=subprocess.run(cmd,cwd=out,capture_output=True,timeout=60);(out/'mxmlc.log').write_bytes(run.stdout+run.stderr)
    assert run.returncode==0,('mxmlc failed',run.returncode)
    raw=base.read_bytes();results=[]
    for mode,correct in [('negative',False),('positive',True)]:
        swf=out/(mode+'.swf');swf.write_bytes(patch_swf(raw,correct))
        app=out/(mode+'.xml');app.write_text('''<?xml version="1.0" encoding="utf-8"?>
<application xmlns="http://ns.adobe.com/air/application/51.2"><id>cn.release.scopeprobe</id>
<versionNumber>1.0</versionNumber><filename>scopeprobe</filename>
<initialWindow><content>'''+swf.name+'''</content><visible>false</visible><width>10</width><height>10</height></initialWindow></application>''',encoding='utf-8')
        command=[str(SDK/'bin/adl.exe'),'-nodebug',str(app)]
        result=subprocess.run(command,cwd=out,capture_output=True,timeout=30)
        log=result.stdout+result.stderr;(out/(mode+'.log')).write_bytes(log)
        text=log.decode('utf-8',errors='replace')
        results.append(dict(mode=mode,exit_code=result.returncode,log=text))
    assert 'SCOPE_PROBE_ERROR 1058' in results[0]['log'],results[0]
    assert 'SCOPE_PROBE_OK' in results[1]['log'] and 'SCOPE_PROBE_ERROR' not in results[1]['log'],results[1]
    report=dict(status='receiver_scope_negative_and_positive_executed',results=results,bounded_job=job,
        scope_shape=dict(negative=['original_receiver'],positive=['static_helper_class','original_receiver']),
        game_or_ios_native_executed=False,device_tested=False)
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
