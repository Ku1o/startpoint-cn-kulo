"""Build portable, data-driven offline character review pages. No game/source writes.

The inventory is supplied by the production adapter, not discovered by this tool.
Hash/coverage checks do not certify native semantics, aesthetics or playback.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOTS = tuple(Path(value).resolve() for value in os.environ.get(
    'STARPOINT_PREVIEW_ROOTS', '').split(os.pathsep) if value)
TEMPLATE = Path(__file__).resolve().parent.parent / 'assets/character-preview-v1'
ARRAYS = ('forms', 'assets', 'ui', 'motions', 'media', 'mechanics', 'checks', 'inventory', 'extras')
STATES = {'ready', 'pending', 'not_applicable'}
EXTENSIONS = {'image': {'.png', '.jpg', '.jpeg', '.webp', '.gif'},
              'audio': {'.wav', '.mp3', '.ogg', '.m4a'}, 'video': {'.mp4', '.webm'}}
RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
            *(f'LPT{i}' for i in range(1, 10))}


class PreviewError(ValueError):
    pass


def require(value, message):
    if not value:
        raise PreviewError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(path):
    return json.loads(Path(path).read_text('utf-8-sig'))


def safe_output(value):
    lexical = Path(value).absolute()
    resolved = lexical.resolve()
    require(not resolved.is_relative_to(Path(__file__).resolve().parents[3]),
            'Source-repository output forbidden')
    require(any(resolved != root and resolved.is_relative_to(root) for root in ROOTS),
            'Output must be strictly within an explicit STARPOINT_PREVIEW_ROOTS directory')
    for part in (*lexical.parts, *resolved.parts):
        require(part.lower() not in {'.cdn', '.git'}, 'Protected output path')
        require(part.rstrip(' .') == part and part.split('.')[0].upper() not in RESERVED
                and (':' not in part or part in {lexical.anchor, resolved.anchor}),
                'Unsafe output component')
    require(not lexical.is_symlink(), 'Output symlink forbidden')
    return resolved


def save_new(path, data):
    path = safe_output(path)
    require(not path.exists(), f'Refusing to overwrite {path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def ident(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', value),
            f'Invalid identifier: {value!r}')
    return value


def string(value, label, empty=False):
    require(isinstance(value, str) and (empty or value.strip()), f'{label}: expected text')
    return value


def starter(code, name=None):
    ident(code)
    return {'schemaVersion': 1, 'character': {'code': code, 'name': name or code,
            'subtitle': '制作中 · 素材与设计待补齐'},
            **{key: [] for key in ARRAYS},
            'inventoryScope': '待从本角色实际设计和最终原生资源清单建立；空清单不是完整性证明。',
            'checks': [{'id': key, 'label': label, 'state': 'pending', 'note': '待制作或检查'}
                       for key, label in [('brief', '设计与官方参考'), ('mechanics', '玩法与数值'),
                       ('illustration', '立绘'), ('ui', 'UI 全用途裁剪'), ('pixel_motion', '人物动作'),
                       ('active_fx', '主动技能演出'), ('audio', '台词与声音'), ('assembly', '原生总装')]]}


def validate(spec, base, check_files=True):
    require(isinstance(spec, dict) and spec.get('schemaVersion') == 1, 'Expected schemaVersion 1')
    char = spec.get('character', {})
    require(isinstance(char, dict), 'character: object required')
    ident(char.get('code'))
    string(char.get('name'), 'character.name')
    string(char.get('subtitle', ''), 'character.subtitle', True)
    for name in ARRAYS:
        require(isinstance(spec.get(name), list), f'{name}: array required')
        require(all(isinstance(row, dict) for row in spec[name]), f'{name}: objects required')
    missing, assets, paths, entries = [], {}, {}, {}

    def miss(key, reason):
        missing.append({'id': key, 'reason': reason})

    for a in spec['assets']:
        key = ident(a.get('id'))
        require(key not in assets, f'Duplicate asset {key}')
        require(a.get('kind') in EXTENSIONS, f'{key}: unsupported media kind')
        source = string(a.get('path'), f'{key}.path')
        require('://' not in source, f'{key}: local files required')
        p = Path(source)
        p = (base / p).resolve() if not p.is_absolute() else p.resolve()
        require(p.suffix.lower() in EXTENSIONS[a['kind']], f'{key}: disallowed file extension')
        require(re.fullmatch('[0-9a-f]{64}', a.get('sha256', '')) is not None,
                f'{key}: actual lowercase sha256 required')
        if check_files:
            require(p.is_file() and digest(p) == a['sha256'], f'{key}: missing or stale media {p}')
        assets[key], paths[key] = a, p

    def asset_ref(ref, kind, label, optional=False):
        if optional and ref is None:
            return False
        require(isinstance(ref, str) and ref in assets and assets[ref]['kind'] == kind,
                f'{label}: missing/wrong-kind asset {ref}')
        return True

    forms = set()
    for f in spec['forms']:
        key = ident(f.get('id'))
        require(key not in forms, f'Duplicate form {key}')
        forms.add(key)
        string(f.get('label'), f'{key}.label')
        entries[key] = {'kind': 'illustration', 'ready': asset_ref(f.get('illustration'), 'image', key, True)}
        if not entries[key]['ready']:
            miss(key, '立绘待制作')

    for category in ('ui', 'motions', 'media'):
        for row in spec[category]:
            key = ident(row.get('id'))
            require(key not in entries, f'Duplicate display entry {key}')
            string(row.get('label'), f'{key}.label')
            string(row.get('note', ''), f'{key}.note', True)
            if category == 'motions':
                for number in ('fps', 'displayScale'):
                    v = row.get(number)
                    require(type(v) in (int, float) and math.isfinite(v) and 0 < v <= 240,
                            f'{key}: invalid {number}')
                require(isinstance(row.get('frames'), list), f'{key}: frames required')
                if 'viewport' in row:
                    vp = row['viewport']
                    require(isinstance(vp, dict) and all(type(vp.get(n)) is int and vp[n] >= 0 for n in ('x', 'y'))
                            and all(type(vp.get(n)) is int and vp[n] > 0 for n in ('width', 'height')),
                            f'{key}: invalid fixed viewport')
                for frame in row['frames']:
                    require(isinstance(frame, dict), f'{key}: frame object required')
                    asset_ref(frame.get('asset'), 'image', key)
                    require(type(frame.get('ticks')) is int and 0 < frame['ticks'] <= 100000,
                            f'{key}: invalid ticks')
                ready = bool(row['frames'])
                kind = 'motion'
                if not ready:
                    miss(key, '动作帧待制作')
            else:
                state = row.get('status')
                require(state in STATES, f'{key}: invalid status')
                kind = 'image' if category == 'ui' else row.get('kind')
                require(category == 'ui' or kind in {'audio', 'video'}, f'{key}: invalid media kind')
                present = asset_ref(row.get('asset'), kind, key, True)
                require(state != 'ready' or present, f'{key}: ready entry has no media')
                ready = state == 'ready' and present
                if state == 'pending':
                    miss(key, row.get('note') or '素材或审阅待完成')
                if state == 'not_applicable':
                    require(row.get('note', '').strip(), f'{key}: omission reason required')
                if category == 'ui':
                    require(row.get('form') is None or row['form'] in forms, f'{key}: unknown form')
                    string(row.get('variant'), f'{key}.variant')
                    require(isinstance(row.get('resourceKeys'), list)
                            and all(isinstance(x, str) and x for x in row['resourceKeys']),
                            f'{key}: resourceKeys required')
                    require(state != 'ready' or row['resourceKeys'],
                            f'{key}: ready UI requires at least one inventory resource key')
                    kind = 'ui'
                else:
                    require(row.get('section') in {'overview', 'actions', 'skill'}, f'{key}: invalid section')
                    string(row.get('caption', ''), f'{key}.caption', True)
                    kind = 'audio' if kind == 'audio' else 'skill'
            entries[key] = {'kind': kind, 'ready': ready}

    keys, covered = set(), 0
    for inv in spec['inventory']:
        key = string(inv.get('key'), 'inventory.key')
        require(key not in keys, f'Duplicate inventory key {key}')
        keys.add(key)
        require(inv.get('category') in {'ui', 'motion', 'audio', 'illustration', 'skill'}, f'{key}: invalid inventory category')
        require(inv.get('status') in STATES, f'{key}: invalid inventory status')
        entry = inv.get('entry')
        if entry is not None:
            require(entry in entries, f'{key}: unknown inventory entry {entry}')
            require(entries[entry]['kind'] == inv['category'], f'{key}: wrong inventory category')
        if inv['status'] == 'ready':
            require(entry is not None and entries[entry]['ready'], f'{key}: falsely ready inventory entry')
            if inv['category'] == 'ui':
                ui = next(x for x in spec['ui'] if x['id'] == entry)
                require(key in ui['resourceKeys'], f'{key}: UI reverse mapping missing')
            covered += 1
        elif inv['status'] == 'not_applicable':
            require(inv.get('note', '').strip(), f'{key}: omission reason required')
        else:
            miss(key, inv.get('note') or '资源清单中有待展示项')
    # Prevent cards without a corresponding inventory row from inflating coverage.
    for ui in spec['ui']:
        for key in ui['resourceKeys']:
            require(any(inv['key'] == key and inv['entry'] == ui['id'] for inv in spec['inventory']),
                    f'{ui["id"]}: resource key absent from inventory: {key}')
    for category, label in (('forms', '立绘'), ('ui', 'UI 裁剪'), ('motions', '人物动作'),
                            ('media', '声音与演出'), ('mechanics', '玩法数值'), ('inventory', '实际资源覆盖清单')):
        if not spec[category]:
            miss(category, label + '尚未建立')
    for key in ('mechanics', 'extras'):
        for row in spec[key]:
            string(row.get('title'), key + '.title')
            string(row.get('text'), key + '.text', True)
    check_ids = set()
    for c in spec['checks']:
        ident(c.get('id'))
        require(c['id'] not in check_ids, 'Duplicate check id')
        check_ids.add(c['id'])
        string(c.get('label'), 'check.label')
        require(c.get('state') in {'pending', 'offline_checked', 'approved', 'deferred_to_game', 'not_applicable'},
                'Invalid check state; game certification is not supported')
        string(c.get('note'), 'check.note')
        if c['state'] == 'pending':
            miss(c['id'], c['note'])
    if 'inventoryScope' in spec:
        string(spec['inventoryScope'], 'inventoryScope')
    require(isinstance(spec.get('sourceBindings', []), list), 'sourceBindings: array required')
    for b in spec.get('sourceBindings', []):
        require(isinstance(b, dict) and isinstance(b.get('path'), str), 'Invalid source binding')
        p = (base / b['path']).resolve()
        require(p.is_file() and digest(p) == b.get('sha256'), 'Stale source inventory/selection binding')
    return paths, {'missing': missing, 'inventoryCount': len(keys), 'coveredCount': covered,
                   'assetCount': len(assets), 'gameVerified': False,
                   'coverageMeaning': '仅核对提供的资源清单与展示映射；须由制作流程核对清单是否完整。'}


def public_data(spec):
    # Explicit allowlist: never copy arbitrary private report fields into a shareable page.
    fields = {'forms': ('id', 'label', 'illustration'), 'assets': ('id', 'kind', 'path', 'sha256'),
              'ui': ('id', 'label', 'asset', 'form', 'variant', 'resourceKeys', 'status', 'note'),
              'motions': ('id', 'label', 'displayScale', 'fps', 'frames', 'viewport', 'note'),
              'media': ('id', 'label', 'kind', 'asset', 'section', 'caption', 'status', 'note'),
              'mechanics': ('title', 'text'), 'checks': ('id', 'label', 'state', 'note'),
              'inventory': ('key', 'category', 'entry', 'status', 'note'), 'extras': ('title', 'text')}
    result = {'schemaVersion': 1, 'character': {k: spec['character'].get(k, '') for k in ('code', 'name', 'subtitle')}}
    for name in ARRAYS:
        result[name] = [{key: copy.deepcopy(row[key]) for key in fields[name] if key in row} for row in spec[name]]
    result['inventoryScope'] = spec.get('inventoryScope', '制作者提供的资源集合；范围完整性待独立核验。')
    for m in result['motions']:
        m['frames'] = [{k: frame[k] for k in ('asset', 'ticks')} for frame in m['frames']]
    return result


def build(spec_path, out):
    spec_path = Path(spec_path).resolve()
    before = digest(spec_path)
    spec = load(spec_path)
    paths, computed = validate(spec, spec_path.parent)
    template_files = [TEMPLATE / name for name in ('index.html', 'style.css', 'player.js')]
    require(all(p.is_file() for p in template_files), 'Template is incomplete')
    out = safe_output(out)
    require(not out.exists(), 'Build into a new version directory; existing review snapshots are preserved')
    # All inputs validated before the first output write.
    out.mkdir(parents=True)
    (out / 'media').mkdir()
    data = public_data(spec)
    copied = set()
    for a in data['assets']:
        source = paths[a['id']]
        relative = 'media/' + a['sha256'] + source.suffix.lower()
        if relative not in copied:
            raw = source.read_bytes()
            require(hashlib.sha256(raw).hexdigest() == a['sha256'], 'Media changed during build')
            (out / relative).write_bytes(raw)
            copied.add(relative)
        a['path'] = relative
    for p in template_files:
        (out / p.name).write_bytes(p.read_bytes())
    data['computed'] = computed
    encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    (out / 'preview-data.js').write_text('window.CHARACTER_PREVIEW = ' + encoded + ';\n', encoding='utf-8')
    require(digest(spec_path) == before, 'Spec changed during build')
    files = {p.relative_to(out).as_posix(): digest(p) for p in sorted(out.rglob('*')) if p.is_file()}
    manifest = {'schemaVersion': 1, 'templateVersion': 1, 'specSha256': before,
                'builderSha256': digest(__file__), 'files': files,
                'gameVerified': False, 'browserPlaybackVerified': False}
    save_new(out / 'bundle.json', manifest)
    result = verify(out)
    return {**result, 'index': str(out / 'index.html'), 'missing': computed['missing']}


def verify(out):
    out = Path(out).resolve()
    manifest = load(out / 'bundle.json')
    require(manifest.get('schemaVersion') == 1 and isinstance(manifest.get('files'), dict), 'Invalid bundle manifest')
    actual = {p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file()}
    require(actual == set(manifest['files']) | {'bundle.json'}, 'Bundle file set differs from manifest')
    for name, expected in manifest['files'].items():
        p = (out / name).resolve()
        require(p.is_relative_to(out) and p != out, 'Escaping bundle path')
        require(digest(p) == expected, f'Bundle leaf changed: {name}')
    raw = (out / 'preview-data.js').read_text('utf-8')
    prefix = 'window.CHARACTER_PREVIEW = '
    require(raw.startswith(prefix) and raw.endswith(';\n'), 'Invalid data wrapper')
    data = json.loads(raw[len(prefix):-2])
    for a in data['assets']:
        require(re.fullmatch(r'media/[0-9a-f]{64}\.[a-z0-9]+', a['path']) is not None,
                'Nonportable media path')
        require(a['path'] in manifest['files'], 'Unregistered media file')
    _, computed = validate(data, out)
    require(computed == data.get('computed'), 'Derived missing/coverage data differs')
    require(manifest.get('gameVerified') is False and manifest.get('browserPlaybackVerified') is False,
            'Build cannot certify game or browser playback')
    return {'status': 'offline_bundle_structure_verified', 'fileCount': len(actual),
            **computed, 'browserPlaybackVerified': False, 'deviceVerified': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    cmds = parser.add_subparsers(dest='command', required=True)
    ini = cmds.add_parser('init', help='Create an empty character preview specification')
    ini.add_argument('--out', required=True)
    ini.add_argument('--character-code', required=True)
    ini.add_argument('--name')
    for name in ('check', 'build'):
        cmd = cmds.add_parser(name)
        cmd.add_argument('--spec', required=True)
        if name == 'build':
            cmd.add_argument('--out', required=True)
        cmd.add_argument('--report')
    ver = cmds.add_parser('verify')
    ver.add_argument('--bundle', required=True)
    ver.add_argument('--report')
    args = parser.parse_args(argv)
    try:
        report = getattr(args, 'report', None)
        if report:
            require(not safe_output(report).exists(), 'Report already exists')
        if args.command == 'init':
            save_new(args.out, starter(args.character_code, args.name))
            result = {'status': 'initialized_pending_preview', 'spec': str(Path(args.out).resolve())}
        elif args.command == 'check':
            spec = Path(args.spec).resolve()
            _, result = validate(load(spec), spec.parent)
            result = {'status': 'spec_structure_checked', **result}
        elif args.command == 'build':
            result = build(args.spec, args.out)
        else:
            result = verify(args.bundle)
        if report:
            save_new(report, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (PreviewError, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
