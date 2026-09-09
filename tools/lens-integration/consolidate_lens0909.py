"""Consolidate the explicitly approved 0909 test chain into 102 -> 103."""
import argparse
import copy
import io
import json
import zipfile
from pathlib import Path
import prepare_content as p


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    w = parser.parse_args().work.resolve()
    assert w.is_relative_to(Path('F:/codex/work').resolve())
    assert not w.is_relative_to((p.REPO / '.cdn').resolve())
    c = p.Chain()
    assert c.tail == '1.4.105', 'this historical consolidation locks its three input edges'
    selected = [x for x in c.manifest['patches'] if x.get('enabled') and x['version'] in ('1.4.103', '1.4.104', '1.4.105')]
    assert [(x['depends_on'], x['version']) for x in selected] == [('1.4.102', '1.4.103'), ('1.4.103', '1.4.104'), ('1.4.104', '1.4.105')]
    resources, payloads, sources = {}, {}, []
    for patch in selected:
        audit = p.REPO / patch['audit']['directory']
        for row in p.readj(audit / 'resources.json'):
            resources[row['member']] = row
        for name in patch['chain']:
            source = (p.REPO / 'assets/asset-patch/active' / name).resolve()
            assert source.parent == (p.REPO / 'assets/asset-patch/active').resolve()
            raw = source.read_bytes()
            expected = next(x for x in patch['archive_integrity'] if x['name'] == name)
            assert p.sha(raw) == expected['sha256']
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                assert z.testzip() is None and z.namelist() == expected['files']
                payloads.update({n: z.read(n) for n in z.namelist()})
            sources.append({'path': str(source), 'name': name, 'sha256': p.sha(raw), 'size': len(raw)})
    assert len(resources) == len(payloads) == 191
    for member, row in resources.items():
        assert p.sha(payloads[member]) == row['sha256']
        assert c.get((row['root'], row['rel'])) == payloads[member]
    # Inspect the exact bytes being retained, not the discarded earlier payloads.
    png_count = 0
    for member, row in resources.items():
        if row['logical'].endswith('.png'):
            raw = p.wf_assets.png_decode_stored(payloads[member])
            with p.Image.open(io.BytesIO(raw)) as im:
                im.load()
            png_count += 1
    ticket = p.csvrows(p.rawmap(payloads[p.member(('common', p.hrel('master/item/item.orderedmap'))) ])['10000143'])[0]
    revert = p.readj(p.REPO / 'assets/asset-patch/audit/lens0909-ticket-description-revert-1.4.105/report.json')
    assert ticket[5] == revert['description_after']
    name = 'pinball-1.4.102-1.4.103-1-lens0909-consolidated-cn.zip'
    archive_rel = 'assets/asset-patch/active/' + name
    audit_rel = 'assets/asset-patch/audit/lens0909-consolidated-1.4.103'
    assert not (p.REPO / archive_rel).exists() and not (p.REPO / audit_rel).exists()
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for member, raw in sorted(payloads.items()):
            assert len(Path(member).parts) == 4 and '..' not in Path(member).parts
            zi = zipfile.ZipInfo(member, (2026, 9, 9, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, raw)
    archive = out.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert z.testzip() is None and z.namelist() == sorted(payloads)
        for member, raw in payloads.items():
            assert z.read(member) == raw
    integrity = {'name': name, 'size': len(archive), 'sha256': p.sha(archive), 'members': len(payloads), 'files': sorted(payloads)}
    manifest = copy.deepcopy(c.manifest)
    manifest['patches'] = [x for x in manifest['patches'] if x not in selected]
    assert max(tuple(map(int, x['version'].split('.'))) for x in manifest['patches'] if x.get('enabled')) == (1, 4, 102)
    manifest['patches'].append({
        'id': 'lens0909-consolidated-1.4.103', 'type': 'patch', 'name': '0909 角色、五重与资源优化整合',
        'description': '合并角色调整、夏日白展示、五重难度与资源优化，保留我方卡池及原有规则，并恢复凭证原说明。',
        'version': '1.4.103', 'depends_on': '1.4.102', 'enabled': True,
        'archive': name, 'archive_size': len(archive), 'chain': [name], 'archive_integrity': [integrity],
        'files': sorted(payloads), 'created_at': '2026-09-09', 'local_test_only': False,
        'audit': {'directory': audit_rel, 'report': 'report.json'},
    })
    manifest['cdn_version'] = '1.4.103'
    report = {'status': 'consolidated_and_verified', 'cloud_baseline': '1.4.102', 'version': '1.4.103',
        'inputs': sources, 'archive': integrity, 'resources_equal_previous_terminal': len(payloads),
        'strict_pngs_decoded': png_count, 'ticket_description': ticket[5],
        'prior_manifest_sha256': p.sha(c.manifest_bytes),
        'scope': '用户明确要求合并测试增量为唯一 1.4.103。只整理版本与归档，终态资源逐字节保持；未修改安装包。',
        'h400_status': '部分已知原因修复；换场记录缺失仍待用新增诊断日志定位，尚未声称彻底修复。'}
    backup = w / 'source-before'
    assert not backup.exists()
    backup.mkdir(parents=True)
    (backup / 'manifest.json').write_bytes(c.manifest_bytes)
    # Exact-file moves are explicitly authorized by the version consolidation.
    for source in sources:
        src = Path(source['path']).resolve()
        dst = (backup / source['name']).resolve()
        assert src.parent == (p.REPO / 'assets/asset-patch/active').resolve()
        assert dst.is_relative_to(backup) and not dst.exists()
        assert p.sha(src.read_bytes()) == source['sha256']
    (p.REPO / archive_rel).write_bytes(archive)
    p.savej(p.REPO / audit_rel / 'resources.json', [resources[m] for m in sorted(resources)])
    p.savej(p.REPO / audit_rel / 'report.json', report)
    p.savej(p.REPO / 'assets/asset-patch/manifest.json', manifest)
    for source in sources:
        Path(source['path']).rename(backup / source['name'])
    final = p.Chain()
    assert final.tail == '1.4.103' and set(final.index) == set(c.index)
    for key, location in c.index.items():
        member = p.member(key)
        if member in payloads:
            assert final.get(key) == payloads[member]
        else:
            assert final.index[key] == location, 'unrelated resource source changed'
    p.savej(w / 'consolidation-readback.json', report)
    p.savej(w / 'retired-archives.json', sources)
    print(json.dumps({'version': final.tail, 'resources': len(payloads), 'pngs': png_count,
                      'archive_bytes': len(archive), 'prior_resources_preserved': len(final.index)}))


if __name__ == '__main__':
    main()
