"""Verify sparse author 858 candidates and export native rows for runtime parity."""
import argparse
import copy
import io
import json
import sys
import zlib
from collections import Counter
from pathlib import Path

import prepare as merge
p = merge.p
import wf_dsl
import wf_dsl_sig

NULLABLE = {('CreateCondition', 8): ['Skill'], ('CreateSummonsMultiball', 13): {},
            ('MultiballNumberVariable', 3): []}

def normalize(tree, log):
    """Signature-only sentinels; serialized gameplay values stay unchanged.

    ActionEvaluator case 36 selects context SLv when p13 is null. Case 107
    forwards p3 to SquadImpl.matchMultiball, where null means all multiballs.
    Exact accepted SWF disassembly and hashes are kept in the client receipt.
    """
    tree = copy.deepcopy(tree)
    def walk(value):
        if isinstance(value, list):
            if len(value) == 2 and value[0] in ('Command', 'Event') and isinstance(value[1], list):
                name = value[1][0]
                for i, x in enumerate(value[1][1:], 1):
                    if x is None:
                        assert (name, i) in NULLABLE, (name, i)
                        value[1][i] = copy.deepcopy(NULLABLE[name, i]); log.append([name, i])
            for x in value: walk(x)
        elif isinstance(value, dict):
            for x in value.values(): walk(x)
    walk(tree)
    return tree

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--review', type=Path, required=True); ap.add_argument('--installed', action='store_true')
    args = ap.parse_args()
    w, review = args.work.resolve(), args.review.resolve()
    report = merge.readj(w / 'prepared.json'); chain = p.Chain()
    assert report['ios_completed'] == report['ios_required'] == 12 and not report['ios_skipped']
    expected_manifest = merge.readj(w / 'apply-report.json')['manifest_after_sha256'] if args.installed else report['manifest_before_sha256']
    assert merge.sha(chain.manifest_bytes) == expected_manifest
    index = {(a['root'], a['logical']): a for a in report['assets']}
    def before(root, logical):
        row = index.get((root, logical))
        if args.installed and row:
            return (w / 'before-client' / row['member']).read_bytes() if row['before_sha256'] is not None else None
        return chain.get((root, p.hrel(logical)))
    def effective(root, logical):
        if args.installed: return chain.get((root, p.hrel(logical)))
        row = index.get((root, logical))
        return (w / 'prepared-client' / row['member']).read_bytes() if row else before(root, logical)
    dsl_checks, png_count = [], 0
    for a in report['assets']:
        blob = effective(a['root'], a['logical']); old = before(a['root'], a['logical'])
        assert merge.sha(blob) == a['sha256']
        assert (merge.sha(old) if old is not None else None) == a['before_sha256']
        if a['logical'].endswith('.png'):
            assert blob[:8] == p.wf_assets.PNG_FAKE
            with p.Image.open(io.BytesIO(p.wf_assets.png_decode_stored(blob))) as im: im.load()
            png_count += 1
        if '.dsl.amf3.deflate' in a['logical']:
            tree = wf_dsl.parse_dsl(zlib.decompress(blob, -15))['tree']; nullable = []
            try:
                wf_dsl_sig.validate_action_dsl(normalize(tree, nullable))
            except Exception as error:
                raise ValueError(f"{a['logical']}: {error}") from error
            readback = wf_dsl.parse_dsl(wf_dsl.encode_amf3(tree))['tree']
            assert readback == tree
            wf_dsl_sig.validate_action_dsl(normalize(readback, []))
            if 'white_tiger_summer$' in a['logical']:
                old_tree = wf_dsl.parse_dsl(zlib.decompress(old, -15))['tree']
                hit = tree
                for key in [11, 1, 11, 1, 1, 1, 1, 1]: hit = hit[key]
                assert hit[0] == 'CreateHitArea' and hit[24] == 2
                attack = hit[23][1][0][1]
                assert attack[0] == 'CreateNormalAttack' and attack[6] == [{'min': 75.0, 'max': 75.0}]
                expected = copy.deepcopy(old_tree); old_hit = expected
                for key in [11, 1, 11, 1, 1, 1, 1, 1]: old_hit = old_hit[key]
                assert old_hit[0] == 'CreateHitArea' and old_hit[24] == 0
                old_hit[24] = 2
                old_hit[23][1][0][1][6] = [{'min': 75.0, 'max': 75.0}]
                assert expected == tree, 'summer skill changed beyond multiplier and damage origin'
            dsl_checks.append({'logical': a['logical'], 'sha256': a['sha256'], 'nullable_positions': nullable})
    assert len(dsl_checks) == 29
    for row in merge.readj(w / 'ios-pairs.json'):
        logical = row['logical']; png_path = logical.replace('.atf.deflate', '.png')
        png = p.wf_assets.png_decode_stored(effective('medium', png_path))
        p.wf_atf.validate_cutin_platform_pair(p.wf_atf.inflate(effective('android', logical)),
                                             p.wf_atf.inflate(effective('ios', logical)), png)
    # Every unaffected stored table key, including the other part's weapon rows, stays byte-exact.
    table_changes = merge.readj(w / 'table-changes.json')
    allowed = {}
    for x in table_changes: allowed.setdefault(x['logical'], set()).add(x['key'])
    for (root, logical), a in index.items():
        if not logical.startswith('master/'): continue
        old, new = p.rawmap(before(root, logical)), p.rawmap(effective(root, logical))
        if logical.startswith('master/gacha_odds/'): continue
        assert set(old) - set(new) == set()
        for k in set(old) | set(new):
            if old.get(k) != new.get(k): assert k in allowed.get(logical, set()), (logical, k)
    for cid in merge.DATES:
        row = p.csvrows(p.rawmap(effective('common', 'master/mana_board/mana_board2_open_condition.orderedmap'))[cid])[0]
        assert row[0].startswith('2000-01-01') and row[1].startswith('2199-12-31')
    # Existing saved node identities survive; all four new boards have 23 + 18 distinct nodes.
    node_report = []
    for logical in ('master/generated/mana_board.orderedmap', 'master/mana_board/mana_node.orderedmap'):
        old, new = p.rawmap(before('common', logical)), p.rawmap(effective('common', logical))
        for cid in old:
            if old[cid] == new[cid]: continue
            old_levels, new_levels = p.rawmap(old[cid]), p.rawmap(new[cid])
            assert set(old_levels) == set(new_levels), (logical, cid)
            for level in old_levels:
                assert set(p.rawmap(old_levels[level])) == set(p.rawmap(new_levels[level])), (logical, cid, level)
                old_leaves, new_leaves = p.rawmap(old_levels[level]), p.rawmap(new_levels[level])
                assert all(p.csvrows(v)[0][0] == p.csvrows(new_leaves[k])[0][0] for k, v in old_leaves.items())
        for cid in sorted(merge.NEW):
            levels = p.rawmap(new[cid]); counts = {k: len(p.rawmap(v)) for k, v in levels.items()}
            assert counts == {'1': 23, '2': 18}, (logical, cid, counts)
            ids = [p.csvrows(value)[0][0] for level in levels.values() for value in p.rawmap(level).values()]
            assert len(set(ids)) == 41
            node_report.append({'logical': logical, 'id': cid, 'node_ids': ids})
    chars = p.rawmap(effective('common', 'master/character/character.orderedmap'))
    abilities = p.rawmap(effective('common', 'master/ability/ability.orderedmap'))
    for cid in merge.FULL:
        char = p.csvrows(chars[cid])[0]
        assert all(k in abilities for k in char[19:25]), (cid, char[19:25])
    requirements = merge.readj(review / 'metadata/resources/character-counts.json')
    completeness = []
    for cid in sorted(merge.FULL):
        needed = {i['logical'] for g in requirements[cid]['requirements']['groups'] if g['required'] for i in g['items']}
        missing = [logical for logical in needed if not any(effective(root, logical) is not None for root in p.ROOTS)]
        assert not missing, (cid, missing)
        completeness.append({'id': cid, 'required': len(needed), 'present': len(needed)})
    exclude = p.csvrows(p.rawmap(effective('common', 'master/string/ui_string.orderedmap'))['character_voice_exclude'])[0][0].split('|')
    assert not any(x and x in 'character/ruin_girl_campus/voice/battle/skill_ready' for x in exclude)
    def odds_rows(name):
        outer = p.rawmap(effective('common', f'master/gacha_odds/{name}.orderedmap'))
        leaves = p.rawmap(outer[name])
        assert list(leaves) == list(map(str, range(len(leaves)))), name
        rows = [p.csvrows(v) for v in leaves.values()]
        assert all(len(row) == 1 for row in rows), name
        return [row[0] for row in rows]
    native = {}
    for gid in ('990001', '990002'):
        prefix = 'cnmod_abyss_limited_gacha' if gid == '990001' else 'cnmod_ashen_verdict_gacha'
        meta = p.csvrows(p.rawmap(effective('common', 'master/gacha/gacha.orderedmap'))[gid])[0]
        rarity_name = prefix + '_rarity'
        native[gid] = {'meta_row': meta,
            'rarity_rows': odds_rows(rarity_name),
            'character_rows': {str(6-rank): odds_rows(f'{prefix}_character_{rank}') for rank in (5, 4, 3)}}
    merge.writej(w / 'native-gachas.json', native)
    receipt = {'status': 'passed', 'installed': args.installed, 'prepared_sha256': merge.sha((w / 'prepared.json').read_bytes()),
               'assets_verified': len(index), 'png_strict_checked': png_count, 'dsl': dsl_checks,
               'ios_pairs': 12, 'unrelated_table_keys_preserved': True, 'existing_saved_node_ids_preserved': True,
               'new_boards': node_report, 'required_character_assets': completeness,
               'campus_nephtim_voice_not_excluded': True, 'device_tested': False, 'player_database_accessed': False}
    merge.writej(w / 'static-verification.json', receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k not in ('dsl', 'new_boards', 'required_character_assets')}, ensure_ascii=False))

if __name__ == '__main__': main()
