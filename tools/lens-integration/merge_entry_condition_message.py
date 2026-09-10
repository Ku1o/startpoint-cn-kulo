"""Fold the approved held wording into the user's single .103 -> .104 edge.

Reads an explicit committed manifest, preserves every existing merged payload,
and writes only a fresh --work directory. Activation/sync is a separate step.
"""
import argparse,copy,io,json,zipfile
from pathlib import Path

import prepare_content as p
from five_boss_art_contract import validate_manifest
from update_entry_condition_message import LOGICAL,UI_KEY,BEFORE_SHA256,MESSAGE,validate

OLD_ARCHIVE='pinball-1.4.103-1.4.104-1-abyss-lens0910-consolidated.zip'
OLD_ARCHIVE_SHA256='2af51b045cf16766c0dcaaa9239564d8e383201695a187a515826858ef98d971'
NEW_ARCHIVE='pinball-1.4.103-1.4.104-1-abyss-lens0910-entry-message-consolidated.zip'
AUDIT='assets/asset-patch/audit/entry-condition-message-1.4.104-approved'


def build(manifest_path,archive_dir,previous_report,work):
    assert not work.exists(),'use a fresh output directory'
    assert not work.resolve().is_relative_to((p.REPO/'.cdn').resolve())
    manifest_bytes=manifest_path.read_bytes();manifest=json.loads(manifest_bytes)
    validate_manifest(manifest);assert manifest['cdn_version']=='1.4.104'
    enabled=[e for e in manifest['patches'] if e.get('enabled')]
    edge=enabled[-1]
    assert edge['version']=='1.4.104' and edge['depends_on']=='1.4.103'
    assert edge['archive']==OLD_ARCHIVE and edge['chain']==[OLD_ARCHIVE]
    old_zip=(archive_dir/OLD_ARCHIVE).read_bytes()
    assert p.sha(old_zip)==OLD_ARCHIVE_SHA256
    with zipfile.ZipFile(io.BytesIO(old_zip)) as z:
        assert z.testzip() is None
        assert sorted(z.namelist())==sorted(edge['files'])
        members={name:z.read(name) for name in z.namelist()}
    assert len(members)==600
    member=p.member(('common',p.hrel(LOGICAL)))
    assert member not in members
    before=None;source_archive=None
    for prior in reversed(enabled[:-1]):
        for name in reversed(prior.get('chain') or [prior['archive']]):
            assert Path(name).name==name
            with zipfile.ZipFile(archive_dir/name) as z:
                if member in z.namelist():
                    before=z.read(member);source_archive=name;break
        if before is not None:break
    assert before is not None and p.sha(before)==BEFORE_SHA256
    rows=p.rawmap(before);rows[UI_KEY]=p.packcsv([[MESSAGE]])
    after=p.packmap(rows);checks=validate(before,after)
    assert p.sha(after)=='9ca56e9fc89b868d18abaf7b839b8b84354b0c6193b55938f9ffeb57eecac62c'
    members[member]=after
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,raw in sorted(members.items()):
            info=zipfile.ZipInfo(name,(2026,9,10,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,raw)
    raw=buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert z.testzip() is None and len(z.namelist())==601
        assert all(z.read(name)==payload for name,payload in members.items())
        validate(before,z.read(member))
    integrity=dict(name=NEW_ARCHIVE,size=len(raw),sha256=p.sha(raw),members=len(members),files=sorted(members))
    edge.update(name='深渊连战、称号、五重道具、Lens 0910 与出战提示合并增量',
        description='在原本会话 1.4.104 合并终态上加入已解除暂缓的幻想装备与魂珠使用限制提示。',
        archive=NEW_ARCHIVE,archive_size=len(raw),chain=[NEW_ARCHIVE],archive_integrity=[integrity],files=sorted(members),
        audit=dict(directory=AUDIT,report='report.json'))
    validate_manifest(manifest)
    previous=p.readj(previous_report)
    assert previous['archive']['sha256']==OLD_ARCHIVE_SHA256
    for row in previous['resources']:assert p.sha(members[row['member']])==row['sha256']
    row=dict(root='common',logical=LOGICAL,member=member,sha256=p.sha(after),size=len(after),final_source_archive=NEW_ARCHIVE)
    report=dict(status='payload_verified_activation_pending',base_version='1.4.103',target_version='1.4.104',
        user_authorized_hold_release=True,single_version_consolidation=True,archive=integrity,
        previous_archive=dict(name=OLD_ARCHIVE,sha256=OLD_ARCHIVE_SHA256),previous_manifest_sha256=p.sha(manifest_bytes),
        source_archive=source_archive,before_sha256=p.sha(before),after_sha256=p.sha(after),checks=checks,
        resources=copy.deepcopy(previous['resources'])+[row],final_inventory=copy.deepcopy(previous['final_inventory'])+[row],
        original_600_payloads_identical=True,platforms=['Android','iOS'],shared_4050_message=True,
        server_gate_changed=False,apk_changed=False,desktop_air_run=False,device_tested=False,
        cloud_overlay_created=False,cloud_deployed=False,
        cached_client_note='Already cached .104/.112 clients need resource cache refresh to receive revised .104; no player save or cache is changed by this tool.')
    assert len({r['member'] for r in report['final_inventory']})==len(report['final_inventory'])==610
    work.mkdir(parents=True);(work/NEW_ARCHIVE).write_bytes(raw)
    p.savej(work/'manifest.json',manifest);p.savej(work/'report.json',report)
    (work/'ui_string.bin').write_bytes(after)
    print(json.dumps(dict(version='1.4.104',archive_sha256=p.sha(raw),bytes=len(raw),members=601,changed_ui_keys=checks['changed_keys'])))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ['manifest','archive-dir','previous-report','work']:ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();build(a.manifest,a.archive_dir,a.previous_report,a.work)
