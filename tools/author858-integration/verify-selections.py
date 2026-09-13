"""Independent checks for the user's selected fields and the donor DSL correction."""
import argparse
import copy
import io
import json
import zipfile
import zlib
from fractions import Fraction
from pathlib import Path

import prepare as m
import verify as v


def changed_cells(a, b, path=()):
    if type(a) is not type(b): return [(path, a, b)]
    if isinstance(a, dict):
        return [x for k in a.keys() | b.keys() for x in changed_cells(a.get(k), b.get(k), path + (k,))]
    if isinstance(a, list):
        if len(a) != len(b): return [(path, a, b)]
        return [x for i, (left, right) in enumerate(zip(a, b)) for x in changed_cells(left, right, path + (i,))]
    return [] if a == b else [(path, a, b)]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--review', type=Path, required=True)
    ap.add_argument('--donor', type=Path, default=Path('F:/灰-全68角色与配套资源-1.4.858-20260912.zip'))
    ap.add_argument('--installed', action='store_true')
    args = ap.parse_args()
    w, review = args.work.resolve(), args.review.resolve()
    report = m.readj(w / 'prepared.json'); chain = m.p.Chain()
    expected_manifest = m.readj(w / 'apply-report.json')['manifest_after_sha256'] if args.installed else report['manifest_before_sha256']
    assert m.sha(chain.manifest_bytes) == expected_manifest
    index = {(a['root'], a['logical']): a for a in report['assets']}
    def before(root, logical):
        row = index.get((root, logical))
        if args.installed and row:
            return (w / 'before-client' / row['member']).read_bytes() if row['before_sha256'] is not None else None
        return chain.get((root, m.p.hrel(logical)))
    def effective(root, logical):
        if args.installed: return chain.get((root, m.p.hrel(logical)))
        row = index.get((root, logical))
        return (w / 'prepared-client' / row['member']).read_bytes() if row else before(root, logical)
    payload = m.readj(review / 'metadata/tables/client_payload.json')['tables']
    roster = m.readj(review / 'metadata/roster/roster.json')['characters']
    codes = {x['code_name']: str(x['character_id']) for x in roster}
    # Check donor values independently of the selection log. Nested donor keys
    # are complete for their declared scope; unrelated current siblings survive.
    def contains(actual, expected):
        if 'children' in expected:
            assert 'children' in actual
            for key, value in expected['children'].items(): contains(actual['children'][key], value)
        elif 'csv' in expected: assert actual['csv'] == expected['csv']
        else: assert actual == {'empty': True}
    full_keys = 0
    for logical, table in payload.items():
        rows = m.p.rawmap(effective('common', logical))
        for key, node in table['keys'].items():
            if m.owner_ids(logical, key, node, codes) & m.FULL:
                contains(m.decoded(rows[key]), node); full_keys += 1
    changes = m.readj(w / 'table-changes.json')
    rolf_expected = {
        'master/character/full_shot_image_attribute.orderedmap': (('children', '1', 'csv', 0, 3), '872', '1000'),
        'master/generated/character_image.orderedmap': (('children', '1', 'csv', 0, 0), '187', '315'),
        'master/generated/trimmed_image.orderedmap': (('csv', 0, 0), '187', '315')}
    rolf = [x for x in changes if '179999' in x.get('owners', [])]
    assert len(rolf) == 3
    for x in rolf: assert changed_cells(x['before'], x['after']) == [rolf_expected[x['logical']]]
    for x in changes:
        if x['logical'] == 'master/character/character.orderedmap' and x['key'] in m.VOICES:
            cols = {path[-1] for path, _, _ in changed_cells(x['before'], x['after'])}
            assert cols == ({9, 10, 11, 14, 15, 16} if x['key'] == '119996' else {9, 14, 15, 16})
    # Explicitly rejected historical balance/date differences must stay absent.
    for logical, keys in {
        'master/ability/ability.orderedmap': ['1199963', '1499901'],
        'master/mana_board/mana_board2_open_condition.orderedmap': ['179999'],
        'master/string/custom_ability_string.orderedmap': ['ability_white_tiger_summer_1'],
    }.items():
        a, b = m.p.rawmap(before('common', logical)), m.p.rawmap(effective('common', logical))
        for key in keys:
            if key in a: assert a[key] == b[key], (logical, key)
    # Both Gerald forms are the already reviewed author trees; the two reviewed
    # preimages are still the effective baseline (no intervening skill edit).
    reviewed = m.readj(review / 'dsl-differences.json')
    gerald = [x for x in reviewed if 'white_wolf_gerald$' in x['logical']]
    assert len(gerald) == 2
    for x in gerald:
        old = v.wf_dsl.parse_dsl(zlib.decompress(before('common', x['logical']), -15))['tree']
        new = v.wf_dsl.parse_dsl(zlib.decompress(effective('common', x['logical']), -15))['tree']
        assert old == x['current_tree'] and new == x['donor_tree']
    fixes = m.readj(w / 'technical-fixes.json'); assert len(fixes) == 1
    fix = fixes[0]
    corrected = v.wf_dsl.parse_dsl(zlib.decompress(effective('common', fix['logical']), -15))['tree']
    original = copy.deepcopy(corrected); original[11][1][1][1][8] = ['Block', []]
    assert corrected[11][1][1][1][8] == ['DoNothing']
    negative = None
    try: v.wf_dsl_sig.validate_action_dsl(v.normalize(original, []))
    except Exception as error: negative = str(error)
    assert negative and 'IfTargetNotFound' in negative, negative
    v.wf_dsl_sig.validate_action_dsl(v.normalize(corrected, []))
    assert changed_cells(original, corrected) == [((11, 1, 1, 1, 8), ['Block', []], ['DoNothing'])]
    # All media reachable in the donor's selected-character inventory resolves
    # to identical effective bytes, our paired iOS payload, or the audited atlas.
    baseline = m.readj(w / 'client/inspection.json')
    apk = Path(baseline['apk']); assert m.sha(apk.read_bytes()) == baseline['apk_sha256']
    missing_rows = m.readj(review / 'current-apk-builtin-check.json')['rows']
    builtin = {x['logical']: x for x in missing_rows}
    manifest = m.readj(review / 'metadata/asset-manifest.json')
    existing_atlas_base = 'battle/effect/skill_unique/white_wolf_gerald/white_wolf_gerald'
    existing_atlas_members = {existing_atlas_base + ext for ext in ('.png', '.atlas.amf3.deflate')}
    donor_media = {}
    wanted = {a['member']: a for a in manifest['assets'] if a['root'] == 'common' and a['logical'] in existing_atlas_members}
    assert m.sha(args.donor.read_bytes()) == m.DONOR_SHA
    with zipfile.ZipFile(args.donor) as outer:
        for part in manifest['archives']:
            data = outer.read(part['path']); assert m.sha(data) == part['sha256']
            with zipfile.ZipFile(io.BytesIO(data)) as inner:
                for member in wanted.keys() & set(inner.namelist()):
                    asset = wanted[member]; raw = inner.read(member)
                    assert m.sha(raw) == asset['sha256']; donor_media[asset['logical']] = raw
            if len(donor_media) == 2: break
    assert len(donor_media) == 2
    images, frames = [], []
    for origin in ('current', 'donor'):
        def asset_bytes(ext):
            logical = existing_atlas_base + ext
            raw = effective('common', logical) if origin == 'current' else donor_media[logical]
            if origin == 'donor':
                entry, = [a for a in manifest['assets'] if a['root'] == 'common' and a['logical'] == logical]
                assert m.sha(raw) == entry['sha256']
            return raw
        images.append(m.atlas.decode_png(asset_bytes('.png')))
        frames.append({x['n']: x for x in m.atlas.decode_atlas(asset_bytes('.atlas.amf3.deflate'))})
    assert frames[0].keys() == frames[1].keys() and len(frames[0]) == 37
    assert all(m.opt.visible_signature(images[0], [frames[0][name]]) == m.opt.visible_signature(images[1], [frames[1][name]]) for name in frames[0])
    media_checked = builtin_checked = 0
    with zipfile.ZipFile(apk) as z:
        nested = {}
        def apk_asset(member):
            if '!' not in member: return z.read(member)
            outer, inner = member.split('!', 1)
            if outer not in nested: nested[outer] = zipfile.ZipFile(io.BytesIO(z.read(outer)))
            return nested[outer].read(inner)
        for asset in manifest['assets']:
            if not set(map(str, asset['character_ids'])) & m.FULL: continue
            root, logical = asset['root'], asset['logical']
            if logical in {'item/sprite_sheet.png', 'item/sprite_sheet.atlas.amf3.deflate', fix['logical'],
                          'rich_text/cnmod_abyss_limited_gacha_note.html.deflate',
                          'rich_text/cnmod_ashen_verdict_gacha_note.html.deflate'} | existing_atlas_members: continue
            raw = effective(root, logical)
            if raw is None:
                candidates = builtin[logical]['candidates']
                assert any(m.sha(apk_asset(x['member'])) == asset['sha256'] for x in candidates), logical
                builtin_checked += 1
            else:
                assert m.sha(raw) == asset['sha256'], (root, logical, 'selected media differs from donor')
            media_checked += 1
    # Exact rational probabilities, not rounded UI values or probabilistic draws.
    inputs = m.readj(review / 'gacha-review/runtime-input.json')
    chosen = m.readj(w / 'prepared-server/assets/gacha.json')
    mod_ids = {int(x['character_id']) for x in roster}
    gacha_checks = {}
    for gid in ('990001', '990002'):
        author, selected = inputs['donor'][gid], chosen[gid]
        assert selected['rankRates'] == author['rankRates']
        checked = 0
        for bucket, entries in author['pool'].items():
            after = selected['pool'][bucket]; am = {x['id']: x for x in after}
            author_mods = [x['id'] for x in entries if x['id'] in mod_ids]
            assert [x['id'] for x in after if x['id'] in mod_ids] == author_mods
            total_old, total_new = sum(x['odds'] for x in entries), sum(x['odds'] for x in after)
            for x in entries:
                if x['id'] not in mod_ids: continue
                y = am[x['id']]
                assert Fraction(x['odds'], total_old) == Fraction(y['odds'], total_new)
                assert all(x[k] == y[k] for k in ('rank', 'isRateUp', 'isLimited', 'trialReadingForced'))
                checked += 1
        before_rows = {x['id']: x for group in inputs['current'][gid]['pool'].values() for x in group}
        after_rows = {x['id']: x for group in selected['pool'].values() for x in group}
        ordinary = {cid for cid in before_rows if cid not in mod_ids}
        assert len(ordinary) == 432
        assert all(after_rows[cid]['isExchangeable'] == before_rows[cid]['isExchangeable'] for cid in ordinary)
        assert set(after_rows) - mod_ids == ordinary
        if gid == '990001':
            assert all(after_rows[cid]['isExchangeable'] for cid in (129992, 139995, 179981))
            assert all(not after_rows[int(cid)]['isExchangeable'] for cid in m.FULL | {'149990'})
        else:
            assert all(after_rows[cid]['odds'] == 0 and not after_rows[cid]['isExchangeable'] for cid in range(179982, 179987))
        gacha_checks[gid] = {'author_mod_probabilities_exact': checked, 'author_mod_order_and_highlights_preserved': True,
                             'ordinary_exchange_flags_preserved': len(ordinary)}
    result = {'status': 'passed', 'installed': args.installed, 'prepared_sha256': m.sha((w / 'prepared.json').read_bytes()),
        'complete_donor_table_keys_checked': full_keys, 'rolf_only_three_position_cells': True,
        'unselected_balance_and_date_changes_absent': True, 'gerald_both_reviewed_trees_matched': True,
        'donor_invalid_enum_negative_test': negative, 'corrected_dsl_positive_test': True,
        'selected_character_media_and_dependencies': media_checked, 'current_apk_builtin_dependencies': builtin_checked,
        'retained_gerald_optimized_atlas_identical_visible_frames': len(frames[0]),
        'gacha': gacha_checks, 'device_tested': False}
    m.writej(w / 'selection-verification.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
