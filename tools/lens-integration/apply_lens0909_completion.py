"""Publish only the verified 1.4.103 -> 1.4.104 local sparse resource edge."""
import argparse
import io
import json
import zipfile
from pathlib import Path
import prepare_content as p


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    w = parser.parse_args().work.resolve()
    assert not w.is_relative_to((p.REPO / '.cdn').resolve())
    c = p.Chain()
    prepared = p.readj(w / 'prepare-report.json')
    accepted = p.readj(w / 'acceptance-report.json')
    assert c.tail == prepared['baseline'] == '1.4.103'
    assert p.sha(c.manifest_bytes) == prepared['manifest_sha256']
    assert accepted['status'] == 'passed'
    assert accepted['inventory_sha256'] == p.sha((w / 'resources.json').read_bytes())
    resources = p.readj(w / 'resources.json')
    assert len(resources) == accepted['resources'] == 51
    payloads, writes = {}, {}
    for row in resources:
        assert row['root'] == 'common' and p.hrel(row['logical']) == row['rel']
        key = row['root'], row['rel']
        raw = (w / 'resources' / p.ROOTS[row['root']] / row['rel']).read_bytes()
        assert p.sha(raw) == row['sha256']
        assert p.sha(c.get(key)) == row['before_sha256']
        member = p.member(key)
        assert member == row['member'] and member not in payloads
        payloads[member] = raw
        writes['assets/asset-patch/' + member] = raw

    # Hold every previous 0909 payload, except the exact rows/resources approved here.
    previous = p.readj(p.REPO / 'assets/asset-patch/audit/lens0909-1.4.103/resources.json')
    for row in previous:
        assert p.sha(c.get((row['root'], row['rel']))) == row['sha256']

    archive_name = 'pinball-1.4.103-1.4.104-1-lens0909-completion-cn.zip'
    archive_rel = 'assets/asset-patch/active/' + archive_name
    audit_rel = 'assets/asset-patch/audit/lens0909-completion-1.4.104'
    assert not (p.REPO / archive_rel).exists() and not (p.REPO / audit_rel).exists()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for member, raw in sorted(payloads.items()):
            info = zipfile.ZipInfo(member, (2026, 9, 9, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, raw)
    archive = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert z.testzip() is None and z.namelist() == sorted(payloads)
        for member, raw in payloads.items():
            assert z.read(member) == raw
    integrity = {'name': archive_name, 'size': len(archive), 'sha256': p.sha(archive),
                 'members': len(payloads), 'files': sorted(payloads)}
    manifest = json.loads(c.manifest_bytes)
    manifest['patches'].append({
        'id': 'lens0909-completion-1.4.104', 'type': 'patch',
        'name': '0909 图集优化与门票说明',
        'description': '从我方现有像素重排图集、共享风巨蜥波纹并采用魔王粒子优化；补全门票说明与原生出战条件提示。',
        'version': '1.4.104', 'depends_on': '1.4.103', 'enabled': True,
        'archive': archive_name, 'archive_size': len(archive), 'chain': [archive_name],
        'archive_integrity': [integrity], 'files': sorted(payloads),
        'created_at': '2026-09-09', 'local_test_only': False,
        'audit': {'directory': audit_rel, 'report': 'report.json'},
    })
    manifest['cdn_version'] = '1.4.104'
    writes[archive_rel] = archive
    audit = {
        'status': 'local_implementation_validated_device_acceptance_pending',
        'archive': integrity, 'manifest_before_sha256': p.sha(c.manifest_bytes),
        'acceptance': accepted,
        'remaining_device_checks': ['多角色技能同时装箱与帧率', '风巨蜥三段动画及魔王粒子',
                                    '单人 AUTO 切换和缺票返回界面'],
        'scope': '本地未提交；未同步运行镜像或部署云服；未修改 APK/IPA/SWF。',
        'portrait_scope': '本增量不含立绘、切入或角色 ActionDSL；1.4.103 已接入的角色调整保持。',
        'platform_scope': '这些战斗图集由 Android/iOS 共用 PNG 动态装箱路径载入，不产生平台 ATF 切入。',
    }
    writes[audit_rel + '/report.json'] = (json.dumps(audit, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    for name in ('resources.json', 'atlas-report.json', 'parts-report.json', 'ticket-ui-report.json',
                 'prepare-report.json', 'source-reads.json', 'client-evidence.json'):
        writes[audit_rel + '/' + name] = (w / name).read_bytes()
    writes['assets/asset-patch/manifest.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')

    for rel in writes:
        path = (p.REPO / rel).resolve()
        assert path.is_relative_to(p.REPO.resolve())
        assert not path.is_relative_to((p.REPO / '.cdn').resolve())
        if path.exists():
            backup = w / 'applied-before' / rel
            assert not backup.exists(), 'never replace an earlier application backup'
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(path.read_bytes())
    assert (p.REPO / 'assets/asset-patch/manifest.json').read_bytes() == c.manifest_bytes
    delivery = []
    for rel, raw in writes.items():
        path = p.REPO / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        assert path.read_bytes() == raw
        delivery.append({'path': rel, 'sha256': p.sha(raw)})
    after = p.Chain()
    assert after.tail == '1.4.104'
    final = {(r['root'], r['rel']): r['sha256'] for r in previous + resources}
    for key, digest in final.items():
        assert p.sha(after.get(key)) == digest
    p.savej(w / 'local-delivery.json', delivery)
    p.savej(w / 'applied-readback.json', {'tail': after.tail, 'resources': len(resources),
        'previous_and_new_resources_verified': len(final), 'archive': integrity,
        'manifest_sha256': p.sha(after.manifest_bytes)})
    print(json.dumps({'version': after.tail, 'resources': len(resources), 'local_files': len(delivery),
                      'readback_resources': len(final), 'archive_bytes': len(archive)}))


if __name__ == '__main__':
    main()
