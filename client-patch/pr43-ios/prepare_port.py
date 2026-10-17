"""Import the reviewed Android delta into the accepted iOS full AOT unit.

Keep all existing iOS declarations and native IDs. Only selected bodies change;
two helper classes and two closure methods append after the accepted prefix.
The result must still be compiled and linked against the accepted native image.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import types
import zlib

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE / 'support'))
from fixed_inputs import fixed_json
sys.path.insert(0, str(REPO / 'client-patch/lens0907-0908'))
import build_swf as p
import overlimit_ios
from native_support import INFO_OFFSET, backend, dump, read64, sha

ANDROID_SHA = 'ee871b6bdaa339afe4e4bea755bded1d26d828f2884e0fe17c481c627898c6b6'
ANDROID_REVISIONS = {
    'initial': ANDROID_SHA,
    'old-server-compat': '0d88486dc2a7c4016933efffdee7708895361f93d924c201f9b4387aba7ce678',
}
IOS_SHA = 'a3a7e2b465f14472164a2b7cb61fcdd7b57c3987cb76bf2e8cfa095620270ab8'
OLD_COUNT = 101466
HELPERS = ('cn.loading.BattlePackSlicer', 'cn.loading.GcGate')
POOL_FIELDS = ('ints', 'uints', 'doubles', 'strings', 'namespaces', 'ns_sets', 'multinames')


def view(abc):
    return p.View(types.SimpleNamespace(abc=abc), p.asm)


def class_importer():
    spec = importlib.util.spec_from_file_location('pr43_existing_class_importer',
                  REPO / 'client-patch/ios-cumulative-login/prepare.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ClassImporter


def abc_tags(raw):
    """Read DoABC payloads without rebuilding any original SWF tag."""
    from swfabc import swftags
    if raw[:3] == b'CWS':
        raw = zlib.decompress(raw[8:])
    elif raw[:3] == b'FWS':
        raw = raw[8:]
    else:
        raise ValueError('unsupported SWF compression')
    result = {}
    for kind, offset, header, length in swftags.iter_tags(raw):
        if kind != 82:
            continue
        data = raw[offset + header:offset + header + length]
        end = data.index(b'\0', 4)
        name = data[4:end].decode()
        # Existing game SWFs contain repeated engine tags; only requested
        # helpers are required to have a unique name.
        result.setdefault(name, []).append(data[end + 1:])
    return result


def validate_body(body, abc):
    p.asm._POP_PUSH[0xf2] = (0, 0)
    return p.check_body(body, abc)


def signature(v, mid):
    ret, params, _name, flags, options, names = v.a.methods[mid]
    def constant(value, kind):
        pools = {1: 'strings', 3: 'ints', 4: 'uints', 6: 'doubles'}
        if kind in pools:
            return kind, getattr(v.a, pools[kind])[value]
        if kind in (5, 8, 22, 23, 24, 25, 26):
            tag, name = v.a.namespaces[value]
            return kind, tag, v.a.s(name)
        return kind, value
    return (v.mn(ret), [v.mn(t) for t in params], flags,
            [constant(value, kind) for value, kind in options] if options is not None else None,
            [v.a.s(i) for i in names] if names is not None else None)


def run(out, *, input_ipa, input_full_abc, android_file, android_sha256=None, source_revision='old-server-compat'):
    from hud_adapter import adapt_hud_body
    import zipfile

    out = Path(out).resolve()
    assert not out.exists(), ('fresh output directory required', str(out))
    reg = fixed_json('baseline-contract.json')
    reg.update(ipa=str(Path(input_ipa).resolve()), full_abc=str(Path(input_full_abc).resolve()))
    assert sha(Path(reg['ipa']).read_bytes()) == reg['ipa_sha256'], 'Historical input IPA identity mismatch'
    full = Path(reg['full_abc']).read_bytes()
    assert sha(full) == reg['full_abc_sha256'] == IOS_SHA
    assert source_revision in ANDROID_REVISIONS, ('unknown donor revision', source_revision)
    expected_android_sha = ANDROID_REVISIONS[source_revision]
    assert android_sha256 in (None, expected_android_sha), 'donor hash does not match revision contract'
    android_file = Path(android_file)
    android = android_file.read_bytes()
    assert sha(android) == expected_android_sha
    # Fixed input identity is checked above; extract only two required members.
    with zipfile.ZipFile(reg['ipa']) as archive:
        native, swf = archive.read(reg['native_member']), archive.read(reg['swf_member'])
    assert sha(native) == reg['native_sha256'] and sha(swf) == reg['swf_sha256']
    assert hashlib.sha1(full).digest() == native[INFO_OFFSET:INFO_OFFSET + 20]
    target = view(p.abcfmt.ABC(full))
    assert target.a.serialize() == full and len(target.a.methods) == OLD_COUNT
    old = copy.deepcopy(target.a)
    source = p.View(p.SwfAbc(android_file), p.asm)
    importer = p.Importer(target, source)
    mapping = fixed_json('ios-method-map.json')
    mapped = {r['android_body']: r for r in mapping['rows']}
    plan = json.loads((REPO / 'client-patch/pr43-port/game-plan.json').read_text('utf8'))
    records, new_ids, helper_records = [], [], []

    # The two closures are not discoverable from iOS's stripped parent body.
    # Reserve them explicitly before importing BattleFlipperImpl.update.
    closures = (62995, 62996)
    for source_mid in closures:
        mid = len(target.a.methods)
        importer.methods[source_mid] = mid
        target.a.methods.append(importer.info(source_mid))
        new_ids.append(mid)
    for source_mid in closures:
        indices = [i for i, b in enumerate(source.a.bodies) if b[0] == source_mid]
        assert len(indices) == 1
        src = source.a.bodies[indices[0]]
        assert not src[6] and not src[7]
        assert not any(x.op in (0x40, 0x57, 0x65, 0x67) for x in p.asm.decode(src[5]))
        body = importer.body(indices[0], importer.methods[source_mid])
        target.a.bodies.append(body)
        validate_body(body, target.a)

    for item in plan['methods']:
        if item['action'] != 'apply_final_v33_semantic_delta':
            continue
        row = mapped[item['body']]
        assert row['signature_equal'] and not row['missing_ios_own_fields']
        ti, si = row['ios_body'], row['android_body']
        before = target.a.bodies[ti]
        assert before[0] == row['ios_method']
        assert sha(before[5]) == row['ios_body_sha256']
        assert signature(target, before[0]) == signature(source, source.a.bodies[si][0])
        body = importer.body(si, before[0], scope=before[3])
        adaptation = None
        if before[0] == 63979:
            body, adaptation = adapt_hud_body(target.a, body, p.asm)
        assert p.freeze(body[7]) == p.freeze(before[7]), ('activation traits changed', row['ios_label'])
        target.a.bodies[ti] = body
        proof = validate_body(body, target.a)
        records.append(dict(method_id=before[0], strategy='replace', label=row['ios_label'],
                            source_body=si, before_code_sha256=sha(before[5]),
                            after_code_sha256=sha(body[5]), adaptation=adaptation, validation=proof))
    assert len(records) == 37

    over = overlimit_ios.import_methods(importer, verify_body=validate_body, source_revision=source_revision)
    records.extend(dict(method_id=r['native_redirect_method'], strategy='replace', label=r['label'],
                        source_body=r['source_body_index'], after_code_sha256=sha(target.a.bodies[r['target_body_index']][5]))
                   for r in over['methods'])

    tags = abc_tags(android)
    shop_name = 'cn.shop.ShopFirstOpen'
    assert len(tags[shop_name]) == 1
    shop = view(p.abcfmt.ABC(tags[shop_name][0]))
    shop_importer = p.Importer(target, shop)
    labels = [label for label in shop.by_label if '/productIds|' in label]
    assert len(labels) == 1
    si, = shop.by_label[labels[0]]
    ti, = target.by_label[labels[0]]
    before = target.a.bodies[ti]
    assert before[0] == 101208
    assert signature(target, before[0]) == signature(shop, shop.a.bodies[si][0])
    body = shop_importer.body(si, before[0], scope=before[3])
    assert p.freeze(body[7]) == p.freeze(before[7])
    target.a.bodies[ti] = body
    records.append(dict(method_id=before[0], strategy='replace', label=labels[0],
                        before_code_sha256=sha(before[5]), after_code_sha256=sha(body[5]),
                        validation=validate_body(body, target.a)))

    merge = class_importer()
    for name in HELPERS:
        assert len(tags[name]) == 1
        helper = view(p.abcfmt.ABC(tags[name][0]))
        existing = {target.mn(r[0]) for r in target.a.instances}
        assert all(helper.mn(r[0]) not in existing for r in helper.a.instances)
        merger = merge(target, helper)
        ids = list(merger.methods.values())
        start = len(target.a.bodies)
        merger.merge()
        proofs = [validate_body(b, target.a) for b in target.a.bodies[start:]]
        new_ids.extend(ids)
        helper_records.append(dict(name=name, new_method_ids=ids, validations=proofs))
    assert len(new_ids) == 30 and len(target.a.methods) == OLD_COUNT + 30
    assert len(records) == 50 and len({r['method_id'] for r in records}) == 50
    # Prove every existing declaration/pool entry and unselected body is intact.
    for field in ('methods', 'metadata', 'instances', 'classes', 'scripts', *POOL_FIELDS):
        previous = getattr(old, field)
        assert p.freeze(previous) == p.freeze(getattr(target.a, field)[:len(previous)]), field
    changed = {r['method_id'] for r in records}
    untouched = 0
    for a, b in zip(old.bodies, target.a.bodies):
        assert a[0] == b[0]
        if a[0] not in changed:
            assert p.freeze(a) == p.freeze(b), a[0]
            untouched += 1
    result = target.a.serialize()
    assert p.abcfmt.ABC(result).serialize() == result
    link = backend()
    runtime = native[link.file_offset(native, read64(native, INFO_OFFSET + 24)):
                     link.file_offset(native, read64(native, INFO_OFFSET + 24)) + read64(native, INFO_OFFSET + 32)]
    out.mkdir(parents=True)
    (out / 'baseline-native').write_bytes(native)
    (out / 'baseline.swf').write_bytes(swf)
    (out / 'full.abc').write_bytes(result)
    report = dict(status='prepared_requires_aot_compile_and_link', source_ipa=reg,
                  full_abc_file='full.abc', full_abc_sha256=sha(result),
                  full_abc_sha1=hashlib.sha1(result).hexdigest(), old_methods=OLD_COUNT,
                  total_methods=len(target.a.methods), baseline_native_file='baseline-native',
                  baseline_swf_file='baseline.swf', baseline_runtime_abc_sha256=sha(runtime),
                  methods=records, new_method_ids=new_ids, compiled_helpers=new_ids,
                  permitted_native_entry_aliases={'63979': [101362], '93255': [101370], '18394': [101371]},
                  helper_records=helper_records, overlimit=over,
                  donor_android_swf_file=str(android_file.resolve()),
                  donor_android_swf_sha256=expected_android_sha, source_revision=source_revision,
                  original_full_abc_sha256=IOS_SHA,
                  unchanged_existing_bodies=untouched, old_declarations_and_pool_prefix_preserved=True,
                  device_tested=False)
    dump(out / 'port.json', report)
    print(json.dumps({k: report[k] for k in ('status', 'total_methods', 'full_abc_sha256', 'unchanged_existing_bodies')}))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--input-ipa', type=Path, required=True)
    parser.add_argument('--input-full-abc', type=Path, required=True)
    parser.add_argument('--android-swf', type=Path, required=True)
    parser.add_argument('--android-sha256')
    parser.add_argument('--source-revision', choices=sorted(ANDROID_REVISIONS), default='old-server-compat')
    args = parser.parse_args()
    run(args.out, input_ipa=args.input_ipa, input_full_abc=args.input_full_abc,
        android_file=args.android_swf, android_sha256=args.android_sha256,
        source_revision=args.source_revision)


if __name__ == '__main__':
    main()
