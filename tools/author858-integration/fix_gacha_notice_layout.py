"""Append the two notice repairs as part 3 of .106 -> .107, without changing prose."""
import argparse
import copy
import hashlib
import html
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
import zlib

from gacha_notice import render_notice

ROOT = Path(__file__).resolve().parents[2]
VERSION = '1.4.107'
PART = 'pinball-1.4.106-1.4.107-3-gacha-note-layout.zip'
AUDIT = 'assets/asset-patch/audit/gacha-note-layout-1.4.107'
NOTICES = {
    'rich_text/cnmod_abyss_limited_gacha_note.html.deflate': '深渊限定扭蛋注意事项',
    'rich_text/cnmod_ashen_verdict_gacha_note.html.deflate': '深渊竞速池注意事项',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def packed_json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def prepare(work):
    manifest_path = ROOT / 'assets/asset-patch/manifest.json'
    before_manifest = manifest_path.read_bytes()
    original = json.loads(before_manifest)
    manifest = copy.deepcopy(original)
    enabled = [p for p in manifest['patches'] if p.get('enabled')]
    assert original['cdn_version'] == enabled[-1]['version'] == VERSION
    patch = enabled[-1]
    assert patch['depends_on'] == '1.4.106' and len(patch['chain']) == 2
    assert not (ROOT / 'assets/asset-patch/active' / PART).exists()
    prior_integrity = copy.deepcopy(patch['archive_integrity'])
    for info in prior_integrity:
        raw = (ROOT / 'assets/asset-patch/active' / info['name']).read_bytes()
        assert len(raw) == info['size'] and sha(raw) == info['sha256']
    payloads, rows = {}, []
    for logical, title in NOTICES.items():
        digest = hashlib.sha1((logical + 'K6R9T9Hz22OpeIGEWB0ui6c6PYFQnJGy').encode()).hexdigest()
        member = f'production/upload/{digest[:2]}/{digest[2:]}'
        winners = []
        for prior in enabled:
            for name in prior.get('chain') or [prior['archive']]:
                with zipfile.ZipFile(ROOT / 'assets/asset-patch/active' / name) as archive:
                    if member in archive.namelist():
                        winners.append((name, archive.read(member)))
        name, before = winners[-1]
        assert name == patch['chain'][1], 'Unexpected effective notice source'
        text = zlib.decompress(before, -15).decode('utf-8')
        old = ET.fromstring(text)
        assert old.find('body').find('p') is None and old.find('body').text.strip()
        paragraphs = [html.unescape(t) for t in text.split('<body>\n', 1)[1].rsplit('\n</body>', 1)[0].split('<br/><br/>\n')]
        repaired = render_notice(title, paragraphs)
        parsed = ET.fromstring(repaired.replace('<!DOCTYPE html/>\n', '', 1))
        body = parsed.find('body')
        container = body.find('div')
        assert body.attrib == {'class': 'body', 'style_id': '1'}
        assert container.attrib == {'class': 'container'}
        assert not body.text.strip() and not container.text.strip()
        actual = [''.join(p.itertext()) for p in container.findall('p')]
        assert actual == paragraphs, 'Notice prose changed'
        assert all(child.tag in ('p', 'br') and not (child.tail or '').strip() for child in container)
        after = zlib.compress(repaired.encode('utf-8'), level=9, wbits=-15)
        assert zlib.decompress(after, -15).decode('utf-8') == repaired
        payloads[member] = after
        stem = Path(logical).name
        (work / (stem + '.before.html')).write_bytes(text.encode('utf-8'))
        (work / (stem + '.after.html')).write_bytes(repaired.encode('utf-8'))
        rows.append(dict(logical=logical,member=member,source_archive=name,before_sha256=sha(before),
                         sha256=sha(after),size=len(after),paragraphs=len(paragraphs),prose_unchanged=True,
                         native_paragraph_nodes=True,shared_android_ios=True))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for member in sorted(payloads):
            info = zipfile.ZipInfo(member, date_time=(2026,9,13,0,0,0))
            info.external_attr = 0o644 << 16
            archive.writestr(info,payloads[member],compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    raw_zip = stream.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
        assert archive.namelist() == sorted(payloads) and archive.testzip() is None
        assert all(archive.read(member) == raw for member, raw in payloads.items())
    integrity = dict(name=PART,size=len(raw_zip),sha256=sha(raw_zip),members=2,files=sorted(payloads))
    patch['chain'].append(PART)
    patch['archive_integrity'].append(integrity)
    patch['archive_size'] = sum(i['size'] for i in patch['archive_integrity'])
    patch['files'] = sorted(set(patch['files']) | set(payloads))
    patch.setdefault('changes', []).append('第三分包修复深渊池及竞速池注意事项多行叠字，恢复原生段落排版，说明文字、概率及兑换规则不变。')
    patch.setdefault('audit', {})['gacha_note_layout_directory'] = AUDIT
    assert manifest['cdn_version'] == original['cdn_version']
    assert manifest['patches'][:-1] == original['patches'][:-1]
    assert patch['archive_integrity'][:-1] == prior_integrity
    after_manifest = packed_json(manifest)
    report = dict(status='static_verified',version=VERSION,depends_on='1.4.106',same_version_part=3,
                  root_cause='Bare body text inherits bundled body line-height 1.4, interpreted as an absolute 1.4px by RichTextLength; P uses its native 1em line-height.',
                  save_impact='Text markup only; no persisted IDs, schema, probabilities or exchange rules changed.',
                  archive=integrity,notices=rows,prior_archives_preserved=prior_integrity,
                  manifest_before_sha256=sha(before_manifest),manifest_after_sha256=sha(after_manifest),
                  client_refresh_handled_by_user=True,device_ui_verified=False)
    (work/'manifest.after.json').write_bytes(after_manifest)
    (work/PART).write_bytes(raw_zip)
    (work/'repair-report.json').write_bytes(packed_json(report))
    return before_manifest,after_manifest,raw_zip,report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();work=args.work.resolve()
    assert not work.is_relative_to((ROOT/'.cdn').resolve())
    work.mkdir(parents=True,exist_ok=True)
    before,after,archive,report=prepare(work)
    if args.apply:
        destination=(ROOT/'assets/asset-patch/active'/PART).resolve()
        audit=(ROOT/AUDIT).resolve()
        assert destination.is_relative_to(ROOT.resolve()) and audit.is_relative_to(ROOT.resolve())
        assert not destination.is_relative_to((ROOT/'.cdn').resolve()) and not audit.exists()
        assert (ROOT/'assets/asset-patch/manifest.json').read_bytes()==before
        destination.write_bytes(archive)
        audit.mkdir(parents=True)
        for path in work.glob('*.before.html'):
            (audit/path.name).write_bytes(path.read_bytes())
        for path in work.glob('*.after.html'):
            (audit/path.name).write_bytes(path.read_bytes())
        (audit/'report.json').write_bytes(packed_json(report))
        (ROOT/'assets/asset-patch/manifest.json').write_bytes(after)
    print(json.dumps({'applied':args.apply,'version':VERSION,'part':3,'archive':report['archive'],'notices':report['notices']},ensure_ascii=False))


if __name__=='__main__':
    main()
