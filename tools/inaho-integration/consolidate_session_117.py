"""Fold the .117-.119 resource changes into one .116 -> .117 edge.

Keeps every final resource byte and the earlier chain. Produces an offline
candidate only; old archives are neither rewritten nor deleted.
"""
from __future__ import annotations
import argparse
import copy
import json
import re
import zipfile
from pathlib import Path
import build_redesign_118 as base

ROOT = base.ROOT
SOURCE_MANIFEST_SHA = '7c92f7567f2f89b5adea62eae31792914f2ba1f370c3b4e9d72b4fbc9a7b6782'
BASE, VERSION = '1.4.116', '1.4.117'
ARCHIVE = 'pinball-1.4.116-1.4.117-1-author-inaho-fluffy-consolidated.zip'
AUDIT = 'assets/asset-patch/audit/session-consolidated-1.4.117-20260924'
INPUTS = [
    ('1.4.117', 'pinball-1.4.116-1.4.117-1-author-1043-and-content-fixes.zip', 'cca107e6579341c9979984688ebdeb5d247e80fe59a5c6ff2a879d53326bfd98'),
    ('1.4.118', 'pinball-1.4.117-1.4.118-1-inaho-redesign-fluffy-gauge.zip', '8f619c3d82ce0bd89d6bff0e01895893bd1da2ae8834d2b1d02e789303410f9e'),
    ('1.4.119', 'pinball-1.4.118-1.4.119-1-inaho-leader-target-fix.zip', '197287f260fc7c1a00cce971dc6f4c81dd04a3d6290c0bc60594d2fa9dd09707'),
]
SERVER_FILES = ['assets/gacha.json', 'assets/gacha_cnmod.json', 'assets/cdndata/character_text.json']


