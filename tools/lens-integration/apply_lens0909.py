"""Apply a verified 0909 candidate locally; no runtime mirror or cloud writes."""
import argparse, io, json, zipfile
from pathlib import Path
import prepare_content as p

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,required=True);w=ap.parse_args().work.resolve()
    assert not w.is_relative_to((p.REPO/'.cdn').resolve())
    c=p.Chain();prepared=p.readj(w/'prepare-report.json');accepted=p.readj(w/'acceptance-report.json')
    assert c.tail=='1.4.102' and p.sha(c.manifest_bytes)==prepared['baseline_manifest_sha256']
    assert accepted['status']=='passed'
    assert accepted['resources_inventory_sha256']==p.sha((w/'resources.json').read_bytes())
    assert accepted['server_inventory_sha256']==p.sha((w/'server-files.json').read_bytes())
    resources=p.readj(w/'resources.json');servers=p.readj(w/'server-files.json');payloads={};writes={}
    for row in resources:
        key=row['root'],row['rel'];assert p.hrel(row['logical'])==row['rel']
        raw=(w/'resources'/p.ROOTS[row['root']]/row['rel']).read_bytes();old=c.get(key)
        assert p.sha(raw)==row['sha256'] and (p.sha(old) if old else None)==row['before_sha256']
        member=p.member(key);assert member==row['member']
        payloads[member]=raw;writes['assets/asset-patch/'+member]=raw
    for row in servers:
        raw=(w/'server'/row['path']).read_bytes()
        assert p.sha(raw)==row['sha256'] and p.sha((p.REPO/row['path']).read_bytes())==row['before_sha256']
        writes[row['path']]=raw
    archive_name='pinball-1.4.102-1.4.103-1-lens0909-cn.zip'
    archive_rel='assets/asset-patch/active/'+archive_name
    assert not (p.REPO/archive_rel).exists()
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for member,raw in sorted(payloads.items()):
            info=zipfile.ZipInfo(member,(2026,9,9,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,raw)
    archive=buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert z.testzip() is None and z.namelist()==sorted(payloads)
        for member,raw in payloads.items():assert z.read(member)==raw
    integrity={'name':archive_name,'size':len(archive),'sha256':p.sha(archive),'members':len(payloads),'files':sorted(payloads)}
    audit_rel='assets/asset-patch/audit/lens0909-1.4.103';assert not (p.REPO/audit_rel).exists()
    manifest=json.loads(c.manifest_bytes)
    manifest['patches'].append({'id':'lens0909-1.4.103','type':'patch','name':'0909 角色与五重调整',
        'description':'角色调整、夏日白零权重展示、五重血量与试炼；嫉妒隔离，保留我方规则和单人原生折减。',
        'version':'1.4.103','depends_on':'1.4.102','enabled':True,'archive':archive_name,'archive_size':len(archive),
        'chain':[archive_name],'archive_integrity':[integrity],'files':sorted(payloads),'created_at':'2026-09-09',
        'local_test_only':False,'audit':{'directory':audit_rel,'report':'report.json'}})
    manifest['cdn_version']='1.4.103'
    writes[archive_rel]=archive
    audit={'status':'local_implementation_validated_device_acceptance_pending','archive':integrity,
        'manifest_before_sha256':p.sha(c.manifest_bytes),'acceptance':accepted,
        'remaining_device_checks':['角色技能与水杰拉尔立绘','嫉妒主怪与随从试炼','双人/三人换关及断线恢复'],
        'scope':'本地未提交；未同步运行镜像、未部署云服；没有修改 APK/IPA/SWF。'}
    writes[audit_rel+'/report.json']=(json.dumps(audit,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    for name in ('resources.json','server-files.json','boss-hp-adjustments.json','watch-aliases.json','resource-decisions.json','ios-pairs.json'):
        writes[audit_rel+'/'+name]=(w/name).read_bytes()
    writes['assets/asset-patch/manifest.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    # Check every resolved destination and preserve each old byte before writes.
    for rel in writes:
        path=(p.REPO/rel).resolve()
        assert path.is_relative_to(p.REPO.resolve()) and not path.is_relative_to((p.REPO/'.cdn').resolve())
        if path.exists():
            backup=w/'applied-before'/rel;backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(path.read_bytes())
    assert (p.REPO/'assets/asset-patch/manifest.json').read_bytes()==c.manifest_bytes
    delivery=[]
    for rel,raw in writes.items():
        path=p.REPO/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        assert path.read_bytes()==raw;delivery.append({'path':rel,'sha256':p.sha(raw)})
    # Read through the same active-chain resolver after applying the edge.
    after=p.Chain();assert after.tail=='1.4.103'
    for row in resources:assert p.sha(after.get((row['root'],row['rel'])))==row['sha256']
    p.savej(w/'local-delivery.json',delivery)
    print(json.dumps({'version':after.tail,'resources':len(resources),'server_files':len(servers),'local_files':len(delivery),'archive_bytes':len(archive)}))

if __name__=='__main__':main()
