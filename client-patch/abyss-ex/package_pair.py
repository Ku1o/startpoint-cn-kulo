"""Deliver the complete private pair after both actual client artifacts verify."""
from release_common import *
import datetime, shutil, zipfile

def main():
    android=read(OUT/'android-build-report.json');ios=read(OUT/'ios-build-report.json')
    checked=read(OUT/'ios-verification-report.json');protocol=read(PAIR/'protocol-verification.json')
    assert android['status']=='offline_verified' and checked['status']=='offline_verified_unsigned_candidate'
    assert checked['ipa_sha256']==ios['ipa_sha256'] and protocol['passed'] and protocol['checks']==24
    assert sha(Path(android['apk']).read_bytes())==android['sha256']
    assert sha(Path(ios['ipa']).read_bytes())==ios['ipa_sha256']
    assert android['build_id']==IDS['android'] and ios['build_id']==IDS['ios']
    assert not (PAIR/'server-files.zip').exists(), 'An existing delivery requires explicit same-batch replacement handling.'
    # No other task's private policy updates may be overwritten unnoticed.
    for name in ('client-admission.json','client-admission.keys.json'):
        assert (PRIVATE/'config'/name).read_bytes()==(PAIR/'before'/name).read_bytes(), 'Master pair changed; reconcile before delivery.'
    policy=read(PAIR/'config/client-admission.json');keys=read(PAIR/'config/client-admission.keys.json')
    before=read(PAIR/'before/client-admission.json');oldkeys=read(PAIR/'before/client-admission.keys.json')
    assert policy['enforce']==before['enforce'] and policy['updateMessage']==before['updateMessage']
    assert policy['builds'][:len(before['builds'])]==before['builds']
    assert all(keys.get(k)==v for k,v in oldkeys.items())
    assert set(keys)-set(oldkeys)==set(IDS.values())
    assert all(keys.get(row['id']) for row in policy['builds'])
    del keys,oldkeys
    members={
        'config/client-admission.json':(PAIR/'config/client-admission.json').read_bytes(),
        'config/client-admission.keys.json':(PAIR/'config/client-admission.keys.json').read_bytes(),
        'tools/activate-abyss-ex-admission.cjs':(HERE/'activate-admission.cjs').read_bytes(),
    }
    archive=PAIR/'server-files.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in members.items():z.writestr(name,data)
    with zipfile.ZipFile(archive) as z:
        assert set(z.namelist())==set(members) and z.testzip() is None
        for name,data in members.items():assert z.read(name)==data
    manifest={name:dict(bytes=len(data),sha256=sha(data)) for name,data in members.items()}
    dump(PAIR/'server-files.manifest.json',manifest)
    (PAIR/'server-files.sha256.txt').write_text(sha(archive.read_bytes())+'  server-files.zip\n','utf8')
    notes='''深渊 EX 双端客户端准入配套（私有服务器文件，不发给玩家）

本包仅更新完整准入配置与启用工具，不包含深渊 EX 服务端功能或 CDN 分包。
基于服务器已具备现有双平台 ClientAdmission 协议；不改变 enforce 或现有其他条目。
正式客户端启用前，需先准备对应 EX 服务端和 1.4.110 第二分包。

1. 备份服务器 config/client-admission.json 和 config/client-admission.keys.json。
2. 将 server-files.zip 解压到服务器项目根覆盖；完整名单和密钥已合并，无须手工合并。
3. 在正式向玩家开放这批客户端时，于服务器项目根运行：
   node tools/activate-abyss-ex-admission.cjs . both
   两端分开发放时，最后参数分别使用 android 或 ios。

第 3 步从实际启用时刻起为该平台旧号保留 24 小时。
单纯解压只允许新旧客户端并存，不会提前启动淘汰计时。
启用工具会在 config/abyss-ex-admission-activation.json 留下期限；重复运行不延长期限。
现有准入实现约每 2 秒热加载配置，配对配置本身不需要重启。
新号 android-181-abyss-ex-20260917 / ios-184-abyss-ex-20260917 长期允许；
旧号 android-181-r10-20260915 / ios-184-admission-20260915 在各自期限到达后拒绝。

仅在本地完成配置、真实协议类的离线验证；未上传、覆盖或重启云服。
回退：恢复第 1 步的两份完整配置。保留启用记录，以免再次启用时延长期限。
若云端另有手工准入改动，应先将差异同步回本地完整主记录再生成后续覆盖包。
'''
    (PAIR/'部署说明.txt').write_text(notes,'utf8')
    # Persist a complete paired master only after both clients and protocol pass.
    for name in ('client-admission.keys.json','client-admission.json'):
        target=PRIVATE/'config'/name;temp=target.with_suffix(target.suffix+'.ex.tmp')
        temp.write_bytes((PAIR/'config'/name).read_bytes());temp.replace(target)
    registry=read(PRIVATE/'registry.json')
    registry['builds']=policy['builds']
    registry['files']={name:dict(path=str(PRIVATE/'config'/name),sha256=sha((PRIVATE/'config'/name).read_bytes()))
                       for name in ('client-admission.json','client-admission.keys.json')}
    registry['artifacts']['android']=dict(path=android['apk'],sha256=android['sha256'],build_id=IDS['android'],status='offline_verified_candidate')
    registry['artifacts']['ios']=dict(path=ios['ipa'],sha256=ios['ipa_sha256'],build_id=IDS['ios'],status='offline_verified_unsigned_candidate')
    registry['client_release_delivery']=dict(release='abyss-ex-20260917',private_archive=str(archive),
        sha256=sha(archive.read_bytes()),files=sorted(members),grace_seconds=86400,grace_status='awaiting_server_activation',
        cloud_deployed=False,scope='client_admission_only',does_not_replace_general_server_overlay=True)
    registry['last_packaging_update']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    dump(PRIVATE/'registry.json',registry)
    state=read(PAIR/'release-state.json');state.update(status='offline_verified_delivered',cloud_deployed=False,
           grace_status='awaiting_server_activation',artifacts=registry['artifacts'],server_files=registry['client_release_delivery'])
    dump(PAIR/'release-state.json',state)
    # Full compiler metadata is required to extend this cumulative IPA later.
    shutil.copyfile(WORK/'abyss-ex-full.abc',OUT/'abyss-ex-ios-full.abc')
    shutil.copyfile(WORK/'port.json',OUT/'ios-port.json')
    shutil.copyfile(PAIR/'protocol-verification.json',OUT/'admission-verification.json')
    (OUT/'SHA256.txt').write_text(''.join(digest+'  '+Path(name).name+'\n' for name,digest in
        ((android['apk'],android['sha256']),(ios['ipa'],ios['ipa_sha256']),
         (str(OUT/'abyss-ex-ios-full.abc'),sha((OUT/'abyss-ex-ios-full.abc').read_bytes())))),'utf8')
    print('Complete private pair delivered; two new IDs; old deadlines await actual server activation.')
    print(str(archive))

if __name__=='__main__':main()
