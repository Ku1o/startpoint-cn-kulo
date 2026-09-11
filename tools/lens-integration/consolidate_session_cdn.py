"""Fold the reviewed .104-.112 test chain into one .103 -> .104 CDN edge.

Only writes new output files. Historical ZIPs, held source manifest, pristine
CDN, runtime and APKs are never changed by this builder.
"""
from __future__ import annotations
import argparse,copy,io,json,zipfile
from pathlib import Path
import prepare_content as p
from five_boss_art_contract import validate_manifest

ARCHIVE='pinball-1.4.103-1.4.104-1-abyss-lens0910-consolidated.zip'
ID='abyss-lens0910-consolidated-1.4.104'

def merge_archives(entries,directory):
    result={};provenance={};inputs=[]
    for entry in entries:
        for name in entry.get('chain') or [entry['archive']]:
            assert Path(name).name==name
            raw=(directory/name).read_bytes()
            receipt,=[r for r in entry['archive_integrity'] if r['name']==name]
            assert len(raw)==receipt['size'] and p.sha(raw)==receipt['sha256'],name
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                assert z.testzip() is None
                assert len(set(z.namelist()))==len(z.namelist())
                assert sorted(z.namelist())==sorted(receipt['files']),name
                for member in z.namelist():
                    bits=member.split('/')
                    assert len(bits)==4 and bits[0]=='production' and bits[1] in p.REVERSE_ROOTS
                    assert len(bits[2])==2 and len(bits[3])==38 and all(c in '0123456789abcdef' for c in bits[2]+bits[3])
                    result[member]=z.read(member);provenance[member]=name
            inputs.append(dict(name=name,sha256=p.sha(raw),size=len(raw)))
    return result,provenance,inputs

def build(base_path,current_path,archives,inventory_path,out):
    assert not out.exists(),'use a fresh output directory'
    assert not out.resolve().is_relative_to((p.REPO/'.cdn').resolve())
    base=p.readj(base_path);current=p.readj(current_path)
    assert base['cdn_version']=='1.4.103' and current['cdn_version']=='1.4.112'
    validate_manifest(base);validate_manifest(current)
    assert current['patches'][:len(base['patches'])]==base['patches']
    entries=current['patches'][len(base['patches']):]
    assert len(entries)==9 and all(e['enabled'] for e in entries)
    members,provenance,inputs=merge_archives(entries,archives)
    # All actual changed payloads must agree with the final .112 audit.
    inventory=p.readj(inventory_path);expected={r['member']:r for r in inventory}
    assert len(expected)==len(inventory)
    assert set(members)<=set(expected),set(members)-set(expected)
    for member,raw in members.items():assert p.sha(raw)==expected[member]['sha256'],member
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for member,raw in sorted(members.items()):
            info=zipfile.ZipInfo(member,(2026,9,10,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,raw)
    raw=buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert z.testzip() is None and set(z.namelist())==set(members)
        assert all(z.read(member)==data for member,data in members.items())
    entry=dict(id=ID,type='patch',name='深渊连战、称号、五重道具与 Lens 0910 合并增量',
        description='将本会话测试链的最终资源合并为云服 1.4.103 后的单一 1.4.104 增量。',
        version='1.4.104',depends_on='1.4.103',enabled=True,archive=ARCHIVE,archive_size=len(raw),chain=[ARCHIVE],
        archive_integrity=[dict(name=ARCHIVE,size=len(raw),sha256=p.sha(raw),members=len(members),files=sorted(members))],
        files=sorted(members),created_at='2026-09-10',
        required_client_capability='cn.ui.AbyssDetails/v1 + cn.rules.QuestElementResistance/v1 + Lens0910',
        audit=dict(directory='assets/asset-patch/audit/session-consolidated-1.4.104',report='report.json'))
    manifest=copy.deepcopy(base);manifest['cdn_version']='1.4.104';manifest['patches'].append(entry);validate_manifest(manifest)
    out.mkdir(parents=True);(out/ARCHIVE).write_bytes(raw);p.savej(out/'manifest.json',manifest)
    report=dict(status='archive_payloads_verified_runtime_pending',base_version='1.4.103',target_version='1.4.104',
        source_test_tail='1.4.112',input_archives=inputs,archive=entry['archive_integrity'][0],
        resources=[dict(expected[n],final_source_archive=provenance[n]) for n in sorted(members)],
        final_inventory=inventory,base_manifest_sha256=p.sha(base_path.read_bytes()),
        input_manifest_sha256=p.sha(current_path.read_bytes()),merged_payloads_identical=True,
        intermediate_versions_in_active_manifest=False,source_hold_included=False,
        apk_changed=False,desktop_air_run=False,cloud_overlay_created=False,cloud_deployed=False,
        cached_test_client_note='A client already at test resource 1.4.112 keeps its higher cache marker. Reset its resource cache before later .105+ testing; player save is separate.')
    p.savej(out/'report.json',report);p.savej(out/'manifest-entry.json',entry)
    print(json.dumps(dict(status=report['status'],members=len(members),inventory=len(inventory),archive_bytes=len(raw),sha256=p.sha(raw)),ensure_ascii=False))

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    for n in ['base-manifest','test-manifest','archives','inventory','out']:ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();build(a.base_manifest,a.test_manifest,a.archives,a.inventory,a.out)
