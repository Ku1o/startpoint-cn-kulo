"""Deliver only this batch's 117 resources and the complete private admission pair."""
import datetime,os,shutil,zipfile
from common import *
DEST=Path('F:/codex/outputs/server-overlays/author-public-1.4.117-20260924')
LEDGER=Path('F:/codex/.codex/starpoint-cloud-delivery.json')
ARCHIVE='assets/asset-patch/active/pinball-1.4.116-1.4.117-1-author-inaho-fluffy-consolidated.zip'
HASHES={ARCHIVE:'52beab7461f750dc2a386f6f30a1873b606b2724b28e27af148e32aaad70b555',
        'assets/gacha.json':'a325d55bff3ac11e91d3af7fda3451743b8b68ecef14bc94876dcc4208a2d3be',
        'assets/gacha_cnmod.json':'5a80fc25b0b0eef8a14b214e7789d81b4a232e7d560c65eb4a3f35b568adfae4',
        'assets/cdndata/character_text.json':'f07663bc806904161d305f4506ffb5379d519bba8d873492ac35f3ab2b6db70d'}

def main():
    assert DEST.is_dir(), 'Create and verify the restricted delivery directory first.'
    output=DEST/'startpoint-cn-cloud-overlay-author-public-1.4.117-20260924.zip'
    assert not output.exists(),'Do not overwrite an existing delivery silently.'
    apk=json.loads((OUT/'android/package-report.json').read_text('utf8'))
    ios=json.loads((OUT/'ios/verification-report.json').read_text('utf8'))
    protocol=json.loads((WORK/'protocol/report.json').read_text('utf8'))
    rules=json.loads((OUT/'ios/rules-verification.json').read_text('utf8'))
    assert apk['status']==ios['status']=='offline_verified_public_candidate' and protocol['passed'] and rules['passed']
    for path,key in ((apk['apk'],apk['apk_sha256']),(ios['ipa'],ios['ipa_sha256'])):assert sha(Path(path).read_bytes())==key
    policy,keys=pair();batch=json.loads((PAIR/'batch.json').read_text('utf8'))
    assert sha((PRIVATE/'config/client-admission.json').read_bytes())==batch['previous_policy_sha256'],'Master policy changed during build'
    assert sha((PRIVATE/'config/client-admission.keys.json').read_bytes())==batch['previous_keys_sha256'],'Master keys changed during build'
    baseline=json.loads(LEDGER.read_text('utf8'))
    assert baseline['latest_delivery']['batch']=='author-abyss-inaho-1.4.116-20260924-014013'
    dump(PAIR/'before/cloud-delivery.json',baseline)
    manifest_path=ROOT/'assets/asset-patch/manifest.json'
    manifest=json.loads(manifest_path.read_text('utf8'))
    last,=[p for p in manifest['patches'] if p['id']=='author-inaho-fluffy-consolidated-117-20260924']
    assert last['enabled'] and last['local_test_only'] is False and last['version']=='1.4.117' and last['depends_on']=='1.4.116'
    assert last['archive']==Path(ARCHIVE).name and last['archive_integrity'][0]['sha256']==HASHES[ARCHIVE]
    # Removing the formal-release marker must recover the frozen LAN manifest.
    restored=manifest_path.read_text('utf8').replace('"id": "author-inaho-fluffy-consolidated-117-20260924"',
                                                         '"id": "author-inaho-fluffy-consolidated-117-20260924"',1)
    at=restored.index('"id": "author-inaho-fluffy-consolidated-117-20260924"')
    prefix,tail=restored[:at],restored[at:]
    restored=prefix+tail.replace('"local_test_only": false','"local_test_only": true',1)
    assert sha(restored.encode('utf8'))=='c464058e43152fb7ff9bd401e98e39bf5838818bfec899299ce1c8ca0d1678e8'
    sources={name:ROOT/name for name in HASHES}
    sources['assets/asset-patch/manifest.json']=manifest_path
    for name in ('client-admission.json','client-admission.keys.json'):sources['config/'+name]=PAIR/'config'/name
    for name,expected in HASHES.items():assert sha(sources[name].read_bytes())==expected,name
    with zipfile.ZipFile(sources[ARCHIVE]) as inner:
        assert len(inner.namelist())==2072 and inner.testzip() is None
        assert all(n.startswith('production/') for n in inner.namelist())
    rows=[]
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        for name,path in sorted(sources.items()):
            assert ':' not in name and not name.startswith('/') and '..' not in Path(name).parts
            assert not name.startswith(('production/','assets/asset-patch/production/','.cdn/'))
            raw=path.read_bytes();z.writestr(name,raw)
            rows.append({'path':name,'bytes':len(raw),'sha256':sha(raw)})
    with zipfile.ZipFile(output) as z:
        assert set(z.namelist())==set(sources) and len(z.namelist())==7 and z.testzip() is None
        for name,path in sources.items():assert z.read(name)==path.read_bytes(),name
    timestamp=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds')
    record={'batch':'author-public-1.4.117-20260924','created_at':timestamp,'archive':str(output),
            'sha256':sha(output.read_bytes()),'size':output.stat().st_size,'file_count':7,'files':rows,
            'baseline_batch':baseline['latest_delivery']['batch'],'baseline_commit':baseline['latest_delivery']['included_through_commit'],
            'source_status':'verified_local_candidate_uncommitted','cdn_from':'1.4.116','cdn_to':'1.4.117',
            'cloud_deployment_status':'not_deployed_by_this_task','cloud_deployed_by_this_task':False,
            'next_batch_assumes_this_delivery_covered':True,'admission_pair_included':True,'new_ids':IDS,
            'old_allowed_ids_retained':OLD_IDS,'loose_production_included':False,'changelog_included':False,
            'save_schema_changed':False,'payloads_verified':True}
    dump(DEST/'package-report.json',record)
    (DEST/(output.name+'.sha256')).write_text(record['sha256']+'  '+output.name+'\n',encoding='utf8')
    (DEST/'files.txt').write_text('\n'.join(r['path'] for r in rows)+'\n',encoding='utf8')
    note='''StarPoint CN 公网客户端与 1.4.117 配套（私有服务器文件）

适用基线：上一个正式交付的 1.4.116 整合包已覆盖。
范围：本批合并 1.4.117、两组兑换池、稻穗文字和完整双端准入配对，共 7 个文件。
仅本地候选交付；未提交 Git，未连接、覆盖或重启云服务器。

部署：
1. 备份 files.txt 中云服现有文件，尤其是两个 config/client-admission 文件。
2. 将 ZIP 解压覆盖到服务端项目根目录，保持 assets/ 和 config/ 路径。
3. 两个 config 文件必须使用同批配对，先写入 keys 文件，再写入名单。
4. 重启服务端以统一加载游戏数据和资源配置；无需安装依赖、编译或迁移数据库。
5. 确认标题资源版本 1.4.117，然后测试两端新客户端登录。

新增准入号：
Android：android-181-author-1043-20260924
iOS：ios-184-author-1043-20260924
现有 independent-party 双端旧号、旧密钥及 enforce=true 保持，未设置额外淘汰期限。
单独的准入文件每约 2 秒热加载；本批其他游戏数据仍建议按第 4 步重启。
配套未覆盖前，新准入号不能登录云服。IPA 为 TrollStore unsigned，完成离线检查，未真机测试。

回退：恢复本次备份的全部文件后重启；旧客户端成品已保留。
本批不提供旧 1.4.117/118/119 测试缓存的迁移；资源合并按新安装或既定缓存基线测试。
外层不含松散 production、.cdn、签名材料或 changelog；内层 CDN ZIP 原样保留。
本包包含准入密钥，只交给服务器管理员，不作为玩家下载包。
'''
    (DEST/'部署说明.txt').write_text(note,encoding='utf8')
    # Publish the complete verified pair to the private master, keys first.
    for name in ('client-admission.keys.json','client-admission.json'):
        target=PRIVATE/'config'/name;temp=target.with_suffix(target.suffix+'.author.tmp')
        assert not temp.exists();temp.write_bytes((PAIR/'config'/name).read_bytes());os.replace(temp,target)
    registry=json.loads((PRIVATE/'registry.json').read_text('utf-8-sig'))
    registry['builds']=policy['builds'];registry['enforce']=policy['enforce']
    for name in ('client-admission.json','client-admission.keys.json'):
        registry['files'][name]={'path':str(PRIVATE/'config'/name),'sha256':sha((PRIVATE/'config'/name).read_bytes())}
    registry['artifacts']['android']={'path':apk['apk'],'sha256':apk['apk_sha256'],'build_id':IDS['android'],'status':apk['status']}
    registry['artifacts']['ios']={'path':ios['ipa'],'sha256':ios['ipa_sha256'],'build_id':IDS['ios'],'status':ios['status']}
    registry['artifacts']['android_lan']={'path':str(APK),'sha256':APK_SHA,'build_id':OLD_IDS['android'],'status':'user_accepted'}
    registry['latest_delivery']=str(output)
    registry['client_release_delivery']={'release':record['batch'],'private_archive':str(output),'sha256':record['sha256'],
        'files':[r['path'] for r in rows],'old_allowed_ids_retained':OLD_IDS,'cloud_deployed':False,
        'scope':'full 117 resource and admission delivery after formal 116 baseline','does_not_replace_general_server_overlay':False}
    registry['last_admission_change']={'batch':record['batch'],'timestamp':timestamp,'new_ids':IDS,'old_ids_retained':OLD_IDS,'status':'prepared_not_deployed'}
    registry['cloud_deployment_status']='current_batch_not_deployed_by_this_task'
    registry['local_runtime_verified']=False
    dump(PRIVATE/'registry.json',registry)
    batch.update(status='delivered_not_deployed',master_updated=True,private_archive=str(output),private_archive_sha256=record['sha256'])
    dump(PAIR/'batch.json',batch);dump(PAIR/'package-report.json',record)
    baseline['previous_delivery']=baseline['latest_delivery'];baseline['latest_delivery']=record
    dump(LEDGER,baseline)
    public={'batch':record['batch'],'android':registry['artifacts']['android'],'ios':registry['artifacts']['ios'],
            'previous_ids':OLD_IDS,'new_ids':IDS,'resource_version':'1.4.117','private_server_archive':str(output),
            'private_server_archive_sha256':record['sha256'],'cloud_deployed':False,'device_tested_this_batch':False}
    dump(OUT/'release.json',public);dump(HERE/'release.json',public)
    shutil.copyfile(WORK/'protocol/report.json',OUT/'protocol-verification.json')
    print(json.dumps({k:record[k] for k in ('batch','archive','sha256','file_count','cdn_from','cdn_to','cloud_deployment_status')}))

if __name__=='__main__':main()
