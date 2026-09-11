"""Complete the public cumulative APK from pinned public and latest LAN inputs.

The current login SWF supplies all cumulative behavior. Exactly one endpoint
constant changes; the accepted public APK supplies the verified identical
native shell. No AIR desktop runtime, install, deployment, or registry update.
"""
from pathlib import Path
import argparse,copy,importlib.util,json,sys,uuid,zipfile

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
package=module('public_login_packager',HERE/'package_apk.py')
common=package.common
sys.path.insert(0,str(HERE.parent/'lens0907-0908'))
import build_swf as g
from swfabc import swftags

LAN_UUID='88472c39-ba54-42fa-bfc0-a34e7fd34aea'
LAN_SWF_SHA='c667815ff871e12705e665267640db480f7c959e1c6bb4d852016f1e4923d6ed'
PUBLIC_APK_SHA='c868534b575348dde825fcd4c88c156157174fd4444724f1141fd9aa95e32a2d'
LAN_PARENT_SHA='fd42a417dc7231c8dbc421e4839ceeefcfb027f8c83d8bc418baa427dd0b969d'

def dump(p,o):p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n','utf8')

def main(args):
    w=args.work.resolve();out=args.out.resolve()
    assert not w.exists() and not out.exists(),'fresh work and output directories required'
    assert '.cdn' not in w.parts and '.cdn' not in out.parts
    public=package.checker.verify('public');lan=package.checker.verify('lan')
    assert public['apk_sha256']==PUBLIC_APK_SHA and lan['apk_sha256']==LAN_PARENT_SHA,'baseline advanced: re-audit cumulative chain'
    client=json.loads((HERE/'integration-files.json').read_text('utf8'))['client']
    candidate=REPO/client['apk'];assert common.sha256(candidate)==client['apk_sha256']
    assert common.sha256(REPO/client['helper_source'])==client['helper_source_sha256']
    with zipfile.ZipFile(candidate) as z:
        source=z.read(common.SWF_MEMBER);manifest=z.read(common.MANIFEST_MEMBER)
    assert g.sha(source)==LAN_SWF_SHA and manifest.count(LAN_UUID.encode('utf-16le'))==1
    base=Path(public['apk'])
    # Native libraries, assets, package/version/storage identity are equal.
    with zipfile.ZipFile(base) as a,zipfile.ZipFile(candidate) as b:
        names=set(a.namelist())-common.SIGNATURE_MEMBERS
        assert names==set(b.namelist())-common.SIGNATURE_MEMBERS
        for n in names-{common.SWF_MEMBER,common.MANIFEST_MEMBER}:assert a.read(n)==b.read(n),('native shell mismatch',n)
        assert a.read(common.MANIFEST_MEMBER).replace(public['uniqueappversionid'].encode('utf-16le'),LAN_UUID.encode('utf-16le'))==manifest
        before=a.read(common.SWF_MEMBER)
    w.mkdir(parents=True);out.mkdir(parents=True)
    (w/'latest-login-lan.swf').write_bytes(source);(w/'accepted-public.swf').write_bytes(before)
    v=g.View(g.SwfAbc(w/'latest-login-lan.swf'),g.asm);original=copy.deepcopy(v.a)
    pv=g.View(g.SwfAbc(w/'accepted-public.swf'),g.asm)
    body=92013;label='pinball.config.gbits::DevConfig_gf_android/<ctor>'
    assert v.labels[v.a.bodies[body][0]]==pv.labels[pv.a.bodies[body][0]]==label
    instructions=g.asm.decode(v.a.bodies[body][5]);assert instructions[11].op==0x2c
    index=instructions[11].args[0];local=lan['endpoint'].split('://',1)[1]
    host=public['endpoint'].split('://',1)[1]
    assert v.a.strings[index]==local.encode()
    uses=[]
    for bi,b in enumerate(v.a.bodies):
        for ii,ins in enumerate(g.asm.decode(b[5])):
            if ins.op in (0x2c,0x06,0xf1) and ins.args[0]==index:uses.append((bi,ii))
            if ins.op==0xef and ins.args[1]==index:uses.append((bi,ii))
    assert uses==[(body,11)],('endpoint string has another code use',uses)
    # Rewrite the address in place, keeping every bytecode instruction intact
    # and avoiding an unused private LAN address in the public SWF pool.
    v.a.strings[index]=host.encode()
    for name in ('ints','uints','doubles','namespaces','ns_sets','multinames','methods','metadata','instances','classes','scripts','bodies'):
        assert g.freeze(getattr(original,name))==g.freeze(getattr(v.a,name)),name
    assert [i for i,(a,b) in enumerate(zip(original.strings,v.a.strings)) if a!=b]==[index]
    assert v.normalized(body)==pv.normalized(body),'public constructor behavior differs'
    swf=w/'player-login-public.swf';v.swf.save(swf)
    final=g.View(g.SwfAbc(swf),g.asm)
    assert final.a.serialize()==v.a.serialize()
    assert local.encode() not in swftags.load_swf(str(swf))[3],'LAN host remains in public payload'
    def tags(path):
        _,_,_,data=swftags.load_swf(str(path));return [data[o:o+h+n] for c,o,h,n in swftags.iter_tags(data)]
    left,right=tags(w/'latest-login-lan.swf'),tags(swf)
    assert len(left)==len(right) and sum(a!=b for a,b in zip(left,right))==1
    # Check the full old-public -> current behavior delta, in addition to the
    # exact LAN-to-public identity proof. Existing cumulative methods survive.
    changed=[i for i,(a,b) in enumerate(zip(pv.a.bodies,final.a.bodies)) if g.freeze(a)!=g.freeze(b)]
    expected=[7174,21496,29697,31405,37085,56844,58882,59846,71835,77176,78350,82500,82502,92013,92450]
    assert changed==expected,(changed,expected)
    assert len(pv.a.bodies)==len(final.a.bodies)==92561
    helpers=[];total=0
    _,_,_,raw=swftags.load_swf(str(swf))
    for code,o,h,n in swftags.iter_tags(raw):
        if code!=82:continue
        data=raw[o+h:o+h+n];nul=data.index(b'\0',4);a=g.abcfmt.ABC(data[nul+1:]);total+=len(a.bodies)
        name=data[4:nul].decode()
        if name.startswith('cn.'):helpers.append(dict(name=name,methods=len(a.bodies),sha256=g.sha(data[nul+1:])))
    assert total==96515 and [x['methods'] for x in helpers]==[5,13,93]
    java=Path(r'D:\java\bin\java.exe');ffdec=Path(r'F:\codex\tools\ffdec_26.2.1\ffdec.jar');bt=Path(r'F:\StartPointCN\wf_full_patch\build-tools')
    classes=w/'java';classes.mkdir()
    package.run([java.with_name('javac.exe'),'-cp',ffdec,'-d',classes,HERE.parent/'character-carousel/CompareMethodBodies.java'])
    check=package.run([java,'-Xmx2g','-cp',str(classes)+';'+str(ffdec),'CompareMethodBodies',w/'latest-login-lan.swf',swf],capture=True)
    assert 'method_bodies=96515' in check and 'changed_count=0' in check,check
    (w/'ffdec-verification.log').write_text(check,'utf8')
    uid=str(uuid.uuid4());unsigned=w/'unsigned.apk';aligned=w/'aligned.apk'
    apk=out/'StarPoint-CN-1.8.1-player-login-abyss-lens-public-20260911.apk'
    common.replace_apk(base,swf,unsigned,uid,base_uuid=public['uniqueappversionid'])
    package.run([bt/'zipalign.exe','-p','4',unsigned,aligned])
    package.run(['powershell.exe','-NoProfile','-NonInteractive','-File',HERE.parent/'lens0907-0908/sign_apk.ps1',
        '-InputApk',aligned,'-OutputApk',apk,'-ApkSigner',bt/'lib/apksigner.jar','-Java',java])
    verified=common.verify(base,apk,swf,uid,java,bt/'lib/apksigner.jar',base_uuid=public['uniqueappversionid'])
    package.run([bt/'zipalign.exe','-c','-p','4',apk])
    verified.update(status='offline_verified_public_cumulative_candidate',apk=str(apk),endpoint=public['endpoint'],resource_version='1.4.104',
        public_baseline=public,latest_login_input_sha256=client['apk_sha256'],latest_login_swf_sha256=LAN_SWF_SHA,
        native_shell_equal_to_latest_login=True,changed_endpoint_string_index=index,all_latest_login_method_bytes_unchanged=True,
        public_ancestor_changed_body_indexes=changed,main_abc_index=287,all_abc_method_bodies=total,helpers=helpers,
        original_storage_unchanged=True,other_apk_members_unchanged=True,zipalign=True,v1_signature=True,v2_signature=True,
        cloud_deployed=False,device_tested=False,accepted_registry_changed=False,desktop_air_run=False)
    dump(out/'verification-report.json',verified)
    (out/(apk.name+'.sha256')).write_text(verified['apk_sha256']+'  '+apk.name+'\n','utf8')
    for p in (unsigned,aligned):assert p.resolve().parent==w;p.unlink()
    print(json.dumps({'apk':str(apk),'sha256':verified['apk_sha256'],'endpoint':public['endpoint'],'methods_checked':total},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
