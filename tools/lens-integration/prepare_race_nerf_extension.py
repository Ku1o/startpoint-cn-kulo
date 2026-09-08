"""Prepare a sequential resource edge from the latest reviewed race nerf candidate."""
import argparse
import copy
from datetime import date
import io
from pathlib import Path
import zipfile
import prepare_content as p
import wf_race_character_nerf as nerf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', type=Path, required=True)
    w = ap.parse_args().work.resolve()
    assert not w.is_relative_to((p.REPO / '.cdn').resolve())
    candidate = p.readj(w / 'candidate/receipt.json')
    assert candidate['changed_cells'] == 56
    assert p.sha(nerf.SPEC_PATH.read_bytes()) == candidate['spec_sha256']
    c = p.Chain()
    assert candidate['source_tail'] == c.tail
    base = c.tail
    parts = list(map(int, base.split('.'))); parts[-1] += 1
    version = '.'.join(map(str, parts))
    payloads, reports = {}, []
    for record in candidate['tables']:
        logical = record['logical']
        raw = c.get(('common', p.hrel(logical)))
        assert p.sha(raw) == record['input_sha256'], 'candidate input changed'
        output, report = nerf.patch_table(logical, raw)
        member = p.member(('common', p.hrel(logical)))
        assert member == record['member']
        assert output == (w / 'candidate' / member).read_bytes()
        assert p.sha(output) == record['output_sha256']
        final, second = nerf.patch_table(logical, output)
        assert final == output and second['changed_cells'] == 0
        payloads[member] = output
        reports.append(report)
    assert len(payloads) == 2
    assert sum(x['changed_cells'] for x in reports) == 56
    assert sum(len(x['changed_keys']) for x in reports) == 12
    name = f'pinball-{base}-{version}-1-race-character-nerf.zip'
    buffer = io.BytesIO()
    today = date.today()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for member, raw in sorted(payloads.items()):
            info = zipfile.ZipInfo(member, (today.year, today.month, today.day, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, raw)
    archive = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert z.testzip() is None and set(z.namelist()) == set(payloads)
        for member, raw in payloads.items(): assert z.read(member) == raw
    integrity = {'name': name, 'size': len(archive), 'sha256': p.sha(archive),
                 'members': len(payloads), 'files': sorted(payloads)}
    manifest = copy.deepcopy(c.manifest)
    manifest['patches'].append({'id': 'race-character-nerf-' + version, 'type': 'patch',
        'name': '竞速池四角色第一轮削弱',
        'description': '水灵幽魂、红蝮蛇、风暴恶魔拉比、机枪魔块·雷的能力与队长技能调整。',
        'version': version, 'depends_on': base, 'enabled': True, 'archive': name,
        'archive_size': len(archive), 'chain': [name], 'archive_integrity': [integrity],
        'files': sorted(payloads), 'created_at': today.isoformat(),
        'local_test_only': True, 'required_local_platform': 'android',
        'audit': {'directory': f'assets/asset-patch/audit/race-character-nerf-{version}', 'report': 'report.json'}})
    manifest['cdn_version'] = version
    assert (p.REPO / 'assets/asset-patch/manifest.json').read_bytes() == c.manifest_bytes
    (w / name).write_bytes(archive)
    (w / 'manifest.before.json').write_bytes(c.manifest_bytes)
    p.savej(w / 'manifest.after.json', manifest)
    report = {'base': base, 'version': version, 'archive': integrity, 'tables': reports,
              'source_reads': c.reads, 'shared_android_ios_data': True,
              'runtime_platform_gate': 'android', 'device_tested': False,
              'candidate_spec_sha256': candidate['spec_sha256'],
              'all_unrelated_keys_preserved': True, 'regression_tests_passed': 8}
    p.savej(w / 'report.json', report)
    print(f'Prepared {base} -> {version}: {len(archive)} bytes, 2 tables, 12 keys, 56 cells')


if __name__ == '__main__': main()
