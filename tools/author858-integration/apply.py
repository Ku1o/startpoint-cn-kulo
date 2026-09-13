"""Install verified local data and append part 2 to the existing .107 version edge."""
import argparse
import copy
import json
import re
import zipfile
from pathlib import Path

import prepare as m

PART = 'pinball-1.4.106-1.4.107-2-author858-selected.zip'
AUDIT = 'assets/asset-patch/audit/author858-selected-1.4.107'
PART1 = 'pinball-1.4.106-1.4.107-1-weapon-caps-practice-hp.zip'
PART1_SHA = '55f99926afbd3588890505ec52a26f0b67dc13225a2b951509886d91db4f4171'


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--work', type=Path, required=True); args = ap.parse_args()
    w = args.work.resolve(); repo = m.REPO
    prepared_bytes = (w / 'prepared.json').read_bytes(); prepared = json.loads(prepared_bytes)
    for name in ('static-verification.json', 'selection-verification.json', 'candidate-runtime-verification.json'):
        check = m.readj(w / name)
        assert check['status'] == 'passed' and check['prepared_sha256'] == m.sha(prepared_bytes), name
    manifest_path = repo / 'assets/asset-patch/manifest.json'
    manifest_bytes = manifest_path.read_bytes()
    assert m.sha(manifest_bytes) == prepared['manifest_before_sha256'], 'active manifest changed; rebase candidate first'
    original_manifest = json.loads(manifest_bytes); manifest = copy.deepcopy(original_manifest)
    patches = [x for x in manifest['patches'] if x.get('enabled') and x.get('version') == '1.4.107']
    assert len(patches) == 1
    patch = patches[0]
    assert patch['depends_on'] == '1.4.106' and patch['chain'] == [PART1] and patch['archive'] == PART1
    destination = (repo / 'assets/asset-patch/active' / PART).resolve()
    assert destination.parent == (repo / 'assets/asset-patch/active').resolve()
    assert not destination.is_relative_to((repo / '.cdn').resolve())
    assert not destination.exists() and not (repo / AUDIT).exists(), 'part/audit already exists'
    assert m.sha(destination.with_name(PART1).read_bytes()) == PART1_SHA
    server = []
    for row in prepared['server_files']:
        path = (repo / row['path']).resolve()
        assert path.is_relative_to((repo / 'assets').resolve()) and path.suffix == '.json'
        assert not path.is_relative_to((repo / '.cdn').resolve())
        assert m.sha(path.read_bytes()) == row['before_sha256'], ('server source changed', row['path'])
        data = (w / 'prepared-server' / row['path']).read_bytes()
        assert m.sha(data) == row['sha256']; json.loads(data)
        server.append((path, data, row))
    # Create and read back outside active/. A failed build cannot be discovered
    # by the asset route as a partly written downloadable archive.
    zip_path = w / PART
    assert not zip_path.exists()
    with zipfile.ZipFile(zip_path, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for asset in sorted(prepared['assets'], key=lambda x: x['member']):
            member = asset['member']
            assert re.fullmatch(r'production/(upload|medium_upload|android_upload|ios_upload)/[a-f0-9]{2}/[a-f0-9]{38}', member), member
            raw = (w / 'prepared-client' / member).read_bytes()
            assert m.sha(raw) == asset['sha256'] and len(raw) == asset['size']
            info = zipfile.ZipInfo(member, date_time=(2026, 9, 13, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED; info.external_attr = 0o644 << 16
            z.writestr(info, raw, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    members = sorted(x['member'] for x in prepared['assets'])
    with zipfile.ZipFile(zip_path) as z:
        assert z.namelist() == members and len(set(members)) == len(members)
        assert z.testzip() is None
        for asset in prepared['assets']: assert m.sha(z.read(asset['member'])) == asset['sha256']
    zip_info = {'name': PART, 'size': zip_path.stat().st_size, 'sha256': m.sha(zip_path.read_bytes()),
                'members': len(members), 'files': members}
    patch['chain'].append(PART)
    patch.setdefault('archive_integrity', []).append(zip_info)
    patch['archive_size'] = sum(x['size'] for x in patch['archive_integrity'])
    patch['files'] = sorted(set(patch.get('files', [])) | set(members))
    patch['name'] += '；作者 858 选定内容融合'
    patch['description'] += ' 同版本第二分包接入已确认的新角色、小 Boss、技能、语音和美术，并按本服确认取舍重写两池。'
    patch.setdefault('changes', []).extend([
        '第二分包完整接入四位新角色与十五位小 Boss；定点更新光杰拉德、冰雪罗尔夫和夏日白。',
        '作者 MOD 概率、排序和标红保留；普通兑换沿用本服，排除 26 个非扭蛋角色，五位零概率角色不可兑换。',
        '正式语音、美术与十二组 iOS 立绘配套；保留图集自定义图标及已有优化。'])
    patch.setdefault('audit', {})['author858_directory'] = AUDIT
    # Everything outside this one unpublished version entry remains identical.
    for left, right in zip(original_manifest['patches'], manifest['patches']):
        if right is not patch: assert left == right
    assert manifest['cdn_version'] == original_manifest['cdn_version']
    manifest_after = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    (w / 'manifest-before-apply.json').write_bytes(manifest_bytes)
    (w / 'manifest-after-apply.json').write_bytes(manifest_after)
    # Last preimage checks immediately precede the short local mutation phase.
    assert manifest_path.read_bytes() == manifest_bytes
    for path, data, row in server: assert m.sha(path.read_bytes()) == row['before_sha256']
    zip_path.rename(destination)
    for path, data, row in server: path.write_bytes(data)
    manifest_path.write_bytes(manifest_after)
    assert m.sha(destination.read_bytes()) == zip_info['sha256']
    assert m.sha(destination.with_name(PART1).read_bytes()) == PART1_SHA
    for path, data, row in server: assert path.read_bytes() == data
    audit = repo / AUDIT; audit.mkdir(parents=True)
    for name in ('prepared.json', 'static-verification.json', 'selection-verification.json',
                 'candidate-runtime-verification.json', 'table-changes.json', 'server-changes.json',
                 'ios-pairs.json', 'technical-fixes.json', 'native-gachas.json'):
        (audit / name).write_bytes((w / name).read_bytes())
    part1_report = m.readj(repo / 'assets/asset-patch/audit/weapon-caps-practice-hp-1.4.107/report.json')
    chain = m.p.Chain(); assert chain.tail == '1.4.107'
    retained = []
    for scope in part1_report['scope']:
        raw = chain.get(('common', m.p.hrel(scope['logical'])))
        assert m.sha(raw) == scope['after_sha256'], scope['logical']
        retained.append(scope['logical'])
    result = {'status': 'installed_locally_pending_final_checks', 'edge': ['1.4.106', '1.4.107'],
        'part': 2, 'archive': zip_info, 'part1_sha256_unchanged': PART1_SHA,
        'part1_effective_tables_preserved': retained, 'prepared_sha256': m.sha(prepared_bytes),
        'manifest_before_sha256': m.sha(manifest_bytes), 'manifest_after_sha256': m.sha(manifest_after),
        'server_files': prepared['server_files'], 'sparse_preimages': str(w),
        'runtime_synced': False, 'cloud_deployed': False, 'commit_created': False,
        'apk_registry_promoted': False, 'ipa_modified': False, 'device_tested': False}
    m.writej(w / 'apply-report.json', result); m.writej(audit / 'report.json', result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('archive', 'server_files')} |
                     {'archive': {k: v for k, v in zip_info.items() if k != 'files'}}, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