def build(work, source_manifest=None):
    manifest_path = source_manifest or ROOT/'assets/asset-patch/manifest.json'
    manifest_bytes = manifest_path.read_bytes()
    assert base.sha(manifest_bytes) == SOURCE_MANIFEST_SHA, 'Active chain changed; rebase explicitly'
    manifest = json.loads(manifest_bytes)
    assert manifest['cdn_version'] == '1.4.119'
    entries = manifest['patches'][-3:]
    assert [e['version'] for e in entries] == [v for v, _, _ in INPUTS]
    assert all(e['type'] == 'patch' and e['enabled'] for e in entries)
    payloads, winners, receipts, overwritten = {}, {}, [], []
    expected_from = BASE
    for edge, (version, name, digest) in zip(entries, INPUTS):
        assert edge['depends_on'] == expected_from and edge['archive'] == name
        assert (edge.get('chain') or [name]) == [name]
        expected_from = version
        path = ROOT/'assets/asset-patch/active'/name
        raw = path.read_bytes()
        assert base.sha(raw) == digest
        receipt, = edge['archive_integrity']
        assert receipt['sha256'] == digest and receipt['size'] == len(raw)
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            assert z.testzip() is None and len(names) == len(set(names)) == receipt['members']
            assert sorted(names) == sorted(receipt['files']) == sorted(edge['files'])
            for member in names:
                assert re.fullmatch(r'production/(?:upload|medium_upload|small_upload|android_upload|ios_upload)/[0-9a-f]{2}/[0-9a-f]{38}', member), member
                if member in winners:
                    overwritten.append({'member': member, 'previous': winners[member], 'winner': name})
                payloads[member], winners[member] = z.read(member), name
        receipts.append({'version': version, 'archive': name, 'sha256': digest, 'bytes': len(raw), 'members': len(names)})
    assert len(payloads) == 2072 and len(overwritten) == 8
    # Recheck the demonstrated failures using the exact final merged tables.
    _, leaders = base.raw_map(payloads[base.member(base.LEADER)], base.LEADER)
    base.check_combo_gauge(base.core.read_csv_lines(base.ql.parse_node(leaders['159991'])))
    _, abilities = base.raw_map(payloads[base.member(base.ABILITY)], base.ABILITY)
    base.check_gauge_filter(base.core.read_csv_lines(base.ql.parse_node(abilities['1499872'])))

    candidate = work/'candidate'
    archive_path = candidate/'assets/asset-patch/active'/ARCHIVE
    assert not archive_path.exists(), 'Use a fresh build directory'
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for member, raw in sorted(payloads.items()):
            info = zipfile.ZipInfo(member, (2026, 9, 24, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, raw)
    with zipfile.ZipFile(archive_path) as z:
        assert z.testzip() is None and set(z.namelist()) == set(payloads)
        for member, raw in payloads.items(): assert z.read(member) == raw, member
    archive_sha, size = base.sha(archive_path.read_bytes()), archive_path.stat().st_size
    names = sorted(payloads)
    merged = copy.deepcopy(entries[0])
    merged.update(id='author-inaho-fluffy-consolidated-117-20260924',
        name='作者1043角色与中秋稻穗调整整合',
        description='统一角色媒体与机制数据、稻穗数值和分段说明、芙拉菲回槽限制及稻穗详情修复。',
        depends_on=BASE, version=VERSION, archive=ARCHIVE, archive_size=size, chain=[ARCHIVE],
        files=names, archive_integrity=[{'name': ARCHIVE, 'size': size, 'sha256': archive_sha, 'members': len(names), 'files': names}],
        changes=[change for entry in entries for change in entry['changes']], audit={'directory': AUDIT})
    for name in ('quest_time_revisions', 'quest_description_revisions', 'rush_tower_resets', 'rush_tower_preserves'):
        values = {}
        for entry in entries: values.update(entry.get(name, {}))
        if values: merged[name] = values
    result = copy.deepcopy(manifest)
    result['patches'] = result['patches'][:-3] + [merged]
    result['cdn_version'] = VERSION
    assert result['patches'][:-1] == manifest['patches'][:-3]
    assert max(tuple(map(int, e['version'].split('.'))) for e in result['patches'] if e.get('enabled')) == (1, 4, 117)
    base.write(work/'before/assets/asset-patch/manifest.json', manifest_bytes)
    base.write(candidate/'assets/asset-patch/manifest.json', base.jsonb(result))
    companions = []
    for rel in SERVER_FILES:
        data = (ROOT/rel).read_bytes()
        base.write(candidate/rel, data)
        companions.append({'path': rel, 'sha256': base.sha(data), 'bytes': len(data)})
    report = {'status': 'offline_candidate', 'baseline': BASE, 'target': VERSION,
        'input_tail': '1.4.119', 'archive': ARCHIVE, 'archive_sha256': archive_sha,
        'archive_bytes': size, 'members': len(payloads), 'input_archives': receipts,
        'before_files': {'assets/asset-patch/manifest.json': SOURCE_MANIFEST_SHA},
        'manifest_sha256': base.sha(base.jsonb(result)), 'server_companions': companions,
        'overwritten_members': overwritten,
        'resources': [{'member': n, 'sha256': base.sha(payloads[n]), 'bytes': len(payloads[n]), 'source_archive': winners[n]} for n in names],
        'final_payload_bytes_identical': True, 'earlier_manifest_entries_unchanged': True,
        'old_archives_preserved': True, 'intermediate_versions_active': False,
        'upgrade_bridges_created': False, 'apk_rebuilt': False, 'device_tested': False,
        'cloud_deployed': False, 'save_impact': 'Packaging only; no saved IDs, persistence or gameplay data changes.'}
    base.write(work/'build-report.json', base.jsonb(report))
    print(json.dumps({k: report[k] for k in ('status', 'baseline', 'target', 'archive_bytes', 'archive_sha256', 'members')}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--source-manifest', type=Path)
    args = parser.parse_args()
    build(args.work, args.source_manifest)
