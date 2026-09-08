"""Prepare the user-requested .102 release from the verified .102-.108 chain.

Writes only to --work. Retains every terminal byte, including independently
encoded iOS textures. Publication and retirement use the explicit receipt.
"""
import argparse
import copy
import io
import re
from pathlib import Path
import zipfile

import prepare_content as p
import fix_five_boss_icon_closure as icons

BASE = '1.4.101'
VERSION = '1.4.102'
OLD_TAIL = '1.4.108'
ARCHIVE = 'pinball-1.4.101-1.4.102-1-lens0907-0908-consolidated.zip'
MEMBER = re.compile(r'production/(upload|medium_upload|android_upload|ios_upload)/[a-f0-9]{2}/[a-f0-9]{38}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--ios-receipts', type=Path, required=True)
    args = ap.parse_args()
    w = args.work.resolve()
    assert not w.is_relative_to((p.REPO / '.cdn').resolve())
    w.mkdir(parents=True, exist_ok=True)
    c = p.Chain()
    assert c.tail == OLD_TAIL
    selected = [x for x in c.manifest['patches'] if x.get('enabled')
                and int(x['version'].split('.')[-1]) >= 102]
    assert [x['version'] for x in selected] == [f'1.4.{v}' for v in range(102, 109)]
    payloads, writers, source_archives = {}, {}, []
    for entry in selected:
        for name in entry.get('chain') or [entry['archive']]:
            source = p.REPO / 'assets/asset-patch/active' / name
            raw = source.read_bytes()
            receipt = next(r for r in entry['archive_integrity'] if r['name'] == name)
            assert p.sha(raw) == receipt['sha256'] and len(raw) == receipt['size']
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                assert z.testzip() is None
                assert len(z.namelist()) == len(set(z.namelist()))
                for member in z.namelist():
                    assert MEMBER.fullmatch(member), member
                    payloads[member] = z.read(member)
                    writers[member] = name
            source_archives.append({'path': f'assets/asset-patch/active/{name}',
                                    'sha256': p.sha(raw), 'bytes': len(raw)})
    # Compare against the actual effective terminal chain, not a donor snapshot.
    for member, raw in payloads.items():
        _, root, prefix, suffix = member.split('/')
        assert c.get((p.REVERSE_ROOTS[root], prefix + '/' + suffix)) == raw
    android = {n.replace('/android_upload/', '/ios_upload/')
               for n in payloads if '/android_upload/' in n}
    ios_members = {n for n in payloads if '/ios_upload/' in n}
    assert android <= ios_members
    ios_reports = []
    for receipt in p.readj(args.ios_receipts):
        logical = receipt['logical']
        rel = p.hrel(logical)
        # Two Android cut-ins were unchanged from .101 and were deduplicated
        # out of the original edge; their new iOS counterpart still belongs here.
        a = c.get(('android', rel))
        i = payloads[p.member(('ios', rel))]
        png = c.get(('medium', p.hrel(logical.removesuffix('.atf.deflate') + '.png')))
        decoded = p.wf_assets.png_decode_stored(png)
        assert p.sha(i) == receipt['sha256']
        assert p.sha(decoded) == receipt['png_sha256']
        pair = p.wf_atf.validate_cutin_platform_pair(p.wf_atf.inflate(a), p.wf_atf.inflate(i), decoded)
        assert pair == receipt['pair']
        ios_reports.append({'logical': logical, 'android_sha256': p.sha(a),
                            'ios_sha256': p.sha(i), 'png_sha256': p.sha(decoded), **pair})
    assert len(ios_reports) == len(ios_members) == 11
    tables = {name: c.get(('common', p.hrel(name))) for name in (icons.ITEM, icons.STAGE, icons.SHOP)}
    required = icons.requirements(tables)
    atlases = {base: icons.codec.decode_atlas(c.get(('common', p.hrel(base + icons.SUFFIXES[1]))))
               for base in icons.PRELOADED}
    icons.validate_closure(required, atlases)
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, raw in sorted(payloads.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 8, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, raw)
    archive = blob.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert z.testzip() is None and set(z.namelist()) == set(payloads)
        assert all(z.read(n) == raw for n, raw in payloads.items())
    integrity = {'name': ARCHIVE, 'size': len(archive), 'sha256': p.sha(archive),
                 'members': len(payloads), 'files': sorted(payloads)}
    manifest = copy.deepcopy(c.manifest)
    manifest['patches'] = [x for x in manifest['patches'] if x not in selected]
    manifest['patches'].append({'id': 'lens0907-0908-consolidated-1.4.102', 'type': 'patch',
        'name': '0907/0908 新内容与五重决战整合版',
        'description': '整合原 .102～.108 的角色、卡池、五重玩法、材料、奖励和四角色削弱；含完整 iOS 平台资源，配套 IPA 待后续制作。',
        'depends_on': BASE, 'version': VERSION, 'enabled': True,
        'archive': ARCHIVE, 'archive_size': len(archive), 'chain': [ARCHIVE],
        'archive_integrity': [integrity], 'files': sorted(payloads), 'created_at': '2026-09-08',
        'local_test_only': True, 'required_local_platform': 'android',
        'audit': {'directory': 'assets/asset-patch/audit/lens-consolidated-1.4.102', 'report': 'report.json'}})
    manifest['cdn_version'] = VERSION
    assert (p.REPO / 'assets/asset-patch/manifest.json').read_bytes() == c.manifest_bytes
    (w / ARCHIVE).write_bytes(archive)
    (w / 'manifest.before.json').write_bytes(c.manifest_bytes)
    p.savej(w / 'manifest.after.json', manifest)
    for name, raw in payloads.items():
        dest = w / 'prepared' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
    report = {'base': BASE, 'version': VERSION, 'previous_terminal': OLD_TAIL,
        'archive': integrity, 'retire_exact_paths': source_archives,
        'terminal_equivalent': True, 'ios_pairs': ios_reports,
        'platform_counts': {root: sum(f'/{root}/' in n for n in payloads)
                            for root in p.REVERSE_ROOTS},
        'required_preloaded_materials': required, 'ipa_changed': False,
        'ios_runtime_pending': True, 'device_tested': False,
        'resources': [{'member': n, 'bytes': len(raw), 'sha256': p.sha(raw), 'last_writer': writers[n]}
                      for n, raw in sorted(payloads.items())]}
    p.savej(w / 'report.json', report)
    print({'version': VERSION, 'members': len(payloads), 'bytes': len(archive),
           'ios_pairs': len(ios_reports), 'terminal_equivalent': True})


if __name__ == '__main__':
    main()
