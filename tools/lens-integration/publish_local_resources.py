"""Activate the verified sparse content as a local Android test update.

This creates resource archives, not a cloud-server overlay or deployment.
"""
import argparse
import io
import json
import re
import zipfile
from pathlib import Path
import prepare_content as p
import wf_dsl,wf_dsl_sig
from wf_siete_balance import _normalize_for_signature


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,required=True)
    w=ap.parse_args().work.resolve();chain=p.Chain()
    prepared=p.readj(w/'prepare-report.json')
    assert p.sha(chain.manifest_bytes)==prepared['baseline_manifest_sha256']
    terrain=p.readj(w/'five-boss-terrain-audit-v2.json')
    assert terrain['status']=='passed' and terrain['scene_count']==22
    inventory=p.readj(w/'resources.json');assert len(inventory)==407
    expected_unknown={
        '5c/0e9dccdb73bee640ddb02b8a676a7f0b9d00e8':'5d3919bcdb8407ede2ea1c79d83954c6b09824b1ee77194726d6400819c0df40',
        'f9/0fcac59f40ad44525d7a824a26dc3aa6cb1d81':'64494127c984a79388194b7e09f87693613f682c5a62e7b82af08f2dcf903be6'}
    sources=p.readj(w/'source-receipts.json')
    donor_archives=[]
    for source in sources:
        path=Path(source['path'])
        if path.suffix=='.zip':
            assert p.sha(path.read_bytes())==source['sha256']
            donor_archives.append(path)
    unknown=[];payloads={}
    for row in inventory:
        assert re.fullmatch(r'[a-f0-9]{2}/[a-f0-9]{38}',row['rel'])
        key=(row['root'],row['rel']);member=p.member(key)
        blob=(w/'resources'/p.ROOTS[row['root']]/row['rel']).read_bytes()
        assert p.sha(blob)==row['sha256'];old=chain.get(key)
        assert (p.sha(old) if old is not None else None)==row['before_sha256']
        if not row['logical']:
            assert row['root']=='common' and old is None
            assert p.sha(blob)==expected_unknown[row['rel']]
            matching=[]
            for path in donor_archives:
                with zipfile.ZipFile(path) as z:
                    if member in z.namelist() and z.read(member)==blob:matching.append(str(path))
            assert matching,'unknown payload lacks exact donor provenance'
            tree=wf_dsl.parse_dsl(p.wf_atf.inflate(blob))['tree']
            wf_dsl_sig.validate_action_dsl(_normalize_for_signature(tree,row['rel']))
            unknown.append({'member':member,'sha256':p.sha(blob),'donor_archives':matching,
                'logical_name':'unresolved','existing_resource_overwrite':False,'dsl_signature':'passed'})
        payloads[member]=blob
    assert len(unknown)==2
    base=chain.tail;v=list(map(int,base.split('.')));v[-1]+=1;target='.'.join(map(str,v))
    name=f'pinball-{base}-{target}-1-lens0907-0908-local-android.zip'
    folder=p.REPO/'assets/asset-patch';archive=folder/'active'/name
    audit=folder/'audit'/f'lens0907-0908-{target}'
    assert not archive.exists() and not audit.exists()
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for member,blob in sorted(payloads.items()):
            info=zipfile.ZipInfo(member,(2026,9,8,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,blob)
    raw=buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert z.testzip() is None and z.namelist()==sorted(payloads)
        for member,blob in payloads.items():
            stored=z.read(member);assert stored==blob
            if stored[1:4] in (b'png',b'PNG'):
                p.Image.open(io.BytesIO(p.wf_assets.png_decode_stored(stored))).load()
    integrity={'name':name,'size':len(raw),'sha256':p.sha(raw),'members':len(payloads),'files':sorted(payloads)}
    record={'id':f'lens0907-0908-{target}','type':'patch','name':f'0907+0908 安卓本地联调 {target}',
        'description':'新增角色与改版、五重决战、兑换和武器；尚待真机与 iOS 验收。',
        'version':target,'depends_on':base,'enabled':True,'archive':name,'archive_size':len(raw),
        'chain':[name],'archive_integrity':[integrity],'files':sorted(payloads),
        'created_at':'2026-09-08','local_test_only':True,'required_local_platform':'android',
        'audit':{'directory':audit.relative_to(p.REPO).as_posix(),'report':'report.json'}}
    manifest=json.loads(chain.manifest_bytes);manifest['patches'].append(record);manifest['cdn_version']=target
    output=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    audit.mkdir(parents=True)
    (audit/'manifest.before.json').write_bytes(chain.manifest_bytes)
    report={'status':'local_android_test_only','base_version':base,'target_version':target,'archive':integrity,
        'manifest_before_sha256':p.sha(chain.manifest_bytes),'manifest_after_sha256':p.sha(output),
        'terrain_closure':terrain,'terrain_repair':p.readj(w/'terrain-fix-receipt.json'),
        'unmapped_payloads':unknown,'remaining':['device_gameplay_acceptance','ios_runtime_port','unmapped_logical_names'],
        'rules':'User authorized local sync/run for Android testing; this is not a cloud release.'}
    p.savej(audit/'report.json',report)
    archive.write_bytes(raw);assert p.sha(archive.read_bytes())==integrity['sha256']
    delivery=[archive.relative_to(p.REPO).as_posix()]
    for member,blob in payloads.items():
        path=folder/member
        assert path.resolve().is_relative_to(p.REPO.resolve())
        assert not path.resolve().is_relative_to((p.REPO/'.cdn').resolve())
        before=path.read_bytes() if path.exists() else None
        if before is not None:
            backup=w/'loose-resource-before'/member;backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(before)
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(blob)
        delivery.append(path.relative_to(p.REPO).as_posix())
    assert (folder/'manifest.json').read_bytes()==chain.manifest_bytes
    (folder/'manifest.json').write_bytes(output)
    delivery.append('assets/asset-patch/manifest.json')
    p.savej(w/'local-resource-delivery.json',[{'path':name,'sha256':p.sha((p.REPO/name).read_bytes())} for name in delivery])
    print(json.dumps({'version':target,'resources':len(payloads),'zip_bytes':len(raw),'sha256':integrity['sha256'],'unmapped_names':len(unknown)}))


if __name__=='__main__':main()
