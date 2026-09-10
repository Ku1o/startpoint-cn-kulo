"""Append the shared entry-condition wording update to the verified .103 chain.

Writes only the source repository and --work; never starts or syncs a server.
The exact preimage locks this historical builder to its reviewed input.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import zipfile

import prepare_content as p

BASE, VERSION = '1.4.103', '1.4.104'
LOGICAL = 'master/string/ui_string.orderedmap'
UI_KEY = 'quest_start_out_of_period_error'
BEFORE_SHA256 = 'a901379873ae114774f79b0fb4eada438e6e962c5fbcbe3ab2eb6ba76e85593d'
MANIFEST_SHA256 = 'd3be9e13245264893c6e1ae8528026b9e97c6103b9e07ca7d3dafc857d5400ec'
MESSAGE = (
    '当前不满足出战条件。\n'
    '请检查关卡开放状态、入场门票和队伍限制。\n'
    '幻想连战专属装备及魂珠仅限幻想连战使用，\n'
    '挑战其他关卡前请先卸下或更换。'
)


def validate(before: bytes, after: bytes):
    old, new = p.rawmap(before), p.rawmap(after)
    assert list(old) == list(new)
    assert [key for key in old if old[key] != new[key]] == [UI_KEY]
    assert p.csvrows(new[UI_KEY]) == [[MESSAGE]]
    return {'rows': len(new), 'changed_keys': [UI_KEY],
            'other_rows_byte_identical': True, 'message': MESSAGE}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work', type=Path, required=True)
    work = ap.parse_args().work.resolve()
    repo, cdn = p.REPO.resolve(), (p.REPO / '.cdn').resolve()
    assert not work.is_relative_to(cdn)
    assert not work.exists(), 'use a fresh task directory'
    chain = p.Chain()
    assert chain.tail == BASE and p.sha(chain.manifest_bytes) == MANIFEST_SHA256
    key = ('common', p.hrel(LOGICAL))
    before = chain.get(key)
    assert before is not None and p.sha(before) == BEFORE_SHA256
    rows = p.rawmap(before)
    old_message = p.csvrows(rows[UI_KEY])[0][0]
    rows[UI_KEY] = p.packcsv([[MESSAGE]])
    after = p.packmap(rows)
    checks = validate(before, after)
    member = p.member(key)
    direct_rel = 'assets/asset-patch/' + member
    assert (repo / direct_rel).read_bytes() == before, 'direct CDN source diverged'

    name = f'pinball-{BASE}-{VERSION}-1-entry-condition-message-cn.zip'
    archive_rel = 'assets/asset-patch/active/' + name
    audit_rel = 'assets/asset-patch/audit/entry-condition-message-' + VERSION
    assert not (repo / archive_rel).exists() and not (repo / audit_rel).exists()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        info = zipfile.ZipInfo(member, (2026, 9, 9, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, after)
    archive = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert z.testzip() is None and z.namelist() == [member]
        assert z.read(member) == after
        validate(before, z.read(member))
    integrity = {'name': name, 'size': len(archive), 'sha256': p.sha(archive),
                 'members': 1, 'files': [member]}
    manifest = json.loads(chain.manifest_bytes)
    manifest['patches'].append({
        'id': 'entry-condition-message-' + VERSION, 'type': 'patch',
        'name': '出战提示补充幻想装备与魂珠限制',
        'description': '共用4050提示明确幻想连战专属装备及魂珠仅限本模式使用，保留关卡开放、门票及队伍限制提示。',
        'version': VERSION, 'depends_on': BASE, 'enabled': True,
        'archive': name, 'archive_size': len(archive), 'chain': [name],
        'archive_integrity': [integrity], 'files': [member],
        'created_at': '2026-09-09', 'local_test_only': False,
        'audit': {'directory': audit_rel, 'report': 'report.json'},
    })
    manifest['cdn_version'] = VERSION
    report = {
        'status': 'local_resource_verified_device_acceptance_pending',
        'base': BASE, 'version': VERSION, 'archive': integrity,
        'logical': LOGICAL, 'ui_key': UI_KEY, 'old_message': old_message,
        'checks': checks, 'before_sha256': p.sha(before), 'after_sha256': p.sha(after),
        'manifest_before_sha256': p.sha(chain.manifest_bytes), 'source_reads': chain.reads,
        'platforms': ['android', 'ios'], 'root': 'common',
        'scope': '共用4050文案，幻想装备/魂珠门禁、五重缺票及其他4050场景均显示；没有按拒绝原因区分弹窗。',
        'runtime_evidence': [
            'src/lib/mode15.ts: MODE15_EXCLUSIVE_EQUIPMENT_IDS and getMode15ExclusivePartyItemsSync check equipment and ability_soul slots',
            'src/routes/api/singleBattleQuest.ts, src/routes/api/rushEvent.ts, src/routes/api/raidEvent.ts, src/multi/http/battle.ts: equipment gates return 4050',
            'src/multi/five-boss/entry-response.ts: ticket shortage returns 4050',
            'assets/asset-patch/audit/lens0909-completion-1.4.104/client-evidence.json: native 4050 branch reads this UI key',
            'src/cn-server.ts: direct custom CDN routes read assets/asset-patch/production before pristine CDN',
        ],
        'swf_changed': False, 'device_tested': False, 'runtime_delivered': False,
        'cloud_overlay_created': False,
    }
    writes = {archive_rel: archive, direct_rel: after}
    writes['assets/asset-patch/manifest.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    for rel in writes:
        dest = (repo / rel).resolve()
        assert dest.is_relative_to(repo) and not dest.is_relative_to(cdn)
    work.mkdir(parents=True)
    for rel in writes:
        dest = repo / rel
        if dest.exists():
            saved = work / 'before' / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(dest.read_bytes())
    assert (repo / 'assets/asset-patch/manifest.json').read_bytes() == chain.manifest_bytes
    assert (repo / direct_rel).read_bytes() == before
    for rel, raw in writes.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_bytes(raw)
        assert (repo / rel).read_bytes() == raw

    effective = p.Chain()
    assert effective.tail == VERSION and effective.get(key) == after
    assert (repo / direct_rel).read_bytes() == effective.get(key)
    report['effective_chain_and_direct_file_match'] = True
    report['manifest_after_sha256'] = p.sha(effective.manifest_bytes)
    report['backup_directory'] = str(work / 'before')
    p.savej(repo / audit_rel / 'report.json', report)
    p.savej(work / 'report.json', report)
    print(json.dumps({'version': VERSION, 'archive': integrity, 'checks': checks}, ensure_ascii=True))


if __name__ == '__main__':
    main()
