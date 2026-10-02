"""Sparse Inaho balance / Fluffy target-filter delta from the effective .117 chain.

Builds an offline candidate only. Activation is a separate explicit file sync.
Existing archive members and unrelated raw table rows remain unchanged.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/fantasy-gauntlet-mod-tools'))
import wf_mod_tool as core
import wf_quest_lib as ql
import wf_dsl
import wf_dsl_sig
import wf_dsl_subjects
import wf_atf
import wf_describe
from redesign_descriptions import descriptions as player_descriptions

BASE = '1.4.117'
VERSION = '1.4.118'
BASE_MANIFEST_SHA = '90b01a7850ebbdc4eb0cbe13c203180ba9e7085df744a028fed7f7956d25fb02'
ARCHIVE = 'pinball-1.4.117-1.4.118-1-inaho-redesign-fluffy-gauge.zip'
AUDIT = 'assets/asset-patch/audit/inaho-redesign-fluffy-gauge-1.4.118'
ABILITY = 'master/ability/ability.orderedmap'
LEADER = 'master/ability/leader_ability.orderedmap'
TEXT = 'master/character/character_text.orderedmap'
ACTION = 'master/skill/action_skill.orderedmap'
CAS = 'master/string/custom_ability_string.orderedmap'
REPLACE = 'master/string/skill_replace_string.orderedmap'
SKILL_PREFIX = 'battle/action/skill/action/rare5/cnmod_inaho_midautumn$cnmod_inaho_midautumn_'
CODE = 'cnmod_inaho_midautumn'
NONE = '(None)'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def jsonb(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def member(logical):
    h = hashlib.sha1((logical + 'K6R9T9Hz22OpeIGEWB0ui6c6PYFQnJGy').encode()).hexdigest()
    return 'production/upload/' + h[:2] + '/' + h[2:]


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def replace_cell(row, col, before, after):
    before, after = str(before), str(after)
    assert row[col] in (before, after), (col, row[col], before, after)
    row[col] = after


def pair(row, col, before, after):
    replace_cell(row, col, before, after)
    replace_cell(row, col + 1, before, after)


def append_once(rows, original_length, additions):
    if len(rows) == original_length:
        rows.extend(additions)
    else:
        assert len(rows) == original_length + len(additions)
        assert rows[original_length:] == additions, 'Unknown appended ability rows'


def set_cells(row, values):
    for col, value in values.items():
        row[col] = str(value)
    return row


def check_gauge_filter(rows):
    rules = [r for r in rows if r[5] == '1' and r[109] == '423']
    assert len(rules) == 1
    assert (rules[0][110], rules[0][111], rules[0][118]) == ('5', NONE, '12')


def check_combo_gauge(rows):
    """SkillGauge consumes a required target which the Pierce donor ignores.

    LeaderAbilityValues.parseAt45 calls parseAt46 for content 211. Blank is
    not Myself: the native parser throws ClientError 7050 for that value.
    """
    rules = [r for r in rows if r[3] == '0' and r[45] == '211'
             and r[49:51] == ['1500', '1500']]
    assert len(rules) == 1, 'Expected exactly one combo skill-gauge clause'
    assert rules[0][46] == '0', 'Combo skill-gauge target must explicitly be Myself (0)'
    assert rules[0][47] == NONE, 'Combo skill-gauge must not carry a party filter'


def patch_abilities(abilities, leaders):
    a = [abilities[str(1599910 + n)] for n in range(1, 7)]
    leader = leaders['159991']
    pair(leader[0], 49, 100000, 200000)
    pair(leader[7], 49, 10000, 15000)
    replace_cell(leader[7], 32, 15, 10)
    pair(leader[8], 49, 8000000, 10000000)
    pair(leader[9], 49, 100000, 150000)
    assert all(leader[n][33] == '1' for n in (8, 9, 10)), 'Keep native one-frame recursion guard'
    for n in (11, 12):
        pair(leader[n], 55, 6000000, 12000000)
    replace_cell(leader[14], 33, 300, 360)

    pair(a[0][1], 51, 5000000, 10000000)
    pair(a[0][2], 51, 100000, 150000)
    pair(a[0][4], 51, 20000, 40000)
    pair(a[0][6], 113, -25000, -40000)
    # This draft clause is not main-slot gated; all original A1 rows keep their flags.
    heal_fever = set_cells(copy.deepcopy(a[3][2]), {
        0: CODE + '_1', 1: 'true', 35: 0, 47: 213, 51: 5000000, 52: 5000000, 69: NONE,
    })
    append_once(a[0], 7, [heal_fever])

    pair(a[1][0], 51, 100000, 150000)
    pair(a[1][2], 51, 250000, 1500000)
    pair(a[1][3], 51, 5000, 20000)
    heal_ability = set_cells(copy.deepcopy(a[1][3]), {47: 388, 48: 0, 49: NONE, 51: 30000, 52: 30000})
    append_once(a[1], 5, [heal_ability])

    pair(a[2][1], 113, 250000, 500000)
    pair(a[2][2], 113, 10000, 15000)
    pair(a[2][3], 51, 300, 3000)
    replace_cell(a[2][3], 34, 100, 10)
    pair(a[2][5], 51, 100000, 200000)
    replace_cell(a[2][5], 34, 3, 2)
    group8 = set_cells(copy.deepcopy(a[2][6]), {34: 8, 47: 695, 51: 5000, 52: 5000})
    append_once(a[2], 7, [group8])

    pair(a[3][2], 51, 1000000, 3000000)
    replace_cell(a[3][2], 35, 120, 180)

    pair(a[4][0], 51, 100000, 150000)
    party_heal_fever = set_cells(copy.deepcopy(a[0][-1]), {
        0: CODE + '_5', 28: 7, 29: 'White', 51: 2000000, 52: 2000000,
    })
    append_once(a[4], 4, [party_heal_fever])

    pair(a[5][3], 51, 10000, 15000)
    pair(a[5][6], 51, 3000000, 10000000)
    pair(a[5][6], 57, 60000000, 180000000)
    fever_gain = set_cells(copy.deepcopy(a[5][3]), {47: 50, 51: 20000, 52: 20000})
    append_once(a[5], 8, [fever_gain])

    # Retain the existing Moon-state precondition; only the content is a gauge gain.
    combo_gauge = set_cells(copy.deepcopy(leader[11]), {
        45: 211, 46: 0, 47: NONE, 49: 1500, 50: 1500, 55: 0, 56: 0, 57: 0, 58: 0,
    })
    # Ordinary native DebuffPrevent, while self has visible Moon state and light resonance.
    immunity = copy.deepcopy(a[0][6])
    immunity[6:13] = a[0][5][6:13]
    set_cells(immunity, {104: 15999100, 109: 25, 110: 0, 111: NONE, 113: 0, 114: 0})
    immunity = [CODE, *immunity[3:]]  # leader rows omit unisonable / statue_group_id
    append_once(leader, 15, [combo_gauge, immunity])
    check_combo_gauge(leader)

    # Native AbilityLogic uses row 0 for the whole slot's unison availability.
    # Allow the new heal-Fever clause in unison; explicitly keep all seven old
    # clauses main-only through OwnerIsMain (202), not Leader (42).
    for row in a[0][:7]:
        row[1] = 'true'
        if not any(row[c] == '202' for c in (6, 13, 20)):
            free = next(c for c in (6, 13, 20) if row[c] == '0')
            row[free] = '202'

    fluffy = abilities['1499872']
    assert len(fluffy) == 4 and fluffy[3][109] == '423'
    replace_cell(fluffy[3], 111, '', NONE)
    check_gauge_filter(fluffy)


def walk(value):
    if isinstance(value, list):
        yield value
        for v in value:
            yield from walk(v)
    elif isinstance(value, dict):
        for v in value.values():
            yield from walk(v)


def patch_skill(raw):
    before = wf_dsl.parse_dsl(wf_atf.inflate(raw))['tree']
    tree = copy.deepcopy(before)
    # Editable positions: DeleteCondition p3 count; CreateCondition p2 list's
    # AttackPoint/AbilityDamage/DirectDamage effect p2 strength. IDs/flags stay fixed.
    changes = []
    moon_count = enhanced_count = ally_count = enemy_count = 0
    nodes = list(walk(tree))
    for index, n in enumerate(nodes):
        if not n:
            continue
        if n[0] == 'DeleteCondition' and isinstance(n[2], list) and n[2][0] == 'DCAll':
            if n[1] == 6:
                assert n[2] == ['DCAll', 3] and n[3] in (1, 2) and n[4] == 0
                changes.append((index, 3, copy.deepcopy(n[3])))
                n[3] = 2
                ally_count += 1
            else:
                assert n[1:5] == [5, ['DCAll', 2], 1, 0]
                enemy_count += 1
        if n[0] == 'CreateCondition' and n[7] == CODE + '_moon_payload':
            assert n[1] == 6 and len(n[2]) == 5
            effects = {effect[0]: effect for effect in n[2]}
            skill = effects['ACSkillDamage'][2]
            enhanced = skill == [{'min': 1.5, 'max': 1.5}]
            assert enhanced or skill == [{'min': 1, 'max': 1}]
            for kind, old, new in (
                ('ACAttackPoint', 1.5 if enhanced else 1, 4 if enhanced else 3),
                ('ACAbilityDamage', 1.5 if enhanced else 1, 4 if enhanced else 3),
                ('ACDirectDamage', 1 if enhanced else .5, 2 if enhanced else 1),
            ):
                effect = effects[kind]
                assert effect[1] == [{'min': 1200, 'max': 1200}]
                assert effect[2] in ([{'min': old, 'max': old}], [{'min': new, 'max': new}])
                # Restore changed leaf through the corresponding node in a copy.
                effect_index = next(j for j, node in enumerate(nodes) if node is effect)
                changes.append((effect_index, 2, copy.deepcopy(effect[2])))
                effect[2] = [{'min': new, 'max': new}]
            moon_count += 1
            enhanced_count += int(enhanced)
    assert (moon_count, enhanced_count, ally_count, enemy_count) == (4, 1, 1, 4)
    wf_dsl_sig.validate_action_dsl(tree)
    wf_dsl_subjects.validate_player_action_subjects(tree)
    encoded = wf_atf.deflate(wf_dsl.encode_amf3(tree))
    readback = wf_dsl.parse_dsl(wf_atf.inflate(encoded))['tree']
    assert readback == tree
    wf_dsl_sig.validate_action_dsl(readback)
    wf_dsl_subjects.validate_player_action_subjects(readback)
    inverse = copy.deepcopy(tree)
    inverse_nodes = list(walk(inverse))
    for i, pos, old in changes:
        inverse_nodes[i][pos] = old
    assert inverse == before, 'Undeclared DSL mutation'
    return encoded


def patch_text(text):
    before = '攻击力、技能伤害、能力伤害各+100%，直接攻击伤害+50%'
    after = '攻击力、能力伤害各+300%，技能伤害+100%，直接攻击伤害+100%'
    assert before in text or after in text
    assert '队伍全体1个弱化效果' in text or '队伍全体2个弱化效果' in text
    return text.replace(before, after).replace('队伍全体1个弱化效果', '队伍全体2个弱化效果')


def raw_map(raw, logical):
    om = core.read_orderedmap_raw_rows_from_bytes(raw, logical)
    return om, dict(zip(om.keys, om.rows))


def pack_changes(raw, logical, replacements, additions=None):
    om, original = raw_map(raw, logical)
    assert set(replacements) <= set(original)
    additions = additions or {}
    assert not set(additions) & set(original)
    for key, value in replacements.items():
        om.rows[om.keys.index(key)] = ql.build_node(value)
    for key, value in additions.items():
        om.keys.append(key)
        om.rows.append(ql.build_node(value))
    data = core.build_orderedmap_raw_rows(om)
    check, result = raw_map(data, logical)
    assert om.keys == check.keys
    assert {k for k in original if result[k] != original[k]} == set(replacements)
    assert set(result) - set(original) == set(additions)
    for key, value in (replacements | additions).items():
        assert ql.parse_node(result[key]) == value
    return data


def build(work, baseline_manifest=None):
    manifest_path = baseline_manifest or ROOT / 'assets/asset-patch/manifest.json'
    baseline_bytes = manifest_path.read_bytes()
    assert sha(baseline_bytes) == BASE_MANIFEST_SHA, 'Baseline manifest changed; rebase explicitly'
    manifest = json.loads(baseline_bytes)
    assert manifest['cdn_version'] == BASE
    logicals = [ABILITY, LEADER, TEXT, ACTION, CAS, REPLACE] + [SKILL_PREFIX + str(n) + '.action.dsl.amf3.deflate' for n in (1, 2)]
    # Power-flip scripts are unchanged but checked alongside reachable skill data.
    pf_logicals = [f'battle/action/power_flip/action/override/cnmod_inaho_midautumn$cnmod_inaho_midautumn_lv{n}.action.dsl.amf3.deflate' for n in (1, 2, 3)]
    wanted = {member(l): l for l in logicals + pf_logicals}
    effective, sources, chain = {}, {}, []
    for edge in manifest['patches']:
        if not edge.get('enabled', True):
            continue
        for name in edge.get('chain') or [edge['archive']]:
            path = ROOT / 'assets/asset-patch/active' / name
            chain.append({'archive': name, 'sha256': sha(path.read_bytes())})
            with zipfile.ZipFile(path) as z:
                for name_ in wanted.keys() & set(z.namelist()):
                    effective[wanted[name_]] = z.read(name_)
                    sources[wanted[name_]] = name
    if REPLACE not in effective:
        reference = ROOT / '.cdn/cn/archive-common-full/pinball-1.4.0-129-6ce35b95.zip'
        with zipfile.ZipFile(reference) as z:
            effective[REPLACE] = z.read(member(REPLACE))
        assert sha(effective[REPLACE]) == 'b7688f5597b0b73f08883566e6f71328f8d6806122c9774263bf7ba4f78af118'
        sources[REPLACE] = reference.name
    assert set(logicals + pf_logicals) == set(effective), set(logicals + pf_logicals) - set(effective)
    for logical, data in effective.items():
        write(work / 'before/resources' / member(logical), data)
    write(work / 'before/assets/asset-patch/manifest.json', baseline_bytes)

    def csv_rows(logical, keys):
        _, table = raw_map(effective[logical], logical)
        return {k: core.read_csv_lines(ql.parse_node(table[k])) for k in keys}

    abilities = csv_rows(ABILITY, [str(1599910 + n) for n in range(1, 7)] + ['1499872'])
    leaders = csv_rows(LEADER, ['159991'])
    original_abilities, original_leaders = copy.deepcopy(abilities), copy.deepcopy(leaders)
    try:
        check_gauge_filter(original_abilities['1499872'])
    except AssertionError:
        pass
    else:
        raise AssertionError('Former bad target filter must fail the new gate')
    patch_abilities(abilities, leaders)
    once = copy.deepcopy((abilities, leaders))
    patch_abilities(abilities, leaders)
    assert (abilities, leaders) == once, 'Non-idempotent table transformation'
    # The Fluffy fix is exactly one Option target-filter cell.
    repaired = copy.deepcopy(abilities['1499872'])
    repaired[3][111] = ''
    assert repaired == original_abilities['1499872']
    payloads = {
        ABILITY: pack_changes(effective[ABILITY], ABILITY, {k: core.write_csv_lines(v) for k, v in abilities.items()}),
        LEADER: pack_changes(effective[LEADER], LEADER, {k: core.write_csv_lines(v) for k, v in leaders.items()}),
    }
    descriptions = {}
    for logical, rows_by_key in ((ABILITY, abilities), (LEADER, leaders)):
        kind = Path(logical).stem
        for key, rows in rows_by_key.items():
            assert all(len(row) == (126 if kind == 'ability' else 124) for row in rows)
            descriptions[key] = [wf_describe.describe_line(row, kind) for row in rows]

    texts = csv_rows(TEXT, ['159991'])
    for col in (5, 7):
        texts['159991'][0][col] = patch_text(texts['159991'][0][col])
    payloads[TEXT] = pack_changes(effective[TEXT], TEXT, {'159991': core.write_csv_lines(texts['159991'])})
    _, action_raw = raw_map(effective[ACTION], ACTION)
    action = ql.parse_node(action_raw[CODE])
    assert set(action) == {'1', '2'}
    for form in action:
        rows = core.read_csv_lines(action[form])
        rows[0][1] = patch_text(rows[0][1])
        action[form] = core.write_csv_lines(rows)
    payloads[ACTION] = pack_changes(effective[ACTION], ACTION, {CODE: action})
    enhanced_text = '光属性共鸣时，强化「月满丰穰」的攻击力、能力伤害、直接攻击伤害提升效果[提升量各+100%]，技能伤害提升效果[提升量+50%]'
    display = player_descriptions(abilities, leaders)
    payloads[CAS] = pack_changes(effective[CAS], CAS,
        {CODE + '_enhance_buffs': core.write_csv_lines([[enhanced_text]])},
        {key: core.write_csv_lines([[text]]) for key, text in display.items()})
    replacements = core.read_csv_lines(zlib.decompress(effective[REPLACE]).decode('utf-8'))
    assert not any(row[0] == '作为主要角色编成：' for row in replacements)
    replacements.append(['作为主要角色编成：', " <icon id='main'>  "])
    payloads[REPLACE] = zlib.compress(core.write_csv_lines(replacements).encode('utf-8'))
    assert core.read_csv_lines(zlib.decompress(payloads[REPLACE]).decode('utf-8')) == replacements
    modes = {}
    for key, normal in display.items():
        graphical = normal
        for find, replace in replacements:
            graphical = graphical.replace(find, replace)
        assert '<icon' not in normal
        assert graphical.count("<icon id='main'>") == normal.count('作为主要角色编成：')
        assert '作为主要角色编成：' not in graphical and '光属性' not in graphical
        assert len(normal.splitlines()) == len(graphical.splitlines())
        modes[key] = {'normal': normal, 'graphical': graphical}
    # Row-level main/unison flags alone cannot restrict mixed slots.
    assert abilities['1599911'][0][1] == 'true'
    assert all(sum(row[c] == '202' for c in (6, 13, 20)) == 1 for row in abilities['1599911'][:7])
    assert all(abilities['1599911'][7][c] == '0' for c in (6, 13, 20))
    for logical in logicals:
        if logical.endswith('.deflate'):
            payloads[logical] = patch_skill(effective[logical])
            assert patch_skill(payloads[logical]) == payloads[logical], 'Non-idempotent DSL transformation'
    pf_checked = []
    for logical in pf_logicals:
        if logical in effective:
            tree = wf_dsl.parse_dsl(wf_atf.inflate(effective[logical]))['tree']
            wf_dsl_sig.validate_action_dsl(tree)
            wf_dsl_subjects.validate_player_action_subjects(tree)
            pf_checked.append(logical)

    # Keep the same merged server text key and do not touch unrelated characters.
    server_text = 'assets/cdndata/character_text.json'
    before_server = (ROOT / server_text).read_bytes()
    server_value = json.loads(before_server)
    overrides = load_json(ROOT / 'assets/cdndata/character_text_rank_p5b.json')
    assert '159991' not in overrides, 'A later server text override must be updated too'
    assert server_value['159991'] == csv_rows(TEXT, ['159991'])['159991']
    server_value['159991'] = texts['159991']
    candidate = work / 'candidate'
    write(work / 'before' / server_text, before_server)
    write(candidate / server_text, jsonb(server_value))

    archive_path = candidate / 'assets/asset-patch/active' / ARCHIVE
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for logical, raw in sorted(payloads.items()):
            info = zipfile.ZipInfo(member(logical), (2026, 9, 24, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, raw)
    with zipfile.ZipFile(archive_path) as z:
        assert z.testzip() is None
        assert set(z.namelist()) == {member(l) for l in payloads}
        for logical, raw in payloads.items():
            assert z.read(member(logical)) == raw
    archive_hash = sha(archive_path.read_bytes())
    files = sorted(member(l) for l in payloads)
    manifest['cdn_version'] = VERSION
    manifest['patches'].append({
        'id': 'inaho-redesign-fluffy-gauge-20260924', 'type': 'patch',
        'name': '中秋稻穗调整与芙拉菲回槽限制修复',
        'description': '调整中秋稻穗数值和回复联动，修复芙拉菲全队回槽限制的目标筛选。',
        'version': VERSION, 'depends_on': BASE, 'enabled': True, 'local_test_only': True,
        'archive': ARCHIVE, 'archive_size': archive_path.stat().st_size,
        'archive_integrity': [{'name': ARCHIVE, 'size': archive_path.stat().st_size, 'sha256': archive_hash, 'members': len(files), 'files': files}],
        'files': files, 'audit': {'directory': AUDIT},
        'changes': [
            '稻穗技能移除2个弱化效果，更新月满丰穰增益及能力数值。',
            '补充连击回槽、回复增加Fever、能力独立乘区8与普通弱化免疫。',
            '保留现有强化弹射、技能伤害加成、75倍强化技能、状态生命周期及媒体资源。',
            '稻穗队长技及六条能力按条件分段，主位及属性图标随说明模式切换。',
            '芙拉菲全队限制改用无筛选目标，保留开场及移动充能。',
        ],
    })
    write(candidate / 'assets/asset-patch/manifest.json', jsonb(manifest))
    report = {
        'status': 'offline_candidate', 'baseline': BASE, 'target': VERSION,
        'archive': ARCHIVE, 'archive_sha256': archive_hash, 'archive_bytes': archive_path.stat().st_size,
        'members': len(files), 'source_chain': chain, 'resources': [
            {'logical': l, 'member': member(l), 'source': sources[l], 'before_sha256': sha(effective[l]), 'after_sha256': sha(raw)}
            for l, raw in payloads.items()
        ],
        'changed_table_keys': {ABILITY: list(abilities), LEADER: ['159991'], TEXT: ['159991'], ACTION: [CODE], CAS: [CODE + '_enhance_buffs', *display], REPLACE: ['append main-slot phrase replacement']},
        'before_files': {'assets/asset-patch/manifest.json': sha(baseline_bytes), server_text: sha(before_server)},
        'server_files': {server_text: sha(jsonb(server_value)), 'assets/asset-patch/manifest.json': sha(jsonb(manifest))},
        'pf_validated': pf_checked,
        'checks': ['Unrelated raw table rows preserved', 'Table and DSL transforms idempotent', 'Former Fluffy blank-filter regression rejected', 'Both skill forms serialized and read back', 'DSL edits limited to declared count/strength parameters', 'ZIP CRC and exact member readback', 'Normal/graphical description projection; no fixed icons', 'Mixed A1 main/unison gates explicitly retained'],
        'native_semantics': {'debuff_immunity': 'During content 25 / DebuffPrevent; ordinary debuffs only', 'group_8': 'Instant content 695 / ability damage only', 'flat_fever': 'Instant content 213; decimal units, 50 or 20 points', 'fever_gain': 'Instant content 50; light party +20% under light resonance', 'heal_event': 'Accepted heal event including at full HP'},
        'save_impact': 'Balance and text only; no saved IDs or persistence schema changes.',
        'device_tested': False, 'apk_rebuilt': False, 'cloud_deployed': False,
        'presentation': 'Seven character-specific segmented descriptions; native SkillReplaceString controls ordinary/graphical modes. No fixed icons.',
        'ability1_unison': 'Heal +50 Fever is available in unison. Original seven clauses retain OwnerIsMain 202; first-row unison gate is enabled.',
    }
    write(work / 'build-report.json', jsonb(report))
    write(work / 'ability-descriptions.json', jsonb(descriptions))
    write(work / 'patched-rows.json', jsonb({'ability': abilities, 'leader_ability': leaders}))
    write(work / 'player-descriptions.json', jsonb(display))
    write(work / 'description-modes.json', jsonb(modes))
    print(json.dumps({k: report[k] for k in ('status', 'target', 'archive_sha256', 'archive_bytes', 'members', 'pf_validated')}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--baseline-manifest', type=Path)
    args = parser.parse_args()
    build(args.work, args.baseline_manifest)
