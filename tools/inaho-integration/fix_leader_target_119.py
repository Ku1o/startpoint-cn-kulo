"""Build an immutable .118 -> .119 repair for the Inaho leader target.

Only the active leader table is rewritten, and only one cell may differ.
This builds an offline candidate; activation is separate.
"""
from __future__ import annotations
import argparse
import copy
import json
import zipfile
from pathlib import Path
import build_redesign_118 as base

ROOT = base.ROOT
BASE = '1.4.118'
VERSION = '1.4.119'
MANIFEST_SHA = '5c63b6a9a6628210b4cdc727ea24c0fb475267918721b0f90f893fac17d6225a'
PREVIOUS_ARCHIVE_SHA = '8f619c3d82ce0bd89d6bff0e01895893bd1da2ae8834d2b1d02e789303410f9e'
ARCHIVE = 'pinball-1.4.118-1.4.119-1-inaho-leader-target-fix.zip'
AUDIT = 'assets/asset-patch/audit/inaho-leader-target-fix-1.4.119'
LOGICAL = base.LEADER


def repair(raw):
    original_map, original = base.raw_map(raw, LOGICAL)
    rows = base.core.read_csv_lines(base.ql.parse_node(original['159991']))
    before = copy.deepcopy(rows)
    assert len(rows) == 17 and all(len(row) == 124 for row in rows)
    row = rows[15]
    assert (row[3], row[45], row[47], row[49], row[50]) == ('0', '211', '(None)', '1500', '1500')
    assert row[46] in ('', '0'), 'Unexpected existing gauge target'
    if row[46] == '0':
        base.check_combo_gauge(rows)
        return raw
    row[46] = '0'
    base.check_combo_gauge(rows)
    delta = [(i, j, a, b) for i, (left, right) in enumerate(zip(before, rows))
             for j, (a, b) in enumerate(zip(left, right)) if a != b]
    assert delta == [(15, 46, '', '0')], delta
    result = base.pack_changes(raw, LOGICAL, {'159991': base.core.write_csv_lines(rows)})
    check_map, check = base.raw_map(result, LOGICAL)
    assert check_map.keys == original_map.keys
    assert {k for k in original if original[k] != check[k]} == {'159991'}
    base.check_combo_gauge(base.core.read_csv_lines(base.ql.parse_node(check['159991'])))
    return result


def build(work):
    manifest_bytes = (ROOT / 'assets/asset-patch/manifest.json').read_bytes()
    assert base.sha(manifest_bytes) == MANIFEST_SHA, 'Active manifest changed; rebase explicitly'
    manifest = json.loads(manifest_bytes)
    assert manifest['cdn_version'] == BASE
    original_manifest = copy.deepcopy(manifest)
    source_name, raw = None, None
    member = base.member(LOGICAL)
    for edge in manifest['patches']:
        if not edge.get('enabled', True): continue
        for name in edge.get('chain') or [edge['archive']]:
            with zipfile.ZipFile(ROOT / 'assets/asset-patch/active' / name) as z:
                if member in z.namelist(): raw, source_name = z.read(member), name
    assert source_name == base.ARCHIVE
    assert base.sha((ROOT/'assets/asset-patch/active'/source_name).read_bytes()) == PREVIOUS_ARCHIVE_SHA
    base.write(work/'before/assets/asset-patch/manifest.json', manifest_bytes)
    base.write(work/'before'/member, raw)
    corrected = repair(raw)
    assert repair(corrected) == corrected, 'Repair must be idempotent'
    candidate = work/'candidate'
    archive_path = candidate/'assets/asset-patch/active'/ARCHIVE
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        info = zipfile.ZipInfo(member, (2026, 9, 24, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        z.writestr(info, corrected)
    with zipfile.ZipFile(archive_path) as z:
        assert z.testzip() is None and z.namelist() == [member]
        assert z.read(member) == corrected
        assert repair(z.read(member)) == corrected
    digest, size = base.sha(archive_path.read_bytes()), archive_path.stat().st_size
    manifest['cdn_version'] = VERSION
    manifest['patches'].append({
        'id': 'inaho-leader-target-fix-20260924', 'type': 'patch',
        'name': '中秋稻穗角色详情 C7050 修复',
        'description': '补齐队长技连击回槽的自身目标，修复角色详情解析错误。',
        'version': VERSION, 'depends_on': BASE, 'enabled': True, 'local_test_only': True,
        'archive': ARCHIVE, 'archive_size': size,
        'archive_integrity': [{'name': ARCHIVE, 'size': size, 'sha256': digest, 'members': 1, 'files': [member]}],
        'files': [member], 'audit': {'directory': AUDIT},
        'changes': ['队长技 45 连击回槽明确使用自身目标；数值、触发条件及其他资源不变。'],
    })
    assert manifest['patches'][:-1] == original_manifest['patches']
    base.write(candidate/'assets/asset-patch/manifest.json', base.jsonb(manifest))
    report = {
        'status': 'offline_candidate', 'baseline': BASE, 'target': VERSION,
        'archive': ARCHIVE, 'archive_sha256': digest, 'archive_bytes': size, 'members': 1,
        'logical': LOGICAL, 'member': member, 'source_archive': source_name,
        'source_archive_sha256': PREVIOUS_ARCHIVE_SHA,
        'before_resource_sha256': base.sha(raw), 'after_resource_sha256': base.sha(corrected),
        'before_files': {'assets/asset-patch/manifest.json': MANIFEST_SHA},
        'after_manifest_sha256': base.sha(base.jsonb(manifest)),
        'changes': [{'key': '159991', 'row_zero_based': 15, 'column_zero_based': 46,
                     'before': '', 'after': '0', 'meaning': 'Myself'}],
        'checks': ['Only one decoded cell changed', 'Every unrelated raw row retained',
                   'Native required-target contract applied', 'Idempotent repair',
                   'Archive CRC and serialized readback', 'Historical manifest entries retained'],
        'save_impact': 'Existing ability target only; no persistence, saved ID or schema changes.',
        'device_tested': False, 'apk_rebuilt': False, 'cloud_deployed': False,
    }
    base.write(work/'build-report.json', base.jsonb(report))
    print(json.dumps({k: report[k] for k in ('status', 'target', 'archive_sha256', 'archive_bytes', 'members')}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    build(parser.parse_args().work)
