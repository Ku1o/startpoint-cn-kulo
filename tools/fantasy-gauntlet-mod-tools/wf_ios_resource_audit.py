"""Audit effective custom Android/iOS resources, including legacy CDN and IPA.

Read-only: no client stores are materialized. An optional ZIP overlay permits
checking a proposed incremental repair before registering its manifest edge.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import zipfile

import wf_atf
import wf_live_cdn
import wf_mod_tool as core


@dataclass(frozen=True)
class Entry:
    archive: Path
    member: str
    version: tuple[int, ...]

    def read(self) -> bytes:
        with zipfile.ZipFile(self.archive) as archive:
            return archive.read(self.member)


def version(text: str) -> tuple[int, ...]:
    return tuple(int(v) for v in text.split('.'))


def archive_version(name: str) -> tuple[int, ...]:
    matches = re.findall(r'1\.4\.\d+', name)
    if not matches:
        raise ValueError(f'Archive has no resource version: {name}')
    return version(matches[-1])


def relative(logical: str) -> str:
    digest = core.sha1_path(logical)
    return digest[:2] + '/' + digest[2:]


def collect(root: Path):
    path = root / 'assets/asset-patch/manifest.json'
    manifest = json.loads(path.read_text('utf-8'))
    final = {}
    history = {}
    archives = {}
    for patch in manifest['patches']:
        if not patch.get('enabled', True):
            continue
        for name in patch.get('chain') or [patch['archive']]:
            source = root / 'assets/asset-patch/active' / name
            archives[source] = version(patch['version'])
            with zipfile.ZipFile(source) as archive:
                names = set()
                for info in archive.infolist():
                    if info.filename in names:
                        raise ValueError(f'Duplicate archive member: {source.name}/{info.filename}')
                    names.add(info.filename)
                    parts = info.filename.split('/')
                    if info.is_dir() or len(parts) != 4 or parts[0] != 'production':
                        continue
                    key = (parts[1], '/'.join(parts[2:]))
                    entry = Entry(source, info.filename, version(patch['version']))
                    final[key] = entry
                    history.setdefault(key, []).append(entry)
    return manifest, final, history, archives


def source_changed(current: Entry, history: list[Entry], ios_version) -> bool:
    if current.version <= ios_version:
        return False
    previous = [entry for entry in history if entry.version <= ios_version]
    return not previous or previous[-1].read() != current.read()


def logical_index(final):
    index = {}
    for logical in ('character_pedestal/sprite_sheet.png',
                    'character_pedestal/sprite_sheet.atlas.amf3.deflate',
                    'battle/common/layer0.png'):
        index[relative(logical)] = logical
    char_entry = final.get(('upload', relative(core.CHARACTER_LOGICAL)))
    if char_entry:
        rows = core.read_orderedmap_file_from_bytes(char_entry.read())
        for row in rows.values():
            code = row.split(',')[0]
            for number in range(6):
                logical = f'character/{code}/ui/skill_cutin_{number}.atf.deflate'
                index[relative(logical)] = logical
    # Cut-in names are not limited to _0/_1: matched and dragon variants exist.
    trimmed = final.get(('upload', relative('master/generated/trimmed_image.orderedmap')))
    if trimmed:
        for key in core.read_orderedmap_file_from_bytes(trimmed.read()):
            logical = key if key.endswith('.png') else key + '.png'
            if '/ui/skill_cutin_' in logical:
                logical = logical[:-4] + '.atf.deflate'
                index[relative(logical)] = logical
    return index


def inspect_pair(android: Entry, ios: Entry | None, png: Entry | None,
                 png_history: list[Entry]):
    if ios is None:
        return 'missing_ios'
    raw = wf_atf.inflate(android.read())
    other = wf_atf.inflate(ios.read())
    wf_atf.validate_cutin_platform_pair(raw, other)
    if png is None:
        return 'missing_source_png'
    if source_changed(png, png_history, ios.version):
        return 'stale_ios_source'
    return None


def audit(root: Path, cdn: Path, ipa: Path, overlays=()):
    manifest, final, history, archives = collect(root)
    plan = wf_live_cdn._build_ios_plan(cdn, root)
    if plan is None or str(plan.tail) != manifest['cdn_version']:
        raise ValueError('iOS replay tail does not match the enabled manifest')
    ios = {}
    for (platform, rel), entry in plan.entries.items():
        if platform == 'ios':
            source = Path(entry.zip_path)
            ios[rel] = Entry(source, entry.name, archives.get(source) or archive_version(source.name))
    with zipfile.ZipFile(ipa) as archive:
        bundle = {name.rsplit('ios_bundle/', 1)[1]: Entry(ipa, name, (1, 4, 0))
                  for name in archive.namelist() if '/asset/production/ios_bundle/' in name}
    for overlay in overlays:
        with zipfile.ZipFile(overlay) as archive:
            for name in archive.namelist():
                if name.startswith('production/ios_upload/'):
                    ios[name.removeprefix('production/ios_upload/')] = Entry(
                        overlay, name, archive_version(overlay.name))
    index = logical_index(final)
    counts = {'android_resources': 0, 'atf_pairs': 0, 'shared_pairs': 0}
    findings = []
    for (platform, rel), android in sorted(final.items()):
        if platform != 'android_upload':
            continue
        counts['android_resources'] += 1
        logical = index.get(rel)
        partner = ios.get(rel)
        data = android.read()
        reason = None
        try:
            if data.startswith(b'\x89png') or (logical and logical.endswith('.atlas.amf3.deflate')):
                counts['shared_pairs'] += 1
                partner = partner or bundle.get(rel)
                if partner is None or partner.read() != data:
                    reason = 'missing_or_stale_shared_ios'
            else:
                counts['atf_pairs'] += 1
                parsed = wf_atf.parse_atf(wf_atf.inflate(data))
                if parsed['slot'] != 2:
                    raise ValueError('Android asset is not ETC1 slot 2')
                if logical is None:
                    reason = 'unresolved_atf_logical'
                else:
                    png_rel = relative(logical.removesuffix('.atf.deflate') + '.png')
                    png_key = next((key for key in [('medium_upload', png_rel), ('upload', png_rel)]
                                    if key in final), None)
                    png = final.get(png_key)
                    reason = inspect_pair(android, partner, png, history.get(png_key, []))
        except (ValueError, KeyError) as exc:
            reason = 'invalid_pair: ' + str(exc)
        if reason:
            findings.append({'logical': logical, 'relative': rel, 'reason': reason,
                'android_archive': android.archive.name,
                'ios_archive': partner.archive.name if partner else None})
    return {'version': manifest['cdn_version'], 'ios_tail': str(plan.tail),
            'counts': counts, 'findings': findings,
            'manifest_sha256': hashlib.sha256((root/'assets/asset-patch/manifest.json').read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-root', type=Path, required=True)
    parser.add_argument('--cdn-root', type=Path)
    parser.add_argument('--ipa', type=Path)
    parser.add_argument('--overlay', action='append', type=Path, default=[])
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    ipa = args.ipa
    if ipa is None:
        record = json.loads((args.server_root/'client-patch/ios-accepted.json').read_text('utf-8'))
        ipa = Path(record['artifact']['ipa'])
    result = audit(args.server_root, args.cdn_root or args.server_root/'.cdn/cn', ipa, args.overlay)
    if args.report:
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return int(bool(result['findings']))


if __name__ == '__main__':
    raise SystemExit(main())
