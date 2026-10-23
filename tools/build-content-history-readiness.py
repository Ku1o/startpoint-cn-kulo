#!/usr/bin/env python3
"""Evidence-only history inventory. Never publish content, mutate a database, or export CDN files."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import zlib
import zipfile
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
EVENT_TYPES = ['advent_event', 'ranking_event', 'story_event', 'daily_week_event', 'challenge_dungeon_event',
               'daily_exp_mana_event', 'world_story_event', 'tower_dungeon_event', 'expert_single_event',
               'carnival_event', 'raid_event', 'rush_event', 'solo_time_attack_event', 'hard_multi_event', 'score_attack_event']
RELATED_TYPES = ['active_mission_event', 'collect_item_event', 'pass_card_event', 'box_gacha',
                 'multi_special_exchange_campaign', 'special_exchange_campaign', 'start_dash_exchange_campaign']
PARENT_TYPES = EVENT_TYPES + RELATED_TYPES + ['gacha']
RAID_MASTER = 'master/quest/event/raid_event.orderedmap'
RAID_QUEST = 'master/quest/event/raid_event_quest.orderedmap'
RAID_OVERALL = 'master/quest/event/raid_event_overall_reward.orderedmap'
RAID_RANKING = 'master/quest/event/raid_event_ranking_reward.orderedmap'
RANKING_REWARD = 'master/quest/event/ranking_event_ranking_reward.orderedmap'
EVENT_SHOP_MASTER = 'master/shop/event_item_shop.orderedmap'
EVENT_SHOP_COLUMNS = {'event': [0, 1], 'event_type_value': [2], 'price': [15, 16],
                      'cost_item_schedule_id': [17], 'buy_max_count': [29], 'max_frequency': [30],
                      'daily_stock': [31], 'monthly_stock': None, 'kind1_equipment_only_possession_one': [50],
                      **{'cost_item' + str(i + 1): [18 + 2 * i, 19 + 2 * i] for i in range(4)},
                      **{'kind' + str(i + 1): [32 + 3 * i, 33 + 3 * i, 34 + 3 * i] for i in range(6)}}
EVENT_SHOP_PARENT_TYPES = ['advent_event', 'story_event', 'world_story_event', 'challenge_dungeon_event',
                          'collect_item_event', 'carnival_event', 'rush_event', 'score_attack_event']
SHOP_NATIVE_SOURCE_SHA = {
    'EventItemShopValues.as': 'df61223f68a66cd8cfac5a589569d012f5af50fcb1ee854518ce84515668c43c',
    'ShopProductLogic.as': 'ac73cf3efedf311c3c48c011b83df9ae31d9d25f9670bb44d82c1a88ccb65369',
    'EventItemShopProductLogic.as': '4b19bd4655b326faab208d927e82835db6a9659490ae14f18d365c042481205f',
}
BATTLE_MASTERS = ['master/battle/floor.orderedmap', 'master/battle/field_data.orderedmap', 'master/battle/zone.orderedmap']
QUEST_PERIOD_COLUMNS = {'rush_event': (7, 8), 'raid_event': (7, 8), 'score_attack_event': (7, 8),
                        'expert_single_event': (7, 8), 'carnival_event': (7, 8),
                        'solo_time_attack_event': (6, 7), 'daily_week_event': (4, 5)}
MISSION_SPECS = {
    0: ('active', 'active_mission_event'), 4: ('collect', 'collect_item_event'),
    6: ('pass_daily', 'pass_card_event'), 7: ('pass_week', 'pass_card_event'), 8: ('pass_event', 'pass_card_event'),
    1: ('regular', 'mission_regular'), 2: ('daily', 'mission_daily'), 3: ('event', 'mission_event'),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf8', newline='\n', prefix=path.name + '.tmp-', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def importer(path):
    spec = importlib.util.spec_from_file_location('history_native_exporter', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def receipt(exporter, logical, identity):
    return dict(identity, member=exporter.member(logical))


def project_event_shop_native(raw):
    """Original Values types; Option.None is null, while Some(0) remains zero."""
    if len(raw) != 51:
        raise ValueError('EventItemShopValues requires exactly 51 columns')
    def integer(index, optional=False):
        value = raw[index]
        if optional and value == '(None)':
            return None
        if not isinstance(value, str) or not re.fullmatch(r'-?\d+', value):
            raise ValueError('invalid native shop integer column ' + str(index))
        return int(value)
    def kind_at(index):
        if raw[index] == '(None)':
            return None
        return {'kind': integer(index), 'id': None if raw[index + 1] in ('', '(None)') else integer(index + 1),
                'number': integer(index + 2)}
    flag = raw[50]
    if flag not in ('FALSE', 'False', 'false', 'TRUE', 'True', 'true'):
        raise ValueError('invalid native shop boolean column 50')
    price = None if raw[15] == '(None)' else {'kind': integer(15), 'count': integer(16)}
    return {'buy_max_count': integer(29), 'max_frequency': integer(30, True),
            'daily_stock': integer(31, True), 'monthly_stock': None,
            'kind1_equipment_only_possession_one': flag in ('TRUE', 'True', 'true'),
            'price': price, 'cost_item_schedule_id': None if raw[17] == '(None)' else raw[17],
            'cost_items': [{'slot': i + 1, 'id': integer(18 + 2 * i), 'count': integer(19 + 2 * i)}
                           for i in range(4) if raw[18 + 2 * i] != '(None)'],
            **{'kind' + str(i + 1): kind_at(32 + 3 * i) for i in range(6)}}


def native_shop_rules_document(exporter, native_rows, catalog, catalog_sha, source, identity, schema_files):
    """Complete catalog event-shop scope only; no conversion into legacy runtime stock."""
    parents = {row['key'] for row in catalog['rows'] if row['type'] in PARENT_TYPES}
    wanted = {row['key']: row for row in catalog['rows'] if row['type'] == 'event_item_shop' and row.get('parentKey') in parents}
    products, true_keys, limits = {}, [], {name: Counter() for name in ['buy_max_count', 'max_frequency', 'daily_stock', 'monthly_stock']}
    columns_sha = exporter.json_sha(EVENT_SHOP_COLUMNS)
    for key, row in sorted(wanted.items()):
        value = native_rows.get(str(row['id']))
        if not value or len(value) != 1:
            raise ValueError('missing or ambiguous native event-shop row: ' + key)
        raw = value[0]
        native = project_event_shop_native(raw)
        if not raw[0].isdigit() or int(raw[0]) >= len(EVENT_SHOP_PARENT_TYPES):
            raise ValueError('unknown native event-shop parent kind: ' + key)
        parent = EVENT_SHOP_PARENT_TYPES[int(raw[0])] + ':' + raw[1]
        if parent != row['parentKey'] or exporter.json_sha(raw) != row['definitionDigest']:
            raise ValueError('native event-shop parent or catalog row identity changed: ' + key)
        products[key] = {'parentKey': parent, 'native': native,
                         'source': {'logical': EVENT_SHOP_MASTER, 'rowId': str(row['id']),
                                    'rowSha256': exporter.json_sha(raw), 'raw': raw,
                                    'columnsRef': 'source.fieldSchema.columns', 'columnsSha256': columns_sha}}
        if native['kind1_equipment_only_possession_one']:
            true_keys.append(key)
        for name, counter in limits.items():
            value = native[name]
            counter['null' if value is None else 'zero' if value == 0 else 'negative' if value < 0 else 'positive'] += 1
    excluded = sorted('event_item_shop:' + ident for ident in native_rows if 'event_item_shop:' + ident not in wanted)
    return {'schemaVersion': 1,
            'source': {'catalogSha256': catalog_sha, 'assetVersion': source['assetVersion'],
                       'manifestSha256': source['manifestSha256'],
                       'resources': {EVENT_SHOP_MASTER: receipt(exporter, EVENT_SHOP_MASTER, identity)},
                       'fieldSchema': {'class': 'EventItemShopValues', 'columns': EVENT_SHOP_COLUMNS,
                                       'columnsSha256': columns_sha, 'nativeSources': schema_files,
                                       'types': {'buy_max_count': 'Int', 'max_frequency': 'Option<Int>',
                                                 'daily_stock': 'Option<Int>', 'monthly_stock': 'not_defined',
                                                 'kind1_equipment_only_possession_one': 'Bool'},
                                       'semantics': {'buy_max_count': 'per-request maximum',
                                                     'max_frequency': 'maximum minus totalPurchaseNum',
                                                     'daily_stock': 'maximum minus todayPurchaseNum',
                                                     'monthly_stock': 'absent from EventItemShopValues; null',
                                                     'kind1_equipment_only_possession_one': 'flag AND first reward is Equipment AND player.hasEquipment(id) makes getMaxBuyCount zero'}}},
            'products': products,
            'summary': {'catalogParentCount': len(parents), 'catalogProductCount': len(products),
                        'nativeRowCount': len(native_rows), 'excludedCurrentOnlyKeys': excluded,
                        'equipmentOnlyPossessionOneKeys': true_keys,
                        'limitValueCounts': {name: {kind: counter[kind] for kind in ['null', 'zero', 'negative', 'positive']}
                                             for name, counter in limits.items()}},
            'scope': {'authoritativeFor': ['buy_max_count', 'max_frequency', 'daily_stock', 'kind1_equipment_only_possession_one'],
                      'otherNativeFields': 'Evidence only; costs, rewards, dates, parent mapping and retained reviewed scope are unchanged.',
                      'defaultEnabled': False, 'gameplayStatus': 'unreviewed'}}


def build_shop_rules_only(args, repo, resource_root, exporter, manifest_before):
    if not args.shop_rules or not args.shop_native_source:
        raise ValueError('--shop-rules-only requires --shop-rules and --shop-native-source')
    catalog_bytes = (repo / 'assets/content_catalog.json').read_bytes()
    native_source = Path(args.shop_native_source).resolve()
    schema_files = {}
    for name, expected in SHOP_NATIVE_SOURCE_SHA.items():
        actual = sha((native_source / name).read_bytes())
        if actual != expected:
            raise ValueError('native shop schema source identity changed: ' + name)
        schema_files[name] = {'sha256': actual,
                              'evidence': 'native-shop-source/' + name}
    inputs, source = exporter.resolve(resource_root, [EVENT_SHOP_MASTER])
    native_rows = exporter.parse_rows(inputs[EVENT_SHOP_MASTER][0], EVENT_SHOP_MASTER)
    document = native_shop_rules_document(exporter, native_rows, json.loads(catalog_bytes), sha(catalog_bytes), source,
                                         inputs[EVENT_SHOP_MASTER][1], schema_files)
    if len(document['products']) != 8579 or len(document['summary']['excludedCurrentOnlyKeys']) != 9:
        raise ValueError('catalog event-shop closed set changed; review the 8579 plus 9 boundary')
    if (repo / 'assets/content_catalog.json').read_bytes() != catalog_bytes or (repo / 'assets/asset-patch/manifest.json').read_bytes() != manifest_before:
        raise ValueError('catalog or target chain changed during shop projection')
    if (resource_root / 'assets/asset-patch/manifest.json').read_bytes() != manifest_before:
        raise ValueError('read-only source winning chain changed during shop projection')
    write(args.shop_rules, document)
    if args.evidence:
        write(args.evidence, {'schemaVersion': 1, 'summary': document['summary'], 'source': document['source'],
                              'outputSha256': sha(Path(args.shop_rules).read_bytes())})
    print(json.dumps(document['summary'], ensure_ascii=False))


def build_raid_assets(exporter, inputs, source):
    """Confirmed native accessor columns only; no runtime scaling or reward-kind conversion."""
    events = exporter.parse_rows(inputs[RAID_MASTER][0], RAID_MASTER)
    quests = exporter.nested_rows(inputs[RAID_QUEST][0], RAID_QUEST, 2)
    records = {}
    for ident, values in events.items():
        if len(values) != 1 or not values[0][17].isdigit():
            raise ValueError('invalid native Raid required kill count: ' + ident)
        weights = {}
        for member, rows in quests.get(ident, {}).items():
            if len(rows) != 1 or not rows[0][52].isdigit() or not rows[0][0].isdigit():
                raise ValueError('invalid native Raid quest weight: ' + ident + '/' + member)
            key, value = rows[0][0], int(rows[0][52])
            if key in weights and weights[key] != value:
                raise ValueError('ambiguous native Raid quest weight: ' + key)
            weights[key] = value
        if not weights:
            raise ValueError('native Raid has no quest weights: ' + ident)
        records[ident] = {'nativeRequiredKillCount': int(values[0][17]), 'questKillCountWeights': weights}
    provenance = {'assetVersion': source['assetVersion'], 'manifestSha256': source['manifestSha256'],
                  'resources': {logical: receipt(exporter, logical, inputs[logical][1])
                                for logical in [RAID_MASTER, RAID_QUEST]}}
    rules = {'schemaVersion': 1, 'source': provenance, 'events': records,
             'scope': 'Native targets and weights only. Existing event 7 runtime scaling and saved state are not overwritten.'}
    reward_source = {'assetVersion': source['assetVersion'], 'manifestSha256': source['manifestSha256'],
                     'resources': {RAID_OVERALL: receipt(exporter, RAID_OVERALL, inputs[RAID_OVERALL][1])}}
    rewards = {'schemaVersion': 1, 'source': reward_source,
               'rows': exporter.parse_rows(inputs[RAID_OVERALL][0], RAID_OVERALL)}
    return rules, rewards


def native_rewards(fields, offset):
    result = []
    for index in range(offset, len(fields) - 2, 3):
        kind, ident, number = fields[index:index + 3]
        if kind in ('', '(None)'):
            continue
        result.append({'kind': int(kind), 'id': int(ident) if ident.isdigit() else None, 'number': int(number)})
    return result


def build_ranking_assets(exporter, inputs, source):
    result = {}
    for logical, depth in [(RANKING_REWARD, 2), (RAID_RANKING, 3)]:
        events = {}
        for event, members in exporter.nested_rows(inputs[logical][0], logical, depth).items():
            values = list(members.values()) if depth == 2 else [rows for group in members.values() for rows in group.values()]
            projected = []
            for rows in values:
                if len(rows) != 1:
                    raise ValueError('ambiguous native ranking reward: ' + logical + '/' + event)
                row = rows[0]
                if logical == RANKING_REWARD:
                    projected.append({'id': int(row[0]), 'maxPercentile': float(row[1]), 'reasonId': int(row[2]),
                                      'rewards': native_rewards(row, 3)})
                else:
                    projected.append({'questId': int(row[0]), 'minCount': int(row[1]), 'maxCount': int(row[2]),
                                      'reasonId': int(row[3]), 'rewards': native_rewards(row, 4)})
            events[event] = projected
        result[logical] = {'schemaVersion': 1,
                           'source': {'assetVersion': source['assetVersion'], 'manifestSha256': source['manifestSha256'],
                                      'resources': {logical: receipt(exporter, logical, inputs[logical][1])}}, 'events': events}
    return result


def quest_specs(exporter):
    result = {}
    for typ, _, _, _, _, _, categories in exporter.TABLES:
        if not categories:
            continue
        for name, cats in exporter.CLIENT_QUEST_TABLES.get(typ, [(typ + '_quest', categories)]):
            result['master/quest/event/' + name + '.orderedmap'] = (typ, cats)
    return result


def collect_quests(exporter, inputs, parents, catalog_map, schema=None):
    nodes, by_parent, excluded = {}, defaultdict(list), []
    fields = exporter.parse_rows(inputs[BATTLE_MASTERS[1]][0], 'field_data') if BATTLE_MASTERS[1] in inputs else {}
    floors = exporter.parse_rows(inputs[BATTLE_MASTERS[0]][0], 'floor') if BATTLE_MASTERS[0] in inputs else {}
    zones = exporter.nested_rows(inputs[BATTLE_MASTERS[2]][0], 'zone', 2) if BATTLE_MASTERS[2] in inputs else {}
    definitions = {record['logical']: record for record in (schema or {}).get('tables', {}).values()}
    odds_tables = {}
    for logical, (typ, categories) in quest_specs(exporter).items():
        if logical not in inputs:
            continue
        start_col, end_col = QUEST_PERIOD_COLUMNS.get(typ, (5, 6))
        for event, members in exporter.nested_rows(inputs[logical][0], logical, 2).items():
            parent = typ + ':' + event
            if parent not in parents:
                excluded.append(parent)
                continue
            for member, values in members.items():
                if len(values) != 1:
                    raise ValueError('ambiguous native quest row: ' + logical + '/' + event + '/' + member)
                value = values[0]
                metadata = definitions.get(logical)
                kind = (metadata.get('rawKindMapping', {}).get(value[metadata['kindColumn']], 'Unknown')
                        if metadata and metadata.get('kindColumn') is not None else 'Battle')
                exact_fields, field_errors, native_projection, drawn_options = None, [], {}, []
                if metadata:
                    resolver = metadata['fieldResolution']
                    exact_fields = []
                    if kind == 'Story':
                        pass
                    elif resolver['kind'] == 'direct_field':
                        exact_fields = [value[resolver['column']]]
                    elif resolver['kind'] == 'floor_group':
                        group = value[resolver['column']]
                        if group not in floors:
                            field_errors.append('floor group absent: ' + group)
                        else:
                            exact_fields = [line[0] for line in floors[group]]
                    elif resolver['kind'] == 'drawn_odds':
                        odds_spec = (schema or {})['tables'][resolver['valuesClass']]
                        if odds_spec['logical'] not in odds_tables:
                            odds_tables[odds_spec['logical']] = exporter.nested_rows(inputs[odds_spec['logical']][0], odds_spec['logical'], 2)
                        odds = odds_tables[odds_spec['logical']]
                        group = value[resolver['oddsGroupColumn']]
                        if group not in odds:
                            field_errors.append('drawn odds group absent: ' + group)
                        else:
                            exact_fields = [row[0][odds_spec['fieldResolution']['column']] for row in odds[group].values()]
                            for local, records in odds[group].items():
                                raw_odds = records[0]
                                odds_element = raw_odds[odds_spec['serverJsonExpectedColumns']['element']]
                                drawn_options.append({'groupId': int(group), 'localId': int(local), 'compositeQuestId': int(group) * 1000 + int(local),
                                                      'fieldKey': raw_odds[odds_spec['fieldResolution']['column']],
                                                      'element': int(odds_element) if odds_element.isdigit() else None,
                                                      'source': odds_spec['logical'], 'rowSha256': exporter.json_sha(raw_odds)})
                    else:
                        field_errors.append('unsupported field resolver: ' + resolver['kind'])
                    for name, column in metadata.get('serverJsonExpectedColumns', {}).items():
                        if kind == 'Story' and name != 'clearRewardId':
                            continue
                        cell = value[column]
                        native_projection[name] = int(cell) if cell.lstrip('-').isdigit() else None if cell in ['', '(None)'] else cell
                        if name in ['bRankTime', 'aRankTime', 'sRankTime', 'sPlusRankTime']:
                            native_projection[name] = int(float(cell) * 1000) if native_projection[name] is not None else 0
                # Exact reference membership is useful provenance, not a substitute for native loader semantics.
                references = [{'column': index, 'kind': 'field' if cell in fields else 'floor', 'value': cell}
                              for index, cell in enumerate(value) if not cell.isdigit() and (cell in fields or cell in floors)]
                selected_fields = {ref['value'] for ref in references if ref['kind'] == 'field'}
                for ref in references:
                    if ref['kind'] == 'floor':
                        selected_fields.update(cell for line in floors[ref['value']] for cell in line if cell in fields)
                if exact_fields is not None:
                    selected_fields = set(exact_fields)
                    field_errors.extend('field absent: ' + field for field in selected_fields if field not in fields)
                scenes = []
                for field in sorted(selected_fields):
                    if field not in fields:
                        continue
                    records = fields[field]
                    terrains = sorted({cell + ('' if cell.endswith('.amf3.deflate') else '.amf3.deflate')
                                       for line in records for cell in line if cell.startswith('battle/terrain/')})
                    zone_ids = sorted({cell for line in records for cell in line if cell in zones})
                    scenes.append({'field': field, 'fieldRowSha256': exporter.json_sha(records), 'terrainLogicals': terrains,
                                   'zoneKeys': zone_ids, 'zoneSha256': {zone: exporter.json_sha(zones[zone]) for zone in zone_ids},
                                   'enemyAndObjectSemantics': 'unreviewed'})
                for category in categories:
                    key = str(category) + ':' + value[0]
                    entry = nodes.setdefault(key, {'key': key, 'category': category, 'questId': int(value[0]),
                                                   'parents': [], 'nativeRows': [], 'catalogOwner': catalog_map.get(key)})
                    if parent not in entry['parents']:
                        entry['parents'].append(parent)
                    entry['nativeRows'].append({'parentKey': parent, 'source': logical, 'event': event, 'member': member,
                                                'rowSha256': exporter.json_sha(value),
                                                'originalStartMs': exporter.timestamp(value[start_col]),
                                                'originalEndMs': exporter.timestamp(value[end_col])})
                    entry['battleReferences'] = {'status': 'candidate_native_reference_membership' if references else 'unresolved_native_loader_mapping',
                                                 'rawReferences': references, 'scenes': scenes,
                                                 'scope': 'Exact native CSV cells intersecting real floor/field keys; not a claim that every native loader has been traced.'}
                    if metadata:
                        entry['nativeKind'] = kind
                        fixed_column = metadata.get('allResolvedScalarColumns', {}).get('battle_fixed_party')
                        if kind != 'Story' and fixed_column is not None and value[fixed_column] not in ['', '(None)']:
                            native_projection['fixedParty'] = int(value[fixed_column])
                        entry['nativeProjection'] = native_projection
                        if drawn_options:
                            entry['drawnQuestOptions'] = drawn_options
                        entry['nativeSchema'] = {'logical': logical, 'classSource': metadata['source'], 'classSha256': metadata['sourceSha256']}
                        entry['nativeEligibility'] = {name: value[column] for name, column in metadata.get('allResolvedScalarColumns', {}).items()
                                                      if name.startswith(('viewable_', 'selectable_', 'battle_startable_', 'start_', 'end_', 'annual_', 'battle_stamina_cost', 'available_play_kind', 'daily_challenge_point_id'))}
                        entry['battleReferences'].update(status='blocked' if field_errors else 'passed_native_field_mapping',
                                                        issues=field_errors, resolver=metadata['fieldResolution'],
                                                        expectedFieldKeys=sorted(selected_fields),
                                                        scope='Exact original Values discriminator and direct/floor/drawn-odds resolver; Story deliberately has no battle field.')
                    if key not in by_parent[parent]:
                        by_parent[parent].append(key)
    return nodes, by_parent, sorted(set(excluded))


def blocker(code, message, **evidence):
    return {'code': code, 'message': message, 'evidence': evidence}


def source_rule_status(observation):
    if not observation:
        return 'unreviewed'
    if observation.get('staticRuleStatus'):
        status = observation['staticRuleStatus']
        return 'passed' if status in ['passed', 'existing_source_reviewed'] else status
    description = observation.get('implementation', observation.get('status', ''))
    if 'not implemented' in description or description.startswith(('missing ', 'root implementing ')):
        return 'unreviewed'
    return 'passed' if description.startswith(('implemented:', 'existing ', 'dedicated ', 'root implemented ',
                                               'root start hook ', 'new accepted-', 'new same-parent ')) else 'unreviewed'


def mission_reward_checks(definition, native_tables, server_ids, parent):
    issues, references = [], []
    if not definition:
        return {'status': 'blocked', 'issues': ['实际服务端阶段解析器无法读取定义'], 'referenceChecks': []}
    for reward in definition.get('rewards', []):
        kind, amount = reward['kind'], reward['amount']
        if kind not in range(8) or not isinstance(amount, int) or amount < 0:
            issues.append('奖励种类或数量未被实际发奖器支持')
        if kind == 7 and not parent.startswith('pass_card_event:'):
            issues.append('通行证积分缺少通行证父范围')
        if kind in [1, 2, 4, 6]:
            native_kind, field = {1: (0, 'itemId'), 2: (4, 'equipmentId'), 4: (3, 'characterId'), 6: (5, 'degreeId')}[kind]
            ident = str(reward.get(field))
            present = ident in native_tables.get(native_kind, {}) and ident in server_ids[native_kind]
            references.append({'kind': native_kind, 'id': reward.get(field), 'nativeAndServerPresent': present})
            if not present:
                issues.append('原生或服务端奖励定义缺失：' + str(native_kind) + ':' + ident)
    return {'status': 'blocked' if issues else 'passed', 'issues': issues, 'referenceChecks': references}


def native_entries(exporter, inputs, schema, parents, flat):
    if not schema:
        return {}
    kinds = {key: value['type'] for key, value in schema['eventKindMapping'].items()}
    folders_logical = 'master/quest/event/event_folder.orderedmap'
    folders = exporter.parse_rows(inputs[folders_logical][0], folders_logical) if folders_logical in inputs else {}
    ui_logical = 'master/string/ui_string.orderedmap'
    ui = exporter.parse_rows(inputs[ui_logical][0], ui_logical) if ui_logical in inputs else {}
    excluded = ui.get('box_gacha_link_ids')
    string_ids = schema.get('parentStringId', {}).get('mapping', {})
    result = {key: {'routes': [], 'nativeTransition': schema['nativeRoutes'].get(row['type']),
                     'selectionPreserves': schema['selectionPreserves']} for key, row in parents.items() if row['type'] in EVENT_TYPES}
    for spec in schema['membershipTables']:
        logical = spec['logical']
        if logical not in inputs:
            raise ValueError('native membership table absent: ' + logical)
        columns = spec['columns']
        folder_mode = 'event_folder_events.' in logical
        parsed = exporter.nested_rows(inputs[logical][0], logical, 2) if folder_mode else exporter.parse_rows(inputs[logical][0], logical)
        for outer, members in parsed.items():
            members = members if folder_mode else {outer: members}
            for member, values in members.items():
                if len(values) != 1:
                    raise ValueError('ambiguous native membership row: ' + logical + '/' + outer + '/' + member)
                value = values[0]
                typ = kinds.get(value[columns['event_kind']])
                key = str(typ) + ':' + value[columns['event_id']]
                if key not in result:
                    continue
                route = {'source': logical, 'outerKey': outer, 'memberKey': member, 'rowSha256': exporter.json_sha(value),
                         'displayOrder': value[columns['display_order']], 'consumer': spec['consumer'], 'selection': spec['selection'],
                         'filtersPreserved': spec['filters'], 'status': 'passed'}
                if folder_mode:
                    route.update(folderKey=outer, containerPresent=outer in folders,
                                 containerRowSha256=exporter.json_sha(folders.get(outer)))
                    if outer not in folders:
                        route['status'] = 'blocked_missing_folder_container'
                elif logical.endswith('/event_list.orderedmap'):
                    definition = parents[key]
                    native = flat[definition['source']][str(definition['id'])][0]
                    column = string_ids.get(typ, {}).get('column')
                    if excluded is None or column is None:
                        route['status'] = 'unreviewed_direct_box_link_filter'
                    else:
                        matched = native[column] in excluded[0][0]
                        route.update(boxLinkExcluded=matched, boxLinkUiStringSha256=exporter.json_sha(excluded),
                                     parentStringIdColumn=column)
                        if matched:
                            route['status'] = 'excluded_by_native_box_link_filter'
                result[key]['routes'].append(route)
    for key, row in result.items():
        row['status'] = 'verified_static_membership' if any(route['status'] == 'passed' for route in row['routes']) else (
            'unreviewed' if any(route['status'].startswith('unreviewed') for route in row['routes']) else 'blocked_absent_original_route')
        row['blockers'] = [] if row['status'] == 'verified_static_membership' else [blocker(
            'native_entry_membership', '原生入口表未给出可达路径；禁止从父定义存在推定玩家有入口', routes=row['routes'])]
    return result


def native_quest_rules_document(nodes, schema, source, resources, schema_receipt, excluded, catalog_sha):
    preserved = ['clearRewardId', 'scoreRewardGroupId', 'sPlusRewardId', 'rankPointReward', 'characterExpReward', 'manaReward', 'poolExpReward']
    projected = {key: {'parentKey': node['parents'][0], 'kind': node['nativeKind'], 'fields': node['nativeProjection'],
                       'nativeEligibility': node['nativeEligibility'], 'fieldKeys': node['battleReferences']['expectedFieldKeys'],
                       'source': {**node['nativeRows'][0], **node['nativeSchema']},
                       'currentOverlayPriorityFields': preserved if node['parents'][0] in ['rush_event:700099', 'rush_event:700100'] else ['sPlusRewardId'] if node['category'] == 21 else [],
                       **({'drawnQuestOptions': node['drawnQuestOptions']} if node.get('drawnQuestOptions') else {})}
                 for key, node in nodes.items()}
    return {'schemaVersion': 1,
            'source': {'assetVersion': source['assetVersion'], 'manifestSha256': source['manifestSha256'], 'catalogSha256': catalog_sha, 'schema': schema_receipt,
                       'resources': {logical: resources[logical] for logical in sorted(resources) if logical in {item['logical'] for item in schema['tables'].values()}}},
            'units': {name: 'milliseconds' for name in ['bRankTime', 'aRankTime', 'sRankTime', 'sPlusRankTime']},
            'quests': projected,
            'overlayPolicy': {'preserveCurrentParents': ['rush_event:700099', 'rush_event:700100'], 'preserveCurrentParentFields': preserved,
                              'preserveAfterNativeProjection': [
                                  {'category': 21, 'field': 'sPlusReward', 'rule': 'Existing CN Recollection SS item14040 x3 override remains after reward resolution', 'source': 'src/lib/assets.ts'},
                                  {'key': '24:700100099', 'rule': 'Existing Abyss EX endless zero scalar and no clear/SS/score reward override remains last', 'source': 'src/lib/assets.ts;src/lib/abyss-modes.ts'}],
                              'excludedCurrentOnlyNativeParents': excluded,
                              'scope': 'Native source projection only; no business getter, control identity, player state or saved reward is changed by this generator.'}}


def prior_entry_references(exporter, root, source, schema, parents, flat, current):
    targets = {key for key, row in current.items() if row['status'] != 'verified_static_membership'}
    history, state = {key: [] for key in targets}, {}
    logicals = {row['logical'] for group in ['membershipTables', 'additionalTables'] for row in schema[group]}
    required = {row['logical'] for row in schema['membershipTables']}
    seen = set()
    for archive in source['actualChain']:
        path = root / archive['archive']
        if path.stat().st_size != archive['size'] or str(path.stat().st_mtime_ns) != str(archive['mtimeNs']):
            raise ValueError('older native membership archive changed: ' + str(path))
        changed = False
        with zipfile.ZipFile(path) as zipped:
            for logical in sorted(logicals):
                try:
                    raw = zipped.read(exporter.member(logical))
                except KeyError:
                    continue
                state[logical] = (raw, {'archive': archive['archive'], 'member': exporter.member(logical), 'sha256': sha(raw)})
                changed = True
        if not changed or not required <= set(state):
            continue
        snapshot = native_entries(exporter, state, schema, parents, flat)
        for key in targets:
            for route in snapshot[key]['routes']:
                identity = json.dumps([key, route], sort_keys=True, separators=(',', ':'))
                if identity in seen:
                    continue
                seen.add(identity)
                history[key].append({'route': route, 'membershipReceipt': state[route['source']][1],
                                     'observedAtArchive': archive['archive'], 'status': 'reference_only_not_current_route'})
    return {'schemaVersion': 1, 'manifestSha256': source['manifestSha256'], 'parents': history,
            'scope': 'Sparse reads of the same CDN chain older membership versions only. No historical battle or reward masters are substituted. This is routing reference, not a current reachable path.'}


def native_quest_reward_members(exporter, inputs, schema, quests, server, native_ids, server_ids, overlays):
    logical = schema['logicalTables']
    clear = exporter.parse_rows(inputs[logical['ClearRewardValues']][0], 'clear_reward')
    score = exporter.nested_rows(inputs[logical['ScoreRewardValues']][0], 'score_reward', 2)
    rare = exporter.nested_rows(inputs[logical['RareScoreRewardValues']][0], 'rare_score_reward', 2)
    conversions = exporter.nested_rows(inputs[logical['RewardElementMapValues']][0], 'reward_element_map', 3)
    index = {}
    def number(value):
        if value in [None, '', '(None)']:
            return None
        result = float(value)
        return int(result) if result.is_integer() else result
    def member(kind, ident, amount):
        kind = int(kind)
        return {'type': kind, 'id': number(ident) if kind in [0, 1, 2, 6, 7] else None,
                'count': 1 if kind == 2 else number(amount)}
    def remote(value, score_common=False):
        if value is None:
            return None
        return member(value.get('reward_type') if score_common else value.get('type'), value.get('id'), value.get('count'))
    def refs(rewards):
        checks = []
        for reward in rewards:
            if reward['type'] not in [0, 1, 2]:
                continue
            kind = {0: 0, 1: 4, 2: 3}[reward['type']]
            ident = str(reward['id'])
            checks.append({'kind': kind, 'id': reward['id'], 'nativeAndServerPresent': ident in native_ids[kind] and ident in server_ids[kind]})
        return checks
    def take(kind, ident):
        key = kind + ':' + str(ident)
        if key in index:
            return key
        raw = {'clear': clear, 'score': score, 'rare': rare}[kind].get(str(ident))
        actual = server[kind].get(str(ident))
        entry = {'key': key, 'kind': kind, 'id': int(ident), 'present': actual is not None, 'nativePresent': raw is not None,
                 'nativeRowSha256': exporter.json_sha(raw), 'serverRowSha256': exporter.json_sha(actual), 'members': [],
                 'issues': [], 'referenceChecks': [], 'childRewardKeys': [], 'staticStatus': 'passed'}
        index[key] = entry
        if raw is None or actual is None:
            entry.update(staticStatus='missing', nativeServerParity='missing')
            return key
        projected, observed, rewards = [], [], []
        if kind == 'clear':
            value = raw[0]
            projected = member(value[1], value[2], value[3])
            observed = remote(actual)
            rewards.append(projected)
        else:
            runtime_positions = {str(value.get('position', offset + 1)): value for offset, value in enumerate(actual)}
            for position, values in raw.items():
                value = values[0]
                existing = runtime_positions.get(position) if kind == 'score' else actual[int(position) - 1] if 0 < int(position) <= len(actual) else None
                if kind == 'score' and value[1] == '1':
                    result = {'position': int(position), 'lotteryKind': 1, 'rareGroup': int(value[6]), 'probability': number(value[7])}
                    observed.append({'position': int(position), 'lotteryKind': existing.get('type'), 'rareGroup': existing.get('id'), 'probability': existing.get('rarity')} if existing else None)
                    entry['childRewardKeys'].append(take('rare', value[6]))
                else:
                    native = member(value[2], value[3], value[4]) if kind == 'score' else member(value[1], value[2], value[3])
                    result = {'position': int(position), 'reward': native,
                              'weight' if kind == 'score' else 'probability': number(value[5] if kind == 'score' else value[4])}
                    observed.append({'position': int(position), 'reward': remote(existing, kind == 'score'),
                                     'weight' if kind == 'score' else 'probability': existing.get('field5' if kind == 'score' else 'rarity')} if existing else None)
                    rewards.append(native)
                projected.append(result)
            if len(raw) != len(actual):
                entry['issues'].append('原生与服务端奖励成员数量不同')
        entry.update(members=projected, serverMembers=observed, referenceChecks=refs(rewards))
        entry['conversionRewards'] = [reward for reward in rewards if reward['type'] in [6, 7]]
        if projected != observed:
            entry['issues'].append('原生与服务端奖励成员、数量或概率不同')
        if any(not value['nativeAndServerPresent'] for value in entry['referenceChecks']):
            entry['issues'].append('收费或奖励引用定义缺失')
        overlay = str(ident) in overlays.get(kind, {})
        entry['nativeServerParity'] = 'preserved_current_overlay' if overlay else 'mismatch' if entry['issues'] else 'passed'
        entry['staticStatus'] = 'passed' if overlay and all(value['nativeAndServerPresent'] for value in entry['referenceChecks']) else 'mismatch' if entry['issues'] else 'passed'
        return key
    for key, quest in quests.items():
        native = quest.get('nativeProjection', {})
        effective = quest.get('effectiveServerDefinition', native)
        for name, fields in [('nativeRewardDependencyKeys', native), ('rewardDependencyKeys', effective)]:
            selected = []
            for field, kind in [('clearRewardId', 'clear'), ('sPlusRewardId', 'clear'), ('scoreRewardGroupId', 'score')]:
                if fields.get(field) is not None:
                    selected.append(take(kind, fields[field]))
            quest[name] = sorted(set(selected))
        all_keys = set(quest['nativeRewardDependencyKeys']) | set(quest['rewardDependencyKeys'])
        all_keys.update(child for reward in list(all_keys) for child in index[reward]['childRewardKeys'])
        elements = {native['element']} if native.get('element') is not None else {row['element'] for row in quest.get('drawnQuestOptions', []) if row['element'] is not None}
        checks = []
        for reward_key in sorted(all_keys):
            for reward in index[reward_key].get('conversionRewards', []):
                branch = '1' if reward['type'] == 6 else '2'
                for element in sorted(elements) if elements else [None]:
                    row = conversions.get(branch, {}).get(str(reward['id']), {}).get(str(element))
                    ident = row[0][0] if row else None
                    checks.append({'rewardKey': reward_key, 'kind': reward['type'], 'rarity': reward['id'], 'questElement': element,
                                   'itemId': number(ident), 'nativeAndServerPresent': ident in native_ids[0] and ident in server_ids[0]})
        quest['rewardConversionChecks'] = checks
        quest['nativeRewardStaticStatus'] = 'passed' if all(index[reward]['staticStatus'] == 'passed' for reward in all_keys) and all(row['nativeAndServerPresent'] for row in checks) else 'blocked'
    return index


def extra_consumed_field_audit(exporter, inputs, schema, quests, tables, entry_costs):
    schemas = {value['logical']: value for value in schema['tables'].values()}
    decoded = {}
    result = {}
    for key, quest in quests.items():
        record = quest['nativeRows'][0]
        logical = record['source']
        if logical not in decoded:
            decoded[logical] = exporter.nested_rows(inputs[logical][0], logical, 2)
        raw = decoded[logical][record['event']][record['member']][0]
        columns = schemas[logical]['allResolvedScalarColumns']
        actual = tables[quest['serverDefinition']['source']].get(str(quest['questId']), {})
        def optional(name, scale=1):
            if name not in columns:
                return None
            value = raw[columns[name]]
            return None if value in ['', '(None)'] else int(float(value) * scale)
        projection = {}
        if quest.get('nativeKind') != 'Story' and 'battle_fixed_party' in columns:
            projection['fixedParty'] = optional('battle_fixed_party')
        if quest['category'] == 24:
            projection.update(rushEventId=int(record['event']), rushEventFolderId=optional('folder_id'), rushEventRound=optional('round'))
        if quest['category'] == 27:
            projection.update(eventId=int(record['event']), folderId=optional('folder_id'), scoreAttackQuestId=int(record['member']),
                              bRankScore=optional('result_rank_b_score'), aRankScore=optional('result_rank_a_score'),
                              sRankScore=optional('result_rank_s_score'), ssRankScore=optional('result_rank_ss_score'))
        elif actual.get('eventId') is not None:
            projection['eventId'] = int(record['event'])
        differences = [{'field': name, 'native': expected, 'server': actual.get(name)} for name, expected in projection.items() if expected != actual.get(name)]
        entry = entry_costs.get(key.replace(':', '_'))
        nominal = optional('battle_stamina_cost') if quest.get('nativeKind') != 'Story' else 0
        observed = (entry or {}).get('stamina', 0)
        result[key] = {'nativeFields': projection, 'rawServerDifferences': differences,
                       'nominalStamina': {'native': nominal, 'server': observed, 'matches': (nominal or 0) == observed,
                                          'entryPresent': entry is not None, 'freeAdmissionPreserved': True,
                                          'preservedPolicy': 'multiplayer_existing_policy' if quest['category'] == 8 else
                                              'current_cn_mod_overlay' if any(parent in ['rush_event:700099', 'rush_event:700100'] for parent in quest['parents']) else None},
                       'nativeClientOwnedScalars': {name: optional(name) for name in ['battle_enemy_level', 'battle_max_continue_count', 'daily_challenge_point_id'] if name in columns},
                       'notConsumedByRawQuest': ['native kind/story routing', 'native prerequisite/rank/unlock constraints',
                                                  'enemy level and party restrictions', 'native attempt/continue limits'],
                       'sourceScope': 'Additional fields actually exposed by RawQuest/getQuestSync, ScoreAttack rank code, Rush round/folder code and nominal stamina credit. Client-native guards are not represented as server verification.'}
        if quest['category'] == 27:
            native_time = optional('battle_time_limit')
            result[key]['forwardedTimeLimit'] = {'nativeRaw': native_time, 'serverMilliseconds': actual.get('timeLimitMs'),
                                                 'matchesNativeAt60Fps': native_time * 1000 / 60 == actual.get('timeLimitMs') if native_time is not None else actual.get('timeLimitMs') is None,
                                                 'unitStatus': '60fps numerical equivalence; no RawQuest gameplay consumer; not classified as a mismatch'}
    return result


def collect_missions(exporter, inputs, catalog):
    nodes, parents = {}, defaultdict(list)
    for category, (spec, parent_type) in MISSION_SPECS.items():
        stem, asset, parent_col = exporter.MISSION_TABLES[spec]
        logical, reward = stem + '.orderedmap', stem + '_reward.orderedmap'
        if logical not in inputs:
            continue
        rewards = exporter.nested_rows(inputs[reward][0], reward, 2) if reward in inputs else {}
        for ident, values in exporter.parse_rows(inputs[logical][0], logical).items():
            if len(values) != 1:
                raise ValueError('ambiguous native mission: ' + logical + '/' + ident)
            value = values[0]
            parent = parent_type + ':' + (value[parent_col] if parent_col is not None else ident)
            key = str(category) + ':' + ident
            parent_matches = catalog['missionMap'].get(key) == parent
            nodes[key] = {'key': key, 'category': category, 'missionId': int(ident), 'parentKey': parent,
                          'relation': 'retained-only' if parent == 'active_mission_event:150' else
                                      'parent_scoped' if category in [0, 4, 6, 7, 8] else 'independent_child',
                          'independentParentAssociation': 'not_inferred' if category in [1, 2, 3] else None,
                          'source': logical, 'rewardSource': reward, 'rowSha256': exporter.json_sha(value),
                          'rewardStages': sorted(rewards.get(ident, {})),
                          'rewardDefinitionSha256': exporter.json_sha(rewards.get(ident)),
                          'catalogOwner': catalog['missionMap'].get(key), 'catalogOwnerMatches': parent_matches,
                          'ruleSupport': 'unreviewed', 'rewardSemantics': 'unreviewed'}
            if category in [6, 7, 8]:
                nodes[key]['nativePatternType'] = int(value[3])
            if category == 7 and value[3] == '20':
                nodes[key]['ruleDecision'] = {'mode': 'successful_rescue_finish_once', 'qualification': 'trusted accepted rescue and durable playId binding',
                                               'existingProgressPreserved': True, 'implementationVerification': 'under_review'}
            if parent == 'active_mission_event:150':
                nodes[key]['ruleDecision'] = {'mode': 'deferred_new_participation_by_decision', 'existingClaimsPreserved': True,
                                               'grantNewComebackQualification': False}
            if key == '0:21030' and parent == 'active_mission_event:3':
                nodes[key]['ruleDecision'] = {'mode': 'campaign2_final_character_exchange_once',
                                               'trigger': 'successful final character exchange, not entry or preview',
                                               'implementationVerification': 'under_review'}
            parents[parent].append(key)
    return nodes, parents


def server_shop_tables(repo):
    base = load(repo / 'assets/event_item_shop.json')
    overlay = load(repo / 'assets/event_item_shop_rank_p5b.json')
    events = copy.deepcopy(base)
    events.setdefault('11', {}).setdefault('700099', {}).update(overlay.get('11', {}).get('700099', {}))
    mapping = {**load(repo / 'assets/event_item_shop_id_map.json'), **load(repo / 'assets/event_item_shop_id_map_rank_p5b.json')}
    mapping.pop('59001010', None)  # Explicit retired Five Boss product remains outside the active accessor.
    result = {typ: load(repo / ('assets/' + typ + '.json')) for typ in
              ['general_shop', 'star_grain_shop', 'treasure_shop', 'boss_coin_shop']}
    result.update(event_item_shop=events, eventMap=mapping,
                  bossMap=load(repo / 'assets/boss_coin_shop_item_category_map.json'))
    return result


def server_product(row, tables):
    ident, typ = str(row['id']), row['type']
    if typ == 'event_item_shop':
        mapping = tables['eventMap'].get(ident)
        return None if not mapping else tables[typ].get(str(mapping['eventType']), {}).get(str(mapping['eventId']), {}).get(ident)
    if typ == 'boss_coin_shop':
        return tables[typ].get(str(tables['bossMap'].get(ident)), {}).get(ident)
    return tables[typ].get(ident)


def product_schema(path):
    if not path:
        return {}, {}
    evidence = load(path)
    schema = evidence.get('schemaMethodReceipt', evidence)
    labels = {'GeneralShopValues': 'general_shop', 'StarGrainShopValues': 'star_grain_shop',
              'TreasureShopValues': 'treasure_shop', 'BossCoinShopValues': 'boss_coin_shop', 'EventItemShopValues': 'event_item_shop'}
    result = {}
    for method in schema.get('methods', []):
        for label, typ in labels.items():
            if label in method.get('label', '') and 'arrayColumnReadsAtFieldAssignments' in method:
                result[typ] = method['arrayColumnReadsAtFieldAssignments']
    return result, {row['key']: row for row in evidence.get('products', [])}


def native_stone_price_matches(price, server):
    """Only the verified native Stone=0 / server VMONEY=0 currency pair."""
    if price is None:
        return not server.get('userCost')
    cost = server.get('userCost')
    return (type(price.get('kind')) is int and price['kind'] == 0
            and type(price.get('count')) is int and price['count'] > 0
            and isinstance(cost, dict) and type(cost.get('type')) is int and type(cost.get('amount')) is int
            and server.get('userCost') == {'type': 0, 'amount': price['count']})


def reviewed_veteran_degree_semantics(raw, server):
    """One original custom product uses a native PassCardPoint display placeholder.

    Bind the complete reviewed 51-column row, not the placeholder enum generally.
    The server remains authoritative for granting degree 9900006; no reward or
    price is rewritten here, and an altered native row loses this exception.
    """
    rewards = server.get('rewards')
    return (sha(json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf8'))
            == 'b79a56c6b24c3c1cd8dd8ac799b49ea7095e0738475ff5cd6209bea4a3387001'
            and server.get('costs', []) == []
            and native_stone_price_matches({'kind': 0, 'count': 5000000}, server)
            and isinstance(rewards, list) and len(rewards) == 1 and isinstance(rewards[0], dict)
            and all(type(rewards[0].get(field)) is int for field in ('type', 'id', 'count'))
            and rewards == [{'type': 5, 'id': 9900006, 'count': 1}])


def audit_product(row, raw, server, columns, prior):
    """Known constructor-column receipt only. Unknown quota/ownership semantics remain explicit."""
    issues, review, matches = [], [], {}
    if not raw:
        return {'status': 'missing', 'issues': ['原生商品定义缺失'], 'review': [], 'matches': {}}
    if not server:
        return {'status': 'missing', 'issues': ['当前服务端商品或真实父映射缺失'], 'review': [], 'matches': {}}
    if not columns:
        return {'status': 'unreviewed', 'issues': [], 'review': ['缺少已确认的原生商品字段映射'], 'matches': {}}
    def cell(name, default=None):
        indices = columns.get(name)
        return raw[indices[0]] if indices else default
    def optional(value):
        return None if value in (None, '', '(None)') else int(value)
    costs = []
    for number in range(1, 5):
        pair = columns.get('cost_item' + str(number), [])
        if pair and raw[pair[0]] not in ('', '(None)'):
            costs.append({'id': int(raw[pair[0]]), 'amount': int(raw[pair[1]])})
    rewards = []
    for number in range(1, 7):
        fields = columns.get('kind' + str(number), [])
        if not fields or raw[fields[0]] in ('', '(None)'):
            continue
        kind, ident, amount = (raw[index] for index in fields)
        rewards.append({'type': int(kind), **({'id': int(ident)} if ident.isdigit() else {}), 'count': int(amount)})
    stock_once, limit = optional(cell('buy_max_count')), optional(cell('max_frequency'))
    matches['costs'] = costs == server.get('costs', [])
    veteran_degree = reviewed_veteran_degree_semantics(raw, server)
    matches['rewards'] = rewards == server.get('rewards', []) or veteran_degree
    price = columns.get('price', [])
    no_user_cost = not price or raw[price[0]] in ('', '(None)')
    native_price = None if no_user_cost else {'kind': int(raw[price[0]]), 'count': int(raw[price[1]])}
    matches['userCost'] = native_stone_price_matches(native_price, server)
    matches['cumulativeStock'] = limit == server.get('stock')
    matches['perRequestMaximumProtected'] = stock_once is None or (isinstance(server.get('stock'), int) and 0 < server['stock'] <= stock_once)
    for native, runtime in [('daily_stock', 'dailyStock'), ('monthly_stock', 'monthlyStock')]:
        matches[runtime] = (optional(cell(native)) or 0) == (server.get(runtime) or 0)
    for field, ok in matches.items():
        if not ok:
            issues.append('原生与服务端商品字段不一致：' + field)
    for field in ['daily_stock', 'monthly_stock']:
        if (optional(cell(field)) or 0) > 0:
            review.append('需要核对周期库存账本：' + field)
    if cell('cost_item_schedule_id') not in (None, '', '(None)'):
        review.append('需要核对动态收费表')
    if not no_user_cost and not veteran_degree:
        review.append('需要核对玩家货币扣款种类与原生资格')
    if server.get('maxFrequency', 0) > 0:
        review.append('服务端追加购买频次规则仍需核对')
    previous = prior.get(row['key'])
    if previous and previous.get('clientRowSha256') == sha(json.dumps([raw], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf8')):
        if previous.get('client', {}).get('equipmentOnlyPossessionOne'):
            review.append('需要核对装备唯一持有规则')
    elif any(reward['type'] == 4 for reward in rewards):
        review.append('需要核对装备持有与唯一购买规则')
    if row['type'] == 'general_shop':
        review.append('需要核对当前普通商店销售白名单')
    return {'status': 'mismatch' if issues else 'unreviewed' if review else 'verified_static', 'issues': issues,
            'review': review, 'matches': matches, 'nativeCosts': costs, 'nativeRewards': rewards,
            'stockOnce': stock_once, 'cumulativeLimit': limit}


def runtime_receipts(repo, products, missions=None, quests=None, runtime_catalog=None, runtime_evidence=None, runtime_keys=None,
                     product_keys=None, runtime_details=False):
    """Compile only the pure definition-capture module in memory; never import database/business handlers."""
    code = r'''
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const root=process.cwd();
function sourceModule(relative){const file=path.join(root,relative),m=new Module(file,module);
 m.filename=file;m.paths=Module._nodeModulePaths(path.dirname(file));
 m.require=name=>{
   if(name==='./exchange-campaign-definitions')return sourceModule('src/lib/exchange-campaign-definitions.ts');
   if(name==='./awake-master-assets')return sourceModule('src/lib/mission/awake-master-assets.ts');
   if(name==='./content-operations'&&relative==='src/lib/box-gacha-policy.ts')return {contentCatalog:{rows:[]}};
   if(name==='./content-quest-rules'&&relative==='src/lib/stamina-cost.ts')return sourceModule('src/lib/content-quest-rules.ts');
   if(name==='./stamina-campaign'&&relative==='src/lib/stamina-cost.ts')return {getActiveCampaignRate:()=>1};
   if(name==='../utils'&&relative==='src/lib/stamina-cost.ts')return {getServerDate:()=>new Date('2025-07-20T04:00:00.000Z')};
   if(name.endsWith('.json')){const resolved=path.resolve(path.dirname(file),name);
     if(!resolved.startsWith(path.join(root,'assets')+path.sep))throw Error('JSON outside reviewed assets');return JSON.parse(fs.readFileSync(resolved,'utf8'));}
   if(['node:fs','node:path','node:crypto','node:zlib','fs','path','crypto'].includes(name))return require(name);
   throw Error('Unreviewed pure-module dependency: '+name);};
 m._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText,file);return m.exports;}
const {captureExactDefinition:capture,exactDefinitionHash:hash,matchCampaignDefinition:campaign,matchExactDefinition:existing}=sourceModule('src/lib/content-definition-evidence.ts');
const {getBoxOperationRules}=sourceModule('src/lib/box-gacha-policy.ts'),rewards=sourceModule('src/lib/mission/rewards.ts'),pass=sourceModule('src/lib/pass-card.ts');
const allBoxes=JSON.parse(fs.readFileSync(path.join(root,'assets/box_reward.json'),'utf8'));
const data=JSON.parse(fs.readFileSync(0,'utf8')),cache=new Map(),rows={},loaderSets={},campaigns={},boxes={},existingMatches={},reboundMatches={},missionRewards={},passEvents={},passRewards={},effectiveQuests={},staminaCosts={},nativeStaminaCosts={},effectiveProducts={};
if(data.runtimeCatalog){
 const source=fs.readFileSync(path.join(root,'src/lib/content-operations.ts'),'utf8');
 const ast=ts.createSourceFile('content-operations.ts',source,ts.ScriptTarget.ES2020,true,ts.ScriptKind.TS);
 const names=new Set(['historicalCatalogIsCurrent','canonicalEvidence','reviewedExistingLoaderRebind','nativeQuestIdentity','nativeShopIdentity','runtimeDefinition','baseRuntimeDefinition']);
 const declarations=ast.statements.filter(node=>ts.isFunctionDeclaration(node)&&node.name&&names.has(node.name.text));
 if(declarations.length!==names.size)throw Error('Runtime definition pure-function boundary changed');
 const owners=ast.statements.filter(node=>ts.isVariableStatement(node)&&node.declarationList.declarations.some(d=>d.name.getText(ast)==='nativeShopOwners'));
 if(owners.length!==1)throw Error('Native shop owner boundary changed');
 const javascript=ts.transpileModule([...owners,...declarations].map(node=>node.getText(ast)).join('\n'),{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText;
 const invoke=new Function('contentCatalog','historicalEvidence','questParents','capturedSources','createHash','readFileSync','path','matchCampaignDefinition','matchExactDefinition','__dirname','keys','details',
  `let historicalCatalogMatches;let nativeQuestIdentities;let nativeShopIdentities;${javascript}\nconst byKey=new Map(contentCatalog.rows.map(row=>[row.key,row])),sourceHashes=new Map();return Object.fromEntries(keys.map(key=>{const row=byKey.get(key),result=runtimeDefinition(row);if(!details)return[key,result];const mismatches=(row.definitionEvidence?.serverSources??[]).filter(source=>{if(!sourceHashes.has(source)){try{sourceHashes.set(source,createHash('sha256').update(readFileSync(path.resolve(__dirname,'../..',source))).digest('hex'))}catch{sourceHashes.set(source,null)}}return sourceHashes.get(source)!==contentCatalog.serverResources?.[source]?.sha256});return[key,{...result,base:baseRuntimeDefinition(row),exact:matchExactDefinition(row,path.resolve(__dirname,'../..')),historicalReceiptPresent:!!historicalEvidence.rows[key],reviewedRebind:reviewedExistingLoaderRebind(row),questIdentityRequired:questParents.has(key),questIdentityAvailable:!!nativeQuestIdentity(key),shopIdentityRequired:nativeShopOwners.has(key),shopIdentityAvailable:!!nativeShopIdentity(key),wholeSourceMismatches:mismatches}]}));`);
 const matrix=invoke(data.runtimeCatalog,data.runtimeEvidence,new Set(Object.values(data.runtimeCatalog.questMap)),new Map(),require('node:crypto').createHash,fs.readFileSync,path,campaign,existing,path.join(root,'src/lib'),data.runtimeKeys,data.runtimeDetails);
 process.stdout.write(JSON.stringify({runtimeDefinitions:matrix,method:'Unmodified seven AST function bodies and nativeShopOwners from actual content-operations.ts; real fs and original matchers; fresh evidence injection, no getDb import'}));process.exit(0);
}
for(const row of data.rows){const match=campaign(row,root);if(match)campaigns[row.key]=match;
 if(row.exactDefinitionEvidence||row.currentParentDefinitionEvidence)existingMatches[row.key]=existing(row,root);
 if(row.type==='box_gacha'){const rules=getBoxOperationRules(row,allBoxes[String(row.id)]??{});boxes[row.key]={policyAccepted:rules!==null,stages:rules?.size??0};}
 if(row.type==='pass_card_event')passEvents[row.key]=pass.getPassCardEventDefinition(row.id)??null;
 const c=capture(row,root,cache);if(!c)continue;const loaderSetId=hash(c.loaders);loaderSets[loaderSetId]=c.loaders;
 const prior=row.exactDefinitionEvidence??row.currentParentDefinitionEvidence;
 if(prior&&prior.dependencyDigest===c.digest){const field=row.exactDefinitionEvidence?'exactDefinitionEvidence':'currentParentDefinitionEvidence';
  reboundMatches[row.key]=existing({...row,[field]:{...prior,loaders:c.loaders}},root);}
 rows[row.key]={schemaVersion:1,key:row.key,definitionDigest:row.definitionDigest,dependencyDigest:c.digest,loaderSetId,
 dependencySelectors:Object.keys(c.dependencies),nonNullSelectors:Object.keys(c.dependencies).filter(k=>c.dependencies[k]!==null)};}
for(const [key,node] of Object.entries(data.missions))missionRewards[key]=Object.fromEntries(node.rewardStages.map(stage=>[stage,
 node.category===0?rewards.getMissionRewardStageDefinition(node.missionId,Number(stage)):rewards.getCategoryMissionRewardStageDefinition(node.category,node.missionId,Number(stage))]));
for(const id of Object.keys(JSON.parse(fs.readFileSync(path.join(root,'assets/pass_card_reward.json'),'utf8'))))passRewards[id]=pass.getPassCardRewardDefinition(Number(id))??null;
if(data.productKeys?.length){
 const source=fs.readFileSync(path.join(root,'src/lib/assets.ts'),'utf8'),ast=ts.createSourceFile('assets.ts',source,ts.ScriptTarget.ES2020,true,ts.ScriptKind.TS);
 const wanted=new Set(['getShopItemSync','getUnprojectedShopItemSync','addShopCompatibilityPeriod']);
 const funcs=ast.statements.filter(node=>ts.isFunctionDeclaration(node)&&node.name&&wanted.has(node.name.text));
 const period=ast.statements.filter(node=>ts.isVariableStatement(node)&&node.declarationList.declarations.some(d=>d.name.getText(ast)==='RUSH_RERUN_SHOP_PERIODS'));
 if(funcs.length!==3||period.length!==1)throw Error('Actual event-shop getter boundary changed');
 const js=ts.transpileModule([...period,...funcs].map(node=>node.getText(ast)).join('\n'),{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText;
 const master=sourceModule('src/lib/content-master.ts'),{applyContentNativeShopRules}=sourceModule('src/lib/content-shop-rules.ts'),{ShopType}=sourceModule('src/lib/types/shop.ts');
 const invoke=new Function('exports','ShopType','eventItemShopIdMap','eventItemShopItems','applyContentNativeShopRules','keys',`${js}\nreturn Object.fromEntries(keys.map(key=>[key,getShopItemSync(ShopType.EVENT_ITEM,key.split(':')[1])]))`);
 Object.assign(effectiveProducts,invoke({},ShopType,master.serverEventShopIdMap,master.serverEventShops,applyContentNativeShopRules,data.productKeys));
}
if(fs.existsSync(path.join(root,'src/lib/content-quest-rules.ts'))){const {applyContentQuestRules:apply,getContentNativeStaminaCost:nativeStamina}=sourceModule('src/lib/content-quest-rules.ts');
 for(const [key,node] of Object.entries(data.quests)){effectiveQuests[key]=apply(node.category,node.questId,node.definition);
  if(nativeStamina)nativeStaminaCosts[key]=nativeStamina(node.category,node.questId);}}
const {getStaminaCost}=sourceModule('src/lib/stamina-cost.ts');
for(const key of Object.keys(data.quests))staminaCosts[key]=getStaminaCost(key.replace(':','_'));
process.stdout.write(JSON.stringify({rows,loaderSets,campaigns,boxes,existingMatches,reboundMatches,missionRewards,passEvents,passRewards,effectiveQuests,staminaCosts,nativeStaminaCosts,effectiveProducts}));
'''
    run = subprocess.run(['node', '-e', code], input=json.dumps({'rows': products, 'missions': missions or {}, 'quests': quests or {},
                         'runtimeCatalog': runtime_catalog, 'runtimeEvidence': runtime_evidence, 'runtimeKeys': runtime_keys,
                         'productKeys': product_keys or [], 'runtimeDetails': runtime_details}), cwd=repo, text=True,
                         encoding='utf8', stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if run.returncode:
        raise ValueError('pure runtime dependency capture failed: ' + run.stderr[-2000:])
    return json.loads(run.stdout)


def validate_shop_getter_evidence(evidence_path, repo, product_keys):
    document = load(evidence_path)
    expected = {'stock', 'nativeStockLimits', 'dailyStock', 'monthlyStock', 'kind1EquipmentOnlyPossessionOne'}
    if (document.get('schemaVersion') != 1 or document.get('status') != 'actual_getter_projection_passed'
            or document.get('staticOnly') is not True or document.get('httpBusinessVerified') is not False
            or document.get('count') != len(product_keys) or sorted(document.get('keys', [])) != sorted(product_keys)
            or set(document.get('projectedFields', [])) != expected
            or set(document.get('preservedFields', [])) != {'costs', 'rewards', 'userCost', 'availableFrom', 'availableUntil'}
            or document.get('publicMasterBytesPreserved') is not True
            or document.get('uncataloguedCurrentOnlyIdsNotProjected') != list(range(9700121, 9700130))):
        raise ValueError('actual getter proof does not cover exact native event-shop scope')
    frozen = {record['path']: record['sha256'].lower() for record in document.get('sourceFreeze', [])}
    if not {'src/lib/assets.ts', 'src/lib/content-shop-rules.ts', 'assets/content_history_shop_rules.json'} <= set(frozen):
        raise ValueError('actual getter proof lacks consumed sources')
    for relative, digest in frozen.items():
        target = (repo / relative).resolve()
        if not target.is_relative_to(repo) or not re.fullmatch('[a-f0-9]{64}', digest) or sha(target.read_bytes()) != digest:
            raise ValueError('actual getter proof source changed: ' + relative)
    log = Path(evidence_path).parent / 'root-shop-projection-src.log'
    if sha(log.read_bytes()) != document.get('logSha256'):
        raise ValueError('actual getter transaction-independent test log changed')
    return {'file': Path(evidence_path).name, 'sha256': sha(Path(evidence_path).read_bytes()),
            'sourceHashes': frozen, 'logSha256': document['logSha256'], 'staticOnly': True,
            'httpBusinessVerified': False}


def effective_shop_field_audit(legacy, native, raw, value, evidence):
    if value is None:
        raise ValueError('actual native shop getter returned no product')
    audit = copy.deepcopy(legacy)
    matches = audit['matches']
    veteran_degree = reviewed_veteran_degree_semantics(raw, value)
    matches.update(costs=audit.get('nativeCosts', []) == value.get('costs', []),
                   rewards=audit.get('nativeRewards', []) == value.get('rewards', []) or veteran_degree,
                   userCost=native_stone_price_matches(native['price'], value),
                   cumulativeStock=value.get('nativeStockLimits', {}).get('lifetime', 'missing') == native['max_frequency'],
                   perRequestMaximumProtected=value.get('nativeStockLimits', {}).get('perRequest') == native['buy_max_count'],
                   dailyStock=value.get('dailyStock') == native['daily_stock'],
                   monthlyStock=value.get('monthlyStock') == native['monthly_stock'],
                   kind1EquipmentOnlyPossessionOne=value.get('kind1EquipmentOnlyPossessionOne') == native['kind1_equipment_only_possession_one'],
                   startDate=value.get('availableFrom') == raw[26],
                   endDate=value.get('availableUntil') == (None if raw[27] == '(None)' else raw[27]))
    audit['issues'] = ['原生与有效服务端商品字段不一致：' + name for name, ok in matches.items() if not ok]
    for reference in audit.get('referenceChecks', []):
        if not reference['nativeAndServerPresent']:
            audit['issues'].append('原生或服务端收费/奖励定义缺失：' + str(reference['kind']) + ':' + str(reference['id']))
    audit['review'] = [reason for reason in legacy.get('review', []) if '装备' not in reason]
    if veteran_degree:
        audit['review'] = [reason for reason in audit['review'] if reason != '需要核对玩家货币扣款种类与原生资格']
        audit['semanticBridge'] = {'kind': 'veteran_degree_display_placeholder', 'productId': 9700118,
                                   'degreeId': 9900006, 'nativeRewardKind': 6, 'serverRewardType': 5,
                                   'nativeRowSha256': 'b79a56c6b24c3c1cd8dd8ac799b49ea7095e0738475ff5cd6209bea4a3387001',
                                   'scope': 'Exact original native name/icon/description/price/limits; server degree grant is authoritative'}
    if native['kind1_equipment_only_possession_one']:
        audit['review'].append('需要核对装备唯一持有规则')
    audit['status'] = 'mismatch' if audit['issues'] else 'unreviewed' if audit['review'] else 'verified_static'
    audit['rawFieldAuditPreserved'] = True
    audit['effectiveGetterValue'] = value
    audit['definitionFieldsMatched'] = not audit['issues'] and all(matches.values())
    audit['evidence'] = {'actualGetterProofSha256': evidence['sha256'], 'staticOnly': True, 'httpBusinessVerified': False,
                         'getter': 'Unmodified assets.ts getShopItemSync/getUnprojectedShopItemSync/compatibility AST; real content-master and shop adapter'}
    return audit


def product_runtime_reviews(evidence_paths, repo, rules):
    """Two explicit source-HTTP rules only. Never clear economics or unrelated shop reviews."""
    coverage, receipts, frozen = defaultdict(set), {}, {}
    all_keys = sorted(rules['products'])
    daily_keys = sorted(key for key, rule in rules['products'].items() if rule['native']['daily_stock'] is not None)
    unique_keys = sorted(rules['summary']['equipmentOnlyPossessionOneKeys'])
    for evidence_path in evidence_paths:
        path = Path(evidence_path)
        data = load(path)
        if data.get('schemaVersion') != 1 or data.get('staticRuleStatus') != 'passed' or data.get('gameplayStatus') != 'actual_passed':
            raise ValueError('product transaction proof did not pass: ' + path.name)
        if path.name == 'root-event-shop-quota-audit.json':
            test = data['tests']
            if (data.get('status') != 'actual_passed' or test.get('total') != 7 or test.get('passed') != 7
                    or test.get('failed') != 0 or test.get('httpCases') != 6
                    or sorted(data['scope'].get('productKeys', [])) != all_keys
                    or sorted(data['scope'].get('dailyStockKeys', [])) != daily_keys
                    or data['scope'].get('monthlyStockKeys') != []):
                raise ValueError('daily quota proof scope differs from exact native products')
            name, keys, log, log_sha = 'daily_stock', daily_keys, Path(test['log']), test['logSha256']
            required = {'src/lib/shop-quota.ts', 'src/routes/api/shop.ts', 'src/routes/api/howToGet.ts',
                        'src/data/domains/shopPurchase.ts', 'src/lib/server-clock-state.ts', 'src/lib/persistence-coordinator.ts'}
        elif path.name == 'server-event-shop-ownership-audit.json':
            test = data['validation']['source']
            if (test.get('status') != 'actual_passed' or test.get('tests') != 6 or test.get('registeredHttpTests') != 5
                    or sorted(record['key'] for record in data.get('products', [])) != unique_keys
                    or any(record['parentKey'] != rules['products'][record['key']]['parentKey'] for record in data['products'])):
                raise ValueError('unique equipment proof scope differs from native flag-true products')
            name, keys, log, log_sha = 'equipment_unique_possession', unique_keys, Path(test['log']), test['logSha256']
            required = {'src/routes/api/shop.ts', 'src/lib/shop-quota.ts', 'src/lib/types/shop.ts'}
        else:
            raise ValueError('unsupported product runtime proof: ' + path.name)
        source_hashes = {record['path']: record['sha256'].lower() for record in data.get('sourceFreeze', [])}
        required.update({'src/lib/assets.ts', 'src/lib/content-shop-rules.ts', 'assets/content_history_shop_rules.json'})
        if not required <= set(source_hashes):
            raise ValueError('product transaction proof lacks consumed sources: ' + path.name)
        for relative, digest in source_hashes.items():
            target = (repo / relative).resolve()
            if not target.is_relative_to(repo) or not re.fullmatch('[a-f0-9]{64}', digest) or sha(target.read_bytes()) != digest:
                raise ValueError('product transaction proof source changed: ' + relative)
        if not log.resolve().is_relative_to(path.resolve().parent) or sha(log.read_bytes()) != log_sha.lower():
            raise ValueError('product transaction proof log changed: ' + path.name)
        frozen.update(source_hashes)
        coverage[name].update(keys)
        receipts[name] = {'file': path.name, 'sha256': sha(path.read_bytes()), 'keys': keys,
                          'sourceHashes': source_hashes, 'logSha256': log_sha.lower(),
                          'boundedStatus': 'source_registered_http_passed', 'deviceAcceptance': False}
    return coverage, receipts, frozen


def apply_product_runtime_reviews(audit, key, coverage, receipts):
    result = copy.deepcopy(audit)
    labels = {'daily_stock': '需要核对周期库存账本：daily_stock', 'equipment_unique_possession': '需要核对装备唯一持有规则'}
    cleared = []
    for rule, label in labels.items():
        if key in coverage.get(rule, set()) and label in result['review']:
            result['review'].remove(label)
            cleared.append(rule)
    result['reviewBeforeRuntimeEvidence'] = audit['review']
    result['boundedTransactionEvidence'] = [{name: receipts[rule][name] for name in ['file', 'sha256', 'logSha256', 'boundedStatus', 'deviceAcceptance']}
                                          for rule in cleared]
    result['status'] = 'mismatch' if result['issues'] else 'unreviewed' if result['review'] else 'verified_static'
    return result


def equivalent_definition_receipts(previous, current):
    return (previous.get('schemaVersion') == current.get('schemaVersion') == 1
            and previous.get('source', {}).get('catalogSha256') == current.get('source', {}).get('catalogSha256')
            and previous.get('source', {}).get('manifestSha256') == current.get('source', {}).get('manifestSha256')
            and previous.get('rows') == current.get('rows')
            and previous.get('existingEvidenceRebind') == current.get('existingEvidenceRebind'))


def native_entry_bridge_evidence(path, expected_keys, read_document):
    proof = read_document(path)
    if (proof.get('schemaVersion') != 1 or proof.get('helperBodies') != 74 or proof.get('runtimeAssertions', 0) < 113
            or sorted(row['key'] for row in proof.get('rows', [])) != sorted(expected_keys)):
        raise ValueError('controlled native entry proof differs from the exact missing-route set')
    records = {}
    for row in proof['rows']:
        runtime = read_document(row['runtimeProof'])
        imported = read_document(row['importReceipt'])
        parsed = read_document(row['parsedOutputProof'])
        if (not runtime.get('passed') or runtime.get('assertions', 0) < proof['runtimeAssertions']
                or runtime.get('assertions') != len(runtime.get('checks', [])) or runtime.get('productionInputsStable') is not True
                or runtime.get('sourceSwfSha256') != proof['candidateSwfSha256']
                or imported.get('sourceSwfSha256') != proof['candidateSwfSha256']
                or parsed.get('candidateSwfSha256') != proof['candidateSwfSha256']
                or runtime.get('productionHelperAbcSha256') != proof['candidateHelperAbcSha256']
                or row.get('candidateSwfSha256') != proof['candidateSwfSha256']
                or row.get('candidateHelperAbcSha256') != proof['candidateHelperAbcSha256']
                or imported.get('actualHelperBodies') != 74 or not imported.get('methods')
                or not all(method.get('normalizedInstructionsCfgExact') for method in imported['methods'])
                or parsed.get('productionHelperBytesMatchSwf') is not True
                or row.get('gameplayStatus') != 'unreviewed' or row.get('deviceTested') is not False
                or row.get('controlActions') != ['visible', 'enter'] or row.get('requiresBothActionsEnabled') is not True
                or not set(row['checks']) <= set(runtime['checks'])):
            raise ValueError('controlled entry proof failed candidate/source/guard binding: ' + row['key'])
        helper_label = 'cn.content::ContentOperationsState$/' + row['helperMethod'] + '|1'
        if helper_label not in {method['label'] for method in imported['methods']}:
            raise ValueError('controlled entry helper body missing: ' + row['key'])
        records[row['key']] = {**row, 'proofFile': Path(path).name, 'proofSha256': sha(Path(path).read_bytes()),
                               'platform': 'android_candidate', 'packaged': proof['packaged'], 'executedAssertionCount': runtime['assertions']}
    return records


def refresh_definition_loaders(args, repo, manifest_before):
    """Rebind existing native-reviewed receipts only if every semantic capture is unchanged."""
    if not args.definition_evidence or not args.evidence:
        raise ValueError('--refresh-definition-loaders requires existing --definition-evidence and --evidence')
    evidence_path = Path(args.definition_evidence)
    previous_bytes = evidence_path.read_bytes()
    previous = json.loads(previous_bytes)
    if previous.get('effectiveShopDefinitionEvidence') and not args.shop_getter_evidence:
        raise ValueError('adopted effective shop receipts require --shop-getter-evidence revalidation')
    catalog_bytes = (repo / 'assets/content_catalog.json').read_bytes()
    catalog = json.loads(catalog_bytes)
    catalog_sha = sha(catalog_bytes)
    if previous.get('schemaVersion') != 1 or previous.get('source', {}).get('catalogSha256') != catalog_sha:
        raise ValueError('existing native receipt catalog identity changed')
    original = {row['key']: row for row in catalog['rows']}
    product_keys = sorted(row['key'] for row in catalog['rows'] if row['type'] == 'event_item_shop') if args.shop_getter_evidence else []
    getter_evidence = validate_shop_getter_evidence(args.shop_getter_evidence, repo, product_keys) if product_keys else None
    keys = sorted(set(previous['rows']) | set(previous['existingEvidenceRebind']) | set(product_keys))
    captured = runtime_receipts(repo, [original[key] for key in keys], product_keys=product_keys)
    next_evidence = copy.deepcopy(previous)
    for key, old in previous['rows'].items():
        row, capture = original[key], captured['rows'].get(key)
        if (not capture or old.get('oldDefinitionMatched') is not True or old.get('key') != key
                or old.get('schemaVersion') != 1 or old.get('definitionDigest') != row['definitionDigest']
                or old.get('previousServerDefinitionDigest') != row['serverDefinitionDigest']
                or old.get('dependencyDigest') != capture['dependencyDigest']):
            raise ValueError('native reviewed receipt dependency changed: ' + key)
        next_evidence['rows'][key]['loaders'] = captured['loaderSets'][capture['loaderSetId']]
    for key, candidate in previous['existingEvidenceRebind'].items():
        row, capture = original[key], captured['rows'].get(key)
        field = 'exactDefinitionEvidence' if candidate['kind'] == 'exact' else 'currentParentDefinitionEvidence'
        prior = row.get(field)
        old_semantics = {name: value for name, value in candidate['evidence'].items() if name != 'loaders'}
        prior_semantics = {name: value for name, value in (prior or {}).items() if name != 'loaders'}
        if (not capture or candidate.get('nativeRowMatchesCatalog') is not True
                or candidate.get('dependencyDigestUnchanged') is not True or candidate['previousEvidence'] != prior
                or old_semantics != prior_semantics or prior['dependencyDigest'] != capture['dependencyDigest']):
            raise ValueError('existing precise receipt semantics changed: ' + key)
        loaders = captured['loaderSets'][capture['loaderSetId']]
        current = next_evidence['existingEvidenceRebind'][key]
        current['evidence'] = dict(prior, loaders=loaders)
        current['currentMatcherAfterLoaderRebind'] = captured['reboundMatches'].get(key)
        if not current['currentMatcherAfterLoaderRebind'] or current['currentMatcherAfterLoaderRebind']['matchesCatalog'] is not True:
            raise ValueError('fresh loader exact matcher rejected: ' + key)
        current['loaderChanges'] = {relative: {'previous': prior['loaders'].get(relative), 'current': loaders.get(relative)}
                                    for relative in sorted(set(prior['loaders']) | set(loaders)) if prior['loaders'].get(relative) != loaders.get(relative)}
    next_evidence['source']['runtimeLoaderSets'] = captured['loaderSets']
    for loaders in captured['loaderSets'].values():
        for relative, digest in loaders.items():
            next_evidence['source']['serverSources'][relative] = {'sha256': digest}
    effective_audits = {}
    if getter_evidence:
        rules = load(repo / 'assets/content_history_shop_rules.json')
        if rules['source']['catalogSha256'] != catalog_sha or rules['source']['manifestSha256'] != sha(manifest_before):
            raise ValueError('native shop rule source changed')
        inventory = load(repo / 'assets/content_history_readiness.json')
        if inventory['sourceSnapshot']['catalogSha256'] != catalog_sha:
            raise ValueError('legacy field audit catalog changed')
        for key in product_keys:
            row, rule, capture = original[key], rules['products'][key], captured['rows'][key]
            if rule['parentKey'] != row['parentKey'] or rule['source']['rowSha256'] != row['definitionDigest']:
                raise ValueError('native shop rule parent or row changed: ' + key)
            audit = effective_shop_field_audit(inventory['childIndex']['catalogChildren'][key]['fieldAudit'],
                                               rule['native'], rule['source']['raw'], captured['effectiveProducts'][key], getter_evidence)
            effective_audits[key] = audit
            if audit['definitionFieldsMatched']:
                next_evidence['rows'][key] = {'schemaVersion': 1, 'key': key, 'oldDefinitionMatched': True,
                    'definitionDigest': row['definitionDigest'], 'dependencyDigest': capture['dependencyDigest'],
                    'loaders': captured['loaderSets'][capture['loaderSetId']], 'previousServerDefinitionDigest': row['serverDefinitionDigest']}
        next_evidence['effectiveShopDefinitionEvidence'] = {'getterProof': getter_evidence,
            'rows': effective_audits, 'scope': 'Static effective definition equality; ledger and ownership reviews remain separate.'}
    matrix = runtime_receipts(repo, [], runtime_catalog=catalog, runtime_evidence=next_evidence,
                               runtime_keys=[row['key'] for row in catalog['rows']], runtime_details=True)
    blocked = sorted(key for key, value in matrix['runtimeDefinitions'].items() if value['matchesCatalog'] is not True)
    blocked_parents = [key for key in blocked if original[key]['type'] in PARENT_TYPES]
    if blocked_parents:
        raise ValueError('refreshed native runtime definition rejects parents: ' + ','.join(blocked_parents))
    if ((repo / 'assets/content_catalog.json').read_bytes() != catalog_bytes
            or (repo / 'assets/asset-patch/manifest.json').read_bytes() != manifest_before
            or evidence_path.read_bytes() != previous_bytes):
        raise ValueError('native receipt source changed during loader refresh')
    for loaders in captured['loaderSets'].values():
        if any(sha((repo / relative).read_bytes()) != digest for relative, digest in loaders.items()):
            raise ValueError('runtime loader changed during receipt refresh')
    if getter_evidence:
        for relative, digest in getter_evidence['sourceHashes'].items():
            if sha((repo / relative).read_bytes()) != digest:
                raise ValueError('actual shop getter input changed during receipt refresh: ' + relative)
    next_evidence['loaderRefresh'] = {'previousEvidenceSha256': sha(previous_bytes),
                                     'semanticDependenciesUnchanged': True,
                                     'reviewedReceiptCount': len(previous['rows']),
                                     'existingRebindCount': len(previous['existingEvidenceRebind']),
                                     'nextReviewedReceiptCount': len(next_evidence['rows'])}
    write(evidence_path, next_evidence)
    proof = {'schemaVersion': 1, 'source': {'catalogSha256': catalog_sha, 'manifestSha256': sha(manifest_before),
                                          'outputSha256': sha(evidence_path.read_bytes()),
                                          'runtimeLoaderSets': captured['loaderSets']},
             'loaderRefresh': next_evidence['loaderRefresh'], 'runtimeDefinitions': matrix['runtimeDefinitions'],
             'method': matrix['method'], 'summary': {'rows': len(catalog['rows']), 'blocked': len(blocked),
                'blockedTypeCounts': dict(Counter(original[key]['type'] for key in blocked))},
             'scope': 'Effective definition identities only; transaction readiness and gameplay status are unchanged.'}
    write(args.evidence, proof)
    print(json.dumps({'reviewedReceipts': len(next_evidence['rows']), 'existingRebind': len(previous['existingEvidenceRebind']),
                      'runtimeRows': len(matrix['runtimeDefinitions']), 'blockedTypeCounts': proof['summary']['blockedTypeCounts'],
                      'effectiveProductCounts': dict(Counter(audit['status'] for audit in effective_audits.values())),
                      'effectiveDefinitionMismatches': [key for key, audit in effective_audits.items() if not audit['definitionFieldsMatched']],
                      'outputSha256': proof['source']['outputSha256']}))


def audit_gacha(exporter, fields, definition, inputs, known_rewards):
    errors, resources, native_pool, rates = [], [], [], {}
    if definition is None:
        return {'status': 'missing', 'issues': ['服务端卡池定义缺失'], 'resources': []}
    weapon = fields[13] == '1'
    for index in ([11, 22, 23, 24] if weapon else [11, 14, 15, 16]):
        if fields[index] in ('', '(None)'):
            continue
        logical = 'master/gacha_odds/' + fields[index] + '.orderedmap'
        resources.append(logical)
        if logical not in inputs:
            errors.append('原生概率表缺失：' + logical)
            continue
        parsed = exporter.nested_rows(inputs[logical][0], logical, 2)
        values = [row[0] for inner in parsed.values() for row in inner.values()]
        if index == 11:
            rates = {int(row[0]): float(row[1]) for row in values}
        else:
            native_pool.extend((int(row[0]), int(row[1]), float(row[2])) for row in values)
    runtime_pool = [(int(row['id']), int(row['rank']), float(row['odds']))
                    for group in definition.get('pool', {}).values() for row in group]
    expected = dict(zip([5, 4, 3], definition.get('rankRates', {}).get('normal', [])))
    a, b = sum(rates.values()), sum(expected.values())
    if a <= 0 or b <= 0 or any(abs(rates.get(rank, 0) / a - expected.get(rank, 0) / b) > 1e-9
                              for rank in set(rates) | set(expected)):
        errors.append('原生与服务端标准稀有度概率不一致')
    if sorted(native_pool) != sorted(runtime_pool):
        errors.append('原生与服务端角色/装备及权重池不一致')
    for index, field, default in [(5, 'singleCost', 75 if weapon else 150),
                                  (6, 'multiCost', 750 if weapon else 1500),
                                  (7, 'discountCost', 25 if weapon else 50)]:
        if int(fields[index] or default) != definition.get(field):
            errors.append('原生与服务端抽取消耗不一致：' + field)
    for index, field in [(4, 'pageKind'), (10, 'guaranteeRarity'), (13, 'type')]:
        if int(fields[index]) != definition.get(field):
            errors.append('原生与服务端抽取规则字段不一致：' + field)
    for index, field in [(27, 'onceTicketItemId'), (28, 'tenTicketItemId')]:
        value = int(fields[index]) if fields[index].isdigit() else None
        if value != definition.get(field):
            errors.append('原生与服务端票券字段不一致：' + field)
    absent = sorted({ident for ident, _, _ in runtime_pool if str(ident) not in known_rewards})
    if absent:
        errors.append('服务端奖励角色/装备定义缺失')
    if any(weight < 0 for _, _, weight in runtime_pool):
        errors.append('抽取权重存在负值')
    return {'status': 'mismatch' if errors else 'verified_static', 'issues': errors, 'resources': resources,
            'nativeEntries': len(native_pool), 'serverEntries': len(runtime_pool), 'absentRewardIds': absent,
            'scope': 'Exact weighted pools, normalized standard rarity, declared costs/page kind/guarantee rarity/tickets and reward IDs; no simulated draw or account eligibility assertion.'}


def build_readiness(args, repo, resource_root, exporter, manifest_before):
    if (args.definition_evidence and Path(args.definition_evidence).is_file()
            and load(args.definition_evidence).get('effectiveShopDefinitionEvidence') and not args.shop_getter_evidence):
        raise ValueError('adopted effective shop receipts require --shop-getter-evidence revalidation')
    catalog_path, plan_path = repo / 'assets/content_catalog.json', repo / 'assets/content_july_controls.json'
    catalog_bytes, plan_bytes = catalog_path.read_bytes(), plan_path.read_bytes()
    catalog, plan = json.loads(catalog_bytes), json.loads(plan_bytes)
    original = {row['key']: row for row in catalog['rows']}
    parents = {key: row for key, row in original.items() if row['type'] in PARENT_TYPES}
    external, client_types, mission_observations, external_bytes = {}, {}, {}, {}
    bounded_runtime, runtime_rows, runtime_source_hashes, runtime_mission_observations = {}, {}, {}, {}
    collect_kind_rows = {}
    def read_external(path):
        raw = Path(path).read_bytes()
        external_bytes[str(path)] = raw
        return json.loads(raw)
    shop_getter_keys = sorted(row['key'] for row in catalog['rows'] if row['type'] == 'event_item_shop')
    shop_getter_proof = None
    shop_native_rules = None
    product_review_coverage, product_review_receipts = {}, {}
    if args.shop_getter_evidence:
        read_external(args.shop_getter_evidence)
        shop_getter_proof = validate_shop_getter_evidence(args.shop_getter_evidence, repo, shop_getter_keys)
        shop_native_rules = read_external(repo / 'assets/content_history_shop_rules.json')
        if (shop_native_rules['source']['catalogSha256'] != sha(catalog_bytes)
                or shop_native_rules['source']['manifestSha256'] != sha(manifest_before)
                or sorted(shop_native_rules['products']) != shop_getter_keys):
            raise ValueError('effective shop definition source differs from catalog/winning chain')
        external['shopGetterEvidence'] = shop_getter_proof
        runtime_source_hashes.update(shop_getter_proof['sourceHashes'])
    if args.product_runtime_evidence:
        if not shop_native_rules:
            raise ValueError('product transaction evidence requires actual --shop-getter-evidence')
        product_review_coverage, product_review_receipts, frozen = product_runtime_reviews(args.product_runtime_evidence, repo, shop_native_rules)
        runtime_source_hashes.update(frozen)
        for evidence_path in args.product_runtime_evidence:
            read_external(evidence_path)
        external['productTransactionEvidence'] = product_review_receipts
    quest_runtime_proof = read_external(args.quest_runtime_evidence) if args.quest_runtime_evidence else None
    collect_kind_evidence = read_external(args.collect_kind_evidence) if args.collect_kind_evidence else None
    if collect_kind_evidence:
        collect_kind_rows = {'collect_item_event:' + str(row['id']): row for row in collect_kind_evidence['rows']}
        external['collectKindEvidence'] = {'file': Path(args.collect_kind_evidence).name,
                                         'sha256': sha(external_bytes[str(args.collect_kind_evidence)]),
                                         'schema': 'CollectItemEventValues col3; kind1 EventTop opens native EventItemExchangeShop; MissionScene rejects3435'}
    if quest_runtime_proof:
        external['questRuntimeEvidence'] = {'file': Path(args.quest_runtime_evidence).name, 'sha256': sha(external_bytes[str(args.quest_runtime_evidence)])}
        if quest_runtime_proof.get('staticStatus') == 'passed':
            hashes = quest_runtime_proof.get('sourceHashes', {})
            required = {'src/lib/content-quest-rules.ts', 'src/routes/api/singleBattleQuest.ts',
                        'src/lib/quest/finish/single-finish-transaction.ts', 'src/lib/quest/finish/challenge-point.ts'}
            if not required <= set(hashes):
                raise ValueError('challenge-point runtime proof lacks critical sources')
            for relative, digest in hashes.items():
                if not re.fullmatch(r'src/[A-Za-z0-9_/-]+\.ts', relative) or '..' in relative or sha((repo / relative).read_bytes()) != digest:
                    raise ValueError('challenge-point runtime proof source mismatch: ' + relative)
            log = quest_runtime_proof.get('transactionTestLog', {})
            if Path(log.get('file', '')).name != log.get('file') or not log.get('file'):
                raise ValueError('challenge-point runtime proof test-log path invalid')
            log_path = Path(args.quest_runtime_evidence).parent / log['file']
            if sha(log_path.read_bytes()) != log.get('sha256'):
                raise ValueError('challenge-point runtime proof transaction log changed')
            external_bytes[str(log_path)] = log_path.read_bytes()
    for evidence_path in args.runtime_evidence:
        data = read_external(evidence_path)
        name = Path(evidence_path).name
        receipt_info = {'file': name, 'sha256': sha(external_bytes[str(evidence_path)]), 'scope': data.get('scope'),
                        'meaning': 'Bounded source/registered HTTP evidence only; no per-parent device or full gameplay acceptance'}
        source_mismatches, frozen_hashes = [], {}
        for frozen in data.get('sourceFreeze', []):
            relative, digest = frozen['path'], frozen['sha256'].lower()
            target = (repo / relative).resolve()
            if not target.is_relative_to(repo) or not re.fullmatch('[a-f0-9]{64}', digest):
                raise ValueError('invalid runtime source receipt: ' + relative)
            if sha(target.read_bytes()) != digest:
                source_mismatches.append(relative)
            frozen_hashes[relative] = digest
        receipt_info['sourceFreezeStatus'] = 'stale_source' if source_mismatches else 'matched' if frozen_hashes else 'not_supplied'
        receipt_info['sourceMismatches'] = source_mismatches
        if frozen_hashes and not source_mismatches:
            runtime_source_hashes.update(frozen_hashes)
        if data.get('rules', {}).get('ticket') == 999012 and 'validation' in data:
            receipt_info.update(validation=data['validation'], rules=data['rules'])
            runtime_rows.setdefault('gacha:100', []).append({'report': name, 'sourceFreezeStatus': receipt_info['sourceFreezeStatus'],
                'boundedStatus': data['validation'].get('source', {}).get('status'), 'scope': data.get('scope')})
        elif data.get('count') == 53 and isinstance(data.get('rows'), list) and len(data['rows']) == 53:
            receipt_info.update(groups=data.get('groups'), bounds=data.get('bounds'))
            for record in data['rows']:
                if record.get('key') not in parents or parents[record['key']]['type'] != 'gacha':
                    raise ValueError('runtime evidence parent outside native gacha catalog')
                runtime_rows.setdefault(record['key'], []).append({'report': name, 'boundedStatus': record.get('status'),
                    'newExecHttpStatus': record.get('newExecHttpStatus'), 'existingExchangeHttpStatus': record.get('existingExchangeHttpStatus'),
                    'sourceFreezeStatus': 'not_supplied', 'nativePageKind': record.get('nativePageKind')})
        elif data.get('native', {}).get('missionId') == 21030 and data['native'].get('eventId') == 3 and data['native'].get('pattern') == 69:
            native = data['native']
            if native.get('source') != 'assets/mission_active.json' or sha((repo / native['source']).read_bytes()) != native['sha256'].lower():
                raise ValueError('active69 native server input changed')
            native_rows = load(repo / native['source'])['21030']
            if len(native_rows) != 1:
                raise ValueError('ambiguous active69 native server row')
            native_row = native_rows[0]
            if int(native_row[native['kindColumn']]) != 2 or int(native_row[native['campaignColumn']]) != 2:
                raise ValueError('active69 exact original kind/campaign mismatch')
            receipt_info.update(validation=data.get('validation'), native=native, fact=data.get('fact'))
            runtime_rows.setdefault('active_mission_event:3', []).append({'report': name, 'sourceFreezeStatus': receipt_info['sourceFreezeStatus'],
                'boundedStatus': data.get('validation', {}).get('source', {}).get('status'), 'staticRuleStatus': data.get('staticRuleStatus')})
            if not source_mismatches and data.get('staticRuleStatus') == 'passed':
                runtime_source_hashes[native['source']] = native['sha256'].lower()
                runtime_mission_observations['0:21030'] = {'key': '0:21030', 'staticRuleStatus': 'passed',
                    'nativePatternType': 69, 'exactKind': 2, 'campaignId': 2, 'report': name,
                    'dynamicStatus': data.get('validation', {}).get('source', {}).get('status')}
        else:
            raise ValueError('unsupported bounded runtime evidence: ' + name)
        bounded_runtime[name] = receipt_info
        external['runtime:' + name] = {'file': name, 'sha256': receipt_info['sha256']}
    quest_schema = read_external(args.quest_schema) if args.quest_schema else None
    quest_reward_schema = read_external(args.quest_reward_schema) if args.quest_reward_schema else None
    entry_schema = read_external(args.entry_schema) if args.entry_schema else None
    for name, path in [('questSchema', args.quest_schema), ('questRewardSchema', args.quest_reward_schema), ('entrySchema', args.entry_schema), ('productSchema', args.product_schema)]:
        if path:
            read_external(path)
            external[name] = {'file': Path(path).name, 'sha256': sha(external_bytes[str(path)])}
    if args.client_audit:
        data = read_external(args.client_audit)
        if data.get('catalogParents') != len(parents):
            raise ValueError('client audit parent scope differs from this catalog')
        client_types = {row['type']: row for row in data['rows']}
        external['clientAudit'] = {'file': Path(args.client_audit).name, 'sha256': sha(external_bytes[str(args.client_audit)]),
                                   'sourceSwfSha256': data.get('sourceSwfSha256'), 'scope': data.get('testedMeaning'),
                                   'notProven': data.get('notProven')}
    if args.action_evidence:
        data = read_external(args.action_evidence)
        for typ in ['collect', 'active', 'pass']:
            for parent in data.get(typ, {}).get('rows', []):
                missions = parent.get('missions', [])
                if isinstance(missions, dict):
                    missions = [mission for group in missions.values() for mission in group]
                for mission in missions:
                    mission_observations[mission['key']] = mission
        external['actionEvidence'] = {'file': Path(args.action_evidence).name, 'sha256': sha(external_bytes[str(args.action_evidence)]),
                                      'scope': data.get('scope'), 'evidence': data.get('evidence')}
    mission_observations.update(runtime_mission_observations)
    if len(parents) != 1020:
        raise ValueError('parent catalog set changed; review the 1020-parent scope')
    wanted = {row['source'] for row in catalog['rows']}
    wanted.update(logical for row in catalog['rows'] for logical in row.get('definitionSources', []) if logical.endswith('.orderedmap'))
    wanted.update(exporter.EXTRA_LOGICALS)
    wanted.update(quest_specs(exporter))
    wanted.update(BATTLE_MASTERS)
    if quest_schema:
        wanted.update(record['logical'] for record in quest_schema['tables'].values())
    if quest_reward_schema:
        wanted.update(quest_reward_schema['logicalTables'].values())
    if entry_schema:
        wanted.update(record['logical'] for group in ['membershipTables', 'additionalTables'] for record in entry_schema[group])
    wanted.update([RAID_OVERALL, RAID_RANKING, RANKING_REWARD,
                   'master/quest/event/event_list.orderedmap', 'master/quest/event/side_story_event_list.orderedmap',
                   'master/item/item.orderedmap', 'master/item/equipment.orderedmap', 'master/character/character.orderedmap'])
    wanted.add('master/degree/degree.orderedmap')
    inputs, source = exporter.resolve(resource_root, sorted(wanted))
    bytes_read = sum(len(value[0]) for value in inputs.values())
    if bytes_read > 256 * 1024 * 1024:
        raise ValueError('master-only inventory exceeded its 256 MiB read budget')
    resources = {logical: dict(receipt(exporter, logical, identity), status='verified_static', bytes=len(raw))
                 for logical, (raw, identity) in inputs.items()}
    flat = {logical: exporter.parse_rows(inputs[logical][0], logical) for logical in {row['source'] for row in catalog['rows']} if logical in inputs}
    if collect_kind_evidence:
        logical = collect_kind_evidence['logical']
        identity = inputs[logical][1]
        if (collect_kind_evidence['manifestSha256'] != source['manifestSha256'] or
                any(identity[name] != collect_kind_evidence['winner'][name] for name in ['archive', 'sha256'])):
            raise ValueError('collect kind source differs from current winning chain')
    native_entry_rows = native_entries(exporter, inputs, entry_schema, parents, flat)
    native_bridges = {}
    if args.native_entry_bridge_evidence:
        missing = [key for key, value in native_entry_rows.items() if value['status'] == 'blocked_absent_original_route']
        native_bridges = native_entry_bridge_evidence(args.native_entry_bridge_evidence, missing, read_external)
        external['nativeEntryBridge'] = {'file': Path(args.native_entry_bridge_evidence).name,
            'sha256': sha(external_bytes[str(args.native_entry_bridge_evidence)]),
            'keys': sorted(native_bridges), 'scope': 'Candidate-specific native entry routes only; gameplay/device acceptance remains unreviewed.'}
    if args.entry_history_output:
        if not entry_schema:
            raise ValueError('--entry-history-output requires --entry-schema')
        history = prior_entry_references(exporter, resource_root, source, entry_schema, parents, flat, native_entry_rows)
        for key, records in history['parents'].items():
            native_entry_rows[key]['historicalMembershipReferences'] = records
        write(args.entry_history_output, history)
    fresh = copy.deepcopy(catalog['rows'])
    server_sources = exporter.bind_server(fresh, catalog['questMap'], repo)
    server_sources.update(exporter.bind_related_definitions(fresh, inputs, repo, {}))
    server_sources.update({relative: {'sha256': digest} for relative, digest in runtime_source_hashes.items()})
    current = {row['key']: row for row in fresh}
    quest_nodes, quest_parents, excluded = collect_quests(exporter, inputs, parents, catalog['questMap'], quest_schema)
    native_rules = native_quest_rules_document(quest_nodes, quest_schema, source, resources, external['questSchema'], excluded, sha(catalog_bytes)) if quest_schema else None
    if args.quest_rules:
        if not native_rules:
            raise ValueError('--quest-rules requires --quest-schema')
        if manifest_before != (repo / 'assets/asset-patch/manifest.json').read_bytes() or catalog_bytes != catalog_path.read_bytes():
            raise ValueError('native quest rules input changed during capture')
        old_rules_raw = Path(args.quest_rules).read_bytes() if Path(args.quest_rules).is_file() else None
        same_rules = old_rules_raw is not None and json.loads(old_rules_raw) == native_rules
        if quest_runtime_proof and quest_runtime_proof.get('staticStatus') == 'passed' and (not same_rules or quest_runtime_proof.get('rulesSha256') != sha(old_rules_raw)):
            raise ValueError('challenge-point proof native rules changed')
        # CDN lookup visits ZIP members through sets. Canonicalize resource order for
        # new artifacts, but retain an identical existing document and its receipt.
        if not same_rules:
            write(args.quest_rules, native_rules)
        if args.quest_rules_only:
            print(json.dumps({'questRules': str(args.quest_rules), 'quests': len(native_rules['quests']),
                              'sha256': sha(Path(args.quest_rules).read_bytes()), 'scope': 'Native data only; no readiness/receipt refresh'}))
            return
    terrain_logicals = sorted({logical for node in quest_nodes.values() for scene in node['battleReferences']['scenes']
                              for logical in scene['terrainLogicals']})
    terrains, terrain_source = exporter.resolve(resource_root, terrain_logicals)
    if terrain_source['manifestSha256'] != source['manifestSha256']:
        raise ValueError('terrain dependency chain changed during capture')
    terrain_failures = {}
    for logical in terrain_logicals:
        if logical not in terrains:
            resources[logical] = {'status': 'missing'}
            terrain_failures[logical] = 'actual winning-chain member absent'
            continue
        raw, identity = terrains[logical]
        syntax = 'unreviewed'
        try:
            decoded = zlib.decompress(raw, -15)
            reader = exporter.core.AMF3Reader(decoded)
            reader.read_value()
            if reader.pos != len(decoded):
                raise ValueError('trailing AMF3 bytes')
            syntax = 'decoded_amf3'
        except Exception as error:
            terrain_failures[logical] = str(error)
        resources[logical] = dict(receipt(exporter, logical, identity), status='present', bytes=len(raw),
                                  syntax=syntax, semanticStatus='unreviewed')
    bytes_read += sum(len(value[0]) for value in terrains.values())
    if bytes_read > 256 * 1024 * 1024:
        raise ValueError('master/terrain inventory exceeded its 256 MiB read budget')
    mission_nodes, mission_parents = collect_missions(exporter, inputs, catalog)
    for key, node in mission_nodes.items():
        if key in mission_observations:
            node['sourceRuleObservation'] = dict(mission_observations[key])
            if node.get('ruleDecision'):
                node['sourceRuleObservation']['supersededByCurrentRuleDecision'] = True
    quest_collisions = {key: row['parents'] for key, row in quest_nodes.items() if len(row['parents']) > 1}
    quest_disagreements = {key: row for key, row in quest_nodes.items() if row['catalogOwner'] not in row['parents']}
    mission_disagreements = {key: row for key, row in mission_nodes.items() if not row['catalogOwnerMatches']}
    controls = {row['key']: row for row in plan['controls']}
    parent_products = defaultdict(list)
    for row in catalog['rows']:
        if row.get('parentKey'):
            parent_products[row['parentKey']].append(row['key'])
    presentation = load(repo / 'assets/content_presentation.json')
    same_image_chain = presentation['source']['manifestSha256'] == source['manifestSha256']
    if same_image_chain:
        for logical, value in presentation['resources'].items():
            resources.setdefault(logical, dict(value, status='verified_receipt_same_chain', reusedWithoutImageDecode=True))
    tables, _server_resources, gachas, _winners = exporter.server_definitions(repo)
    reward_definitions = {'clear': load(repo / 'assets/clear_reward.json'),
                           'score': {**load(repo / 'assets/score_reward.json'), **load(repo / 'assets/score_reward_cnmod.json')},
                           'rare': {**load(repo / 'assets/rare_score_reward.json'), **load(repo / 'assets/rare_score_reward_cnmod.json')}}
    quest_rewards = {}
    for key, node in quest_nodes.items():
        relative = 'assets/' + exporter.QUEST_FILES[node['category']] + '.json'
        value = tables.get(relative, {}).get(str(node['questId']))
        node['serverDefinition'] = {'source': relative, 'present': value is not None, 'rowSha256': exporter.json_sha(value)}
        if 'nativeProjection' in node:
            differences = [{'field': name, 'native': expected, 'server': value.get(name) if value else None}
                           for name, expected in node['nativeProjection'].items() if (value.get(name) if value else None) != expected]
            node['serverFieldParity'] = {'status': 'mismatch' if differences else 'passed', 'differences': differences,
                                         'scope': 'Native original generated Values columns; inactive Story battle columns deliberately excluded.'}
        refs = []
        if value:
            for field, kind in [('clearRewardId', 'clear'), ('sPlusRewardId', 'clear'), ('scoreRewardGroupId', 'score')]:
                if value.get(field) is None:
                    continue
                ident = str(value[field]); dependency = kind + ':' + ident
                selected = reward_definitions[kind].get(ident)
                quest_rewards[dependency] = {'key': dependency, 'kind': kind, 'id': int(ident),
                                             'present': selected is not None, 'rowSha256': exporter.json_sha(selected),
                                             'nativeServerParity': 'unreviewed'}
                refs.append(dependency)
                if kind == 'score' and selected:
                    for reward in selected:
                        if reward.get('type') == 1:
                            rare_id = str(reward['id']); rare_key = 'rare:' + rare_id
                            rare = reward_definitions['rare'].get(rare_id)
                            quest_rewards[rare_key] = {'key': rare_key, 'kind': 'rare', 'id': int(rare_id),
                                                      'present': rare is not None, 'rowSha256': exporter.json_sha(rare),
                                                      'nativeServerParity': 'unreviewed'}
                            refs.append(rare_key)
            node['scalarRewards'] = {name: value[name] for name in ['rankPointReward', 'characterExpReward', 'manaReward', 'poolExpReward'] if name in value}
        node['rewardDependencyKeys'] = sorted(set(refs))
    extra_fields = extra_consumed_field_audit(exporter, inputs, quest_schema, quest_nodes, tables,
                                              load(repo / 'assets/quest_entry_costs.json')) if quest_schema else {}
    server_sources['assets/quest_entry_costs.json'] = {'sha256': sha((repo / 'assets/quest_entry_costs.json').read_bytes())}
    server_sources['src/lib/stamina-cost.ts'] = {'sha256': sha((repo / 'src/lib/stamina-cost.ts').read_bytes())}
    for key, value in extra_fields.items():
        quest_nodes[key]['additionalConsumedFieldAudit'] = value
    daily_keys = sorted(key for key, value in extra_fields.items() if value['nativeClientOwnedScalars'].get('daily_challenge_point_id') is not None)
    daily_wiring_passed = bool(quest_runtime_proof and quest_runtime_proof.get('staticStatus') == 'passed' and sorted(quest_runtime_proof.get('questKeys', [])) == daily_keys)
    if quest_runtime_proof and quest_runtime_proof.get('staticStatus') == 'passed' and not daily_wiring_passed:
        raise ValueError('challenge-point runtime proof does not cover the exact native quest set')
    if daily_wiring_passed:
        server_sources.update({relative: {'sha256': digest} for relative, digest in quest_runtime_proof['sourceHashes'].items()})
    challenge_lookup_path = repo / 'assets/daily_challenge_point_lookup.json'
    challenge_lookup = load(challenge_lookup_path)
    if daily_wiring_passed and quest_runtime_proof.get('lookupSha256') != sha(challenge_lookup_path.read_bytes()):
        raise ValueError('challenge-point proof existing lookup changed')
    server_sources['assets/daily_challenge_point_lookup.json'] = {'sha256': sha(challenge_lookup_path.read_bytes())}
    for key in daily_keys:
        point_id = extra_fields[key]['nativeClientOwnedScalars']['daily_challenge_point_id']
        lookup = challenge_lookup.get(str(point_id))
        if not lookup:
            raise ValueError('native challenge-point ID lacks existing server lookup: ' + key)
        quest_nodes[key]['challengePointRule'] = {'pointId': point_id, 'source': 'Native QuestValues column128 daily_challenge_point_id',
                'existingServerLookup': {name: lookup[name] for name in ['maxPoint', 'isRecovery']},
                'lookupNativeFieldParity': 'not_independently_verified; retained existing server values',
                'staticWiringStatus': 'passed' if daily_wiring_passed else 'unreviewed',
                'ruleDecision': {'consumeAfterSuccessfulCompletion': 1, 'failureRetryAllowed': True,
                                 'preserveExistingPlayerRemainingPoints': True, 'retroactiveConsumption': False,
                                 'preserveExistingExpertFailureConsumption': True, 'officialDeductionTimingVerified': False}}
    characters = {**load(repo / 'assets/character.json'), **load(repo / 'assets/character_rank_p5b.json')}
    equipment = load(repo / 'assets/equipment_max_level.json')
    item_ids = {str(value) for name in ['item_ids', 'item_ids_rank_p5b'] for value in load(repo / ('assets/' + name + '.json'))}
    degrees = {}
    for name in ['degree', 'degree_rank_p5b', 'degree_sponsor', 'degree_character_mod', 'degree_exclusive', 'degree_author926']:
        degrees.update(load(repo / ('assets/' + name + '.json')))
    reward_native_tables = {kind: exporter.parse_rows(inputs[logical][0], logical)
                            for kind, logical in [(0, 'master/item/item.orderedmap'), (3, 'master/character/character.orderedmap'),
                                                  (4, 'master/item/equipment.orderedmap'), (5, 'master/degree/degree.orderedmap')]
                            if logical in inputs}
    reward_server_ids = {0: item_ids, 3: set(characters), 4: set(equipment), 5: set(degrees)}
    for name in ['item_ids', 'item_ids_rank_p5b', 'character', 'character_rank_p5b', 'equipment_max_level',
                 'degree', 'degree_rank_p5b', 'degree_sponsor', 'degree_character_mod', 'degree_exclusive', 'degree_author926',
                 'clear_reward', 'score_reward', 'score_reward_cnmod', 'rare_score_reward', 'rare_score_reward_cnmod']:
        relative = 'assets/' + name + '.json'
        server_sources[relative] = {'sha256': sha((repo / relative).read_bytes())}
    shop_tables = server_shop_tables(repo)
    current_only_children = {}
    for typ, _directory, name_col, start_col, end_col, _exchange_col, _categories in exporter.TABLES:
        if not typ.endswith('_shop'):
            continue
        example = next(row for row in catalog['rows'] if row['type'] == typ)
        logical = example['source']
        for ident, values in flat.get(logical, {}).items():
            key = typ + ':' + ident
            if key in original:
                continue
            fields = values[0]
            parent = None
            if typ == 'event_item_shop':
                parent_type = {0: 'advent_event', 1: 'story_event', 2: 'world_story_event', 3: 'challenge_dungeon_event',
                               4: 'collect_item_event', 5: 'carnival_event', 6: 'rush_event', 7: 'score_attack_event'}.get(int(fields[0]))
                parent = parent_type + ':' + fields[1] if parent_type else None
                if parent in parents:
                    parent_products[parent].append(key)
            current_only_children[key] = {'key': key, 'type': typ, 'title': fields[name_col], 'parentKey': parent,
                                           'source': logical, 'rowSha256': exporter.json_sha(fields), 'catalogPresent': False,
                                           'originalStartMs': exporter.timestamp(fields[start_col]),
                                           'originalEndMs': exporter.timestamp(fields[end_col]),
                                           'staticStatus': 'blocked_absent_catalog',
                                           'blockers': [blocker('current_child_not_in_catalog', '当前获胜链新增成员尚未登记到目录；不能随父项自动开放')]}
    schemas, prior_products = product_schema(args.product_schema)
    products = [row for row in catalog['rows'] if row['type'].endswith('_shop')]
    for relative in ['src/lib/box-gacha-policy.ts', 'src/lib/content-definition-evidence.ts', 'src/lib/exchange-campaign-definitions.ts',
                     'src/lib/mission/rewards.ts', 'src/lib/mission/grants.ts', 'src/lib/mission/awake-master-assets.ts', 'src/lib/types/box-gacha.ts', 'src/lib/gacha.ts']:
        server_sources[relative] = {'sha256': sha((repo / relative).read_bytes())}
    adapter = repo / 'src/lib/content-quest-rules.ts'
    if adapter.exists():
        for relative in ['src/lib/content-quest-rules.ts', 'assets/content_history_quest_rules.json']:
            server_sources[relative] = {'sha256': sha((repo / relative).read_bytes())}
    quest_inputs = {key: {'category': node['category'], 'questId': node['questId'],
                          'definition': tables[node['serverDefinition']['source']].get(str(node['questId']))} for key, node in quest_nodes.items()}
    captured = runtime_receipts(repo, products + list(parents.values()), mission_nodes, quest_inputs,
                                product_keys=shop_getter_keys if shop_getter_proof else [])
    for key, node in quest_nodes.items():
        effective = captured['effectiveQuests'].get(key)
        if effective is not None and node.get('nativeProjection') is not None:
            priority = native_rules['quests'][key]['currentOverlayPriorityFields']
            differences = [{'field': name, 'native': expected, 'effectiveServer': effective.get(name)}
                           for name, expected in node['nativeProjection'].items() if name not in priority and effective.get(name) != expected]
            node['effectiveServerFieldParity'] = {'status': 'mismatch' if differences else 'passed', 'differences': differences,
                                                   'preservedCurrentOverlayFields': priority,
                                                   'source': 'src/lib/content-quest-rules.ts actual pure applyContentQuestRules'}
            node['effectiveServerDefinition'] = effective
            if key in extra_fields:
                additional = extra_fields[key]
                additional['effectiveServerDifferences'] = [{'field': name, 'native': expected, 'effectiveServer': effective.get(name)}
                                                           for name, expected in additional['nativeFields'].items() if effective.get(name) != expected]
                nominal = additional['nominalStamina']
                nominal['effective'] = captured['staminaCosts'].get(key)
                nominal['nativeGetterValue'] = captured['nativeStaminaCosts'].get(key)
                nominal['effectiveMatches'] = (nominal['native'] or 0) == nominal['effective'].get('baseCost')
                nominal['effectiveAuditScope'] = 'Actual getStaminaCost base-cost execution; campaign rate fixed at one and clock stubbed, no DB imports or player writes.'
    if quest_reward_schema:
        quest_rewards = native_quest_reward_members(exporter, inputs, quest_reward_schema, quest_nodes, reward_definitions,
                                                     reward_native_tables, reward_server_ids,
                                                     {'score': load(repo / 'assets/score_reward_cnmod.json'),
                                                      'rare': load(repo / 'assets/rare_score_reward_cnmod.json')})
    for key, node in mission_nodes.items():
        parity = current.get(node['parentKey'], {}).get('definitionEvidence', {}).get('status') == 'matched'
        node['nativeServerParity'] = 'passed' if parity else 'unreviewed'
        parsed = captured['missionRewards'].get(key, {})
        node['rewardStaticAudit'] = {stage: {**mission_reward_checks(value, reward_native_tables, reward_server_ids, node['parentKey']),
                                           'parsedDefinition': value} for stage, value in parsed.items()}
        node['rewardSemantics'] = 'passed' if parity and node['rewardStages'] and len(parsed) == len(node['rewardStages']) and all(
            value['status'] == 'passed' for value in node['rewardStaticAudit'].values()) else 'unreviewed'
        node['ruleSupport'] = source_rule_status(node.get('sourceRuleObservation'))
        if node.get('ruleDecision', {}).get('mode') == 'successful_rescue_finish_once' and node['ruleSupport'] == 'passed':
            node['ruleDecision']['implementationVerification'] = 'passed_static_source_evidence'
        if node.get('ruleDecision', {}).get('mode') == 'campaign2_final_character_exchange_once' and node['ruleSupport'] == 'passed':
            node['ruleDecision']['implementationVerification'] = 'passed_static_source_evidence'
        if node['parentKey'] == 'active_mission_event:150':
            node['ruleSupport'] = 'deferred_by_decision'
    children, exact_receipts = {}, {}
    for row in catalog['rows']:
        if row['key'] in parents:
            continue
        key, typ, ident = row['key'], row['type'], str(row['id'])
        raw = flat.get(row['source'], {}).get(ident)
        native_matches = bool(raw and len(raw) == 1 and exporter.json_sha(raw[0]) == row['definitionDigest'])
        child = {'key': key, 'type': typ, 'parentKey': row.get('parentKey'), 'source': row['source'],
                 'nativeRowMatchesCatalog': native_matches, 'catalogDefinitionStatus': row.get('definitionEvidence', {}).get('status'),
                 'currentDefinitionStatus': current[key].get('definitionEvidence', {}).get('status'), 'gameplayStatus': 'unreviewed'}
        if typ.endswith('_shop'):
            value = server_product(row, shop_tables)
            audit = audit_product(row, raw[0] if raw else None, value, schemas.get(typ), prior_products)
            if value:
                for field, actual in [('startDate', 'availableFrom'), ('endDate', 'availableUntil')]:
                    expected = row['originalStartMs'] if field == 'startDate' else row['originalEndMs']
                    audit['matches'][field] = exporter.timestamp(value.get(actual)) == expected
                    if not audit['matches'][field]:
                        audit['issues'].append('原生与服务端商品日期不一致：' + field)
                if typ == 'event_item_shop':
                    mapping = shop_tables['eventMap'].get(ident)
                    client_kind = {0: 0, 1: 2, 2: 6, 3: 4, 4: 9, 5: 10, 6: 11, 7: 12}.get(int(raw[0][0])) if raw else None
                    audit['matches']['parentMapping'] = bool(mapping and raw and client_kind == mapping['eventType'] and raw[0][1] == str(mapping['eventId']))
                    if not audit['matches']['parentMapping']:
                        audit['issues'].append('原生与服务端商品父项映射不一致')
            if audit['issues']:
                audit['status'] = 'mismatch' if value and raw else 'missing'
            references = [(0, cost['id']) for cost in audit.get('nativeCosts', [])]
            references += [(reward['type'], reward['id']) for reward in audit.get('nativeRewards', []) if 'id' in reward]
            audit['referenceChecks'] = []
            for kind, reward_id in references:
                native_reference = reward_native_tables.get(kind, {}).get(str(reward_id))
                exists = native_reference is not None and str(reward_id) in reward_server_ids.get(kind, set())
                audit['referenceChecks'].append({'kind': kind, 'id': reward_id, 'nativeAndServerPresent': exists,
                                                'nativeRowSha256': exporter.json_sha(native_reference) if native_reference is not None else None})
                if not exists:
                    audit['issues'].append('原生或服务端收费/奖励定义缺失：' + str(kind) + ':' + str(reward_id))
                    audit['status'] = 'missing'
            child['fieldAudit'] = audit
            if shop_getter_proof and key in shop_native_rules['products']:
                rule = shop_native_rules['products'][key]
                if rule['parentKey'] != row['parentKey'] or rule['source']['rowSha256'] != row['definitionDigest']:
                    raise ValueError('effective shop definition row identity changed: ' + key)
                audit = effective_shop_field_audit(audit, rule['native'], rule['source']['raw'], captured['effectiveProducts'][key], shop_getter_proof)
                if product_review_receipts:
                    audit = apply_product_runtime_reviews(audit, key, product_review_coverage, product_review_receipts)
                child['effectiveFieldAudit'] = audit
            child['preciseDependencyCapture'] = captured['rows'].get(key)
            child['existingDefinitionEvidenceMatch'] = captured['existingMatches'].get(key)
            receipt_eligible = audit.get('definitionFieldsMatched') if child.get('effectiveFieldAudit') else audit['status'] == 'verified_static'
            if native_matches and receipt_eligible and row.get('definitionEvidence', {}).get('status') == 'matched' and key in captured['rows']:
                capture = captured['rows'][key]
                exact_receipts[key] = {'schemaVersion': 1, 'key': key, 'oldDefinitionMatched': True,
                                       'definitionDigest': row['definitionDigest'], 'dependencyDigest': capture['dependencyDigest'],
                                       'loaders': captured['loaderSets'][capture['loaderSetId']],
                                       'previousServerDefinitionDigest': row['serverDefinitionDigest']}
            child['staticStatus'] = audit['status'] if native_matches else 'mismatch'
        else:
            child['staticStatus'] = 'unreviewed'
        children[key] = child
    existing_rebind = {}
    for key, old in original.items():
        prior = old.get('exactDefinitionEvidence') or old.get('currentParentDefinitionEvidence')
        capture = captured['rows'].get(key)
        native = flat.get(old['source'], {}).get(str(old['id']))
        native_matches = bool(native and len(native) == 1 and exporter.json_sha(native[0]) == old['definitionDigest'])
        if not prior or not capture or not native_matches:
            continue
        if (prior.get('schemaVersion') != 1 or prior.get('key') != key or prior.get('definitionDigest') != old['definitionDigest']
                or prior.get('previousServerDefinitionDigest') != old['serverDefinitionDigest']
                or prior.get('dependencyDigest') != capture['dependencyDigest']
                or not re.fullmatch('[a-f0-9]{64}', prior.get('dependencyDigest', ''))
                or not prior.get('loaders') or not all(re.fullmatch('[a-f0-9]{64}', value) for value in prior['loaders'].values())
                or (old.get('exactDefinitionEvidence') and prior.get('oldDefinitionMatched') is not True)):
            continue
        loaders = captured['loaderSets'][capture['loaderSetId']]
        if loaders == prior['loaders']:
            continue
        replacement = dict(prior, loaders=loaders)
        existing_rebind[key] = {'kind': 'exact' if old.get('exactDefinitionEvidence') else 'currentParent',
                                'previousEvidence': prior, 'evidence': replacement, 'nativeRowMatchesCatalog': True,
                                'dependencyDigestUnchanged': True,
                                'currentMatcherAfterLoaderRebind': captured['reboundMatches'].get(key),
                                'loaderChanges': {relative: {'previous': prior['loaders'].get(relative), 'current': loaders.get(relative)}
                                                  for relative in sorted(set(prior['loaders']) | set(loaders)) if prior['loaders'].get(relative) != loaders.get(relative)},
                                'status': 'candidate_requires_reviewed_loader_transition'}
    box_stages, box_rewards, parent_stages = {}, {}, defaultdict(list)
    raw_boxes = exporter.nested_rows(inputs['master/box_gacha/box.orderedmap'][0], 'box', 2)
    raw_rewards = exporter.nested_rows(inputs['master/box_gacha/box_reward.orderedmap'][0], 'box_reward', 3)
    for event, stages in raw_boxes.items():
        for stage, values in stages.items():
            key = 'box:' + event + ':' + stage
            parent_stages['box_gacha:' + event].append(key)
            box_stages[key] = {'key': key, 'parentKey': 'box_gacha:' + event, 'stage': stage,
                               'rowSha256': exporter.json_sha(values), 'rewardKeys': [],
                               'nativeRules': current.get('box_gacha:' + event, {}).get('boxRules', {}).get(stage)}
            for reward, value in raw_rewards.get(event, {}).get(stage, {}).items():
                reward_key = key + ':' + reward
                box_stages[key]['rewardKeys'].append(reward_key)
                box_rewards[reward_key] = {'key': reward_key, 'parentKey': 'box_gacha:' + event,
                                           'boxKey': key, 'rowSha256': exporter.json_sha(value), 'rewardSemantics': 'unreviewed'}
                native = value[0]
                projected = {'type': int(native[2]), 'id': int(native[3]) if native[3].isdigit() else None,
                             'count': int(native[4]), 'available': int(native[5]), 'tier': int(native[6])}
                box_rewards[reward_key]['nativeReward'] = projected
                kind = {0: 0, 1: 4, 6: 3}.get(projected['type'])
                if kind is not None:
                    ident = str(projected['id'])
                    box_rewards[reward_key]['referencedDefinitionPresent'] = ident in reward_native_tables.get(kind, {}) and ident in reward_server_ids[kind]
                box_rewards[reward_key]['rewardSemantics'] = 'passed' if projected['type'] in [0, 1, 2, 3, 4, 6] and projected['count'] >= 0 and projected['available'] >= 0 and projected['tier'] in range(3) and box_rewards[reward_key].get('referencedDefinitionPresent', True) else 'blocked'
    pass_rewards = {}
    pass_logical = 'master/pass_card/pass_card_reward.orderedmap'
    for ident, values in exporter.parse_rows(inputs[pass_logical][0], pass_logical).items():
        parent = 'pass_card_event:' + values[0][0]
        pass_rewards['pass_reward:' + ident] = {'key': 'pass_reward:' + ident, 'parentKey': parent, 'source': pass_logical,
                                                'rowSha256': exporter.json_sha(values), 'rewardSemantics': 'unreviewed'}
        parsed = captured['passRewards'].get(ident)
        audit = mission_reward_checks({'rewards': [parsed['reward1'], parsed['reward2']]} if parsed else None,
                                      reward_native_tables, reward_server_ids, parent)
        pass_rewards['pass_reward:' + ident].update(parsedDefinition=parsed, rewardStaticAudit=audit,
                                                   rewardSemantics=audit['status'] if current[parent]['definitionEvidence']['status'] == 'matched' else 'unreviewed')
    rows, page_counts, parent_receipts = [], Counter(), {}
    parent_boxes, box_routes = defaultdict(list), defaultdict(list)
    for parent, record in parents.items():
        index = 18 if record['type'] == 'raid_event' else 14 if record['type'] == 'world_story_event' else None
        if index is None:
            continue
        values = flat.get(record['source'], {}).get(str(record['id']))
        if values and values[0][index].isdigit() and 'box_gacha:' + values[0][index] in parents:
            box_key = 'box_gacha:' + values[0][index]
            parent_boxes[parent].append(box_key)
            box_routes[box_key].append({'parentKey': parent, 'source': record['source'], 'fieldIndex': index})
    for key, old in parents.items():
        typ, ident = old['type'], str(old['id'])
        row = current[key]
        native_values = flat.get(old['source'], {}).get(ident)
        native = native_values[0] if native_values and len(native_values) == 1 else None
        native_matches = bool(native and exporter.json_sha(native) == old['definitionDigest'])
        current_definition = row.get('definitionEvidence', {})
        campaign_parity = captured['campaigns'].get(key)
        if campaign_parity and campaign_parity['matchesCatalog']:
            current_definition = {'status': 'matched', 'issues': [], 'scope': 'Exact current native campaign masters and runtime campaign definition receipt'}
        definition_status = current_definition.get('status', 'unsupported')
        dated_only = typ == 'gacha' and set(current_definition.get('issues', [])) <= {'startDate differs', 'endDate differs'}
        definition_ok = native_matches and (definition_status == 'matched' or dated_only)
        if typ == 'active_mission_event' and native_matches and definition_status == 'matched' and key in captured['rows']:
            capture = captured['rows'][key]
            parent_receipts[key] = {'schemaVersion': 1, 'key': key, 'oldDefinitionMatched': True,
                                   'definitionDigest': old['definitionDigest'], 'dependencyDigest': capture['dependencyDigest'],
                                   'loaders': captured['loaderSets'][capture['loaderSetId']], 'previousServerDefinitionDigest': old['serverDefinitionDigest']}
        dependencies = {'questKeys': sorted(quest_parents.get(key, [])), 'missionKeys': sorted(mission_parents.get(key, [])),
                        'productKeys': sorted(parent_products.get(key, [])), 'boxStageKeys': sorted(parent_stages.get(key, [])),
                        'resourceLogicals': sorted(set(row.get('definitionSources', [])))}
        dependencies['missionRelations'] = {member: mission_nodes[member]['relation'] for member in dependencies['missionKeys']}
        dependencies['boxGachaKeys'] = sorted(parent_boxes.get(key, []))
        dependencies['passRewardKeys'] = sorted(member for member, value in pass_rewards.items() if value['parentKey'] == key)
        dependencies['currentOnlyProductKeys'] = [member for member in dependencies['productKeys'] if member in current_only_children]
        dependencies['challengePointQuestKeys'] = [member for member in dependencies['questKeys'] if member in daily_keys]
        dependencies['challengePointIds'] = sorted({quest_nodes[member]['challengePointRule']['pointId'] for member in dependencies['challengePointQuestKeys']})
        collect_shop_only = key in collect_kind_rows
        if collect_shop_only:
            expected = collect_kind_rows[key]
            if not native or native[3] != '1' or exporter.json_sha(native) != expected['rowSha256'] or dependencies['missionKeys'] or len(dependencies['productKeys']) != expected['nativeShopProducts']:
                raise ValueError('collect shop-only native membership changed: ' + key)
        actions = {action: {'status': 'not_applicable', 'blockers': []} for action in ['visible', 'enter', 'claim', 'exchange']}
        supported = ['visible', 'enter']
        if dependencies['productKeys'] or typ == 'gacha' or typ.endswith('_campaign'):
            supported.append('exchange')
        if typ in ['active_mission_event', 'collect_item_event', 'pass_card_event', 'box_gacha', 'rush_event', 'ranking_event']:
            supported.append('claim')
        base_blockers = []
        if not native_matches:
            base_blockers.append(blocker('native_parent_changed', '当前原生父定义缺失或与目录不一致', source=old['source']))
        if not definition_ok:
            base_blockers.append(blocker('server_definition_not_closed', '服务端定义尚未与当前原生定义闭合', details=current_definition))
        constraints = {'required': False, 'rules': [], 'catalogPersonalWindow': old.get('personalWindow', False)}
        exclusive = 'pass-card-active-period' if typ == 'pass_card_event' else None
        gacha_audit = None
        if typ == 'gacha' and native:
            kind = int(native[4]); page_counts[str(kind)] += 1
            for observation in runtime_rows.get(key, []):
                if observation.get('nativePageKind') is not None and observation['nativePageKind'] != kind:
                    raise ValueError('runtime gacha page-kind evidence differs from current native row: ' + key)
            constraints.update(pageKind=kind, required=kind not in [0, 8] or old.get('personalWindow', False))
            constraints['nativeComebackFlag'] = native[43].lower() == 'true'
            constraints['nativeStarsFlag'] = native[46].lower() == 'true'
            constraints['personalTimeWindowRequired'] = constraints['nativeComebackFlag'] or constraints['nativeStarsFlag']
            constraints['onceTicketItemId'] = int(native[27]) if native[27].isdigit() else None
            constraints['tenTicketItemId'] = int(native[28]) if native[28].isdigit() else None
            constraints['qualificationKind'] = 'account_once_ten' if kind == 1 else 'fixed_native_ticket' if kind in [2, 3, 4, 5] else 'native_personal_option_window' if constraints['personalTimeWindowRequired'] else 'ordinary'
            if kind == 5:
                constraints['nativeCrazyTenTimesTicketItemId'] = int(native[45]) if native[45].isdigit() else None
                constraints['ticketEvidence'] = {'source': old['source'], 'column': 45, 'meaning': 'crazy_ten_times_ticket_item_id; qualification only, not consumption timing'}
                supported.append('claim')
            constraints['required'] = constraints['required'] or constraints['nativeComebackFlag'] or constraints['nativeStarsFlag']
            constraints['rules'] = (['原生单账号十连次数与既有记录'] if kind == 1 else
                                    ['原生专用票券与账号资格'] if kind in [2, 3, 4, 5] else
                                    ['原生未实现页面类型，不得整体启用'] if kind in [6, 7] else ['原有支付、票券、折扣和抽取记录'])
            if constraints['nativeComebackFlag']:
                constraints['rules'].append('原生回归资格与个人有效窗')
            if constraints['nativeStarsFlag']:
                constraints['rules'].append('原生星辰池个人资格与既有次数')
            if kind in [6, 7]:
                base_blockers.append(blocker('native_gacha_page_unimplemented', '原生页面本身未实现（C9100 / PINBALL-70885）', pageKind=kind))
            gacha_audit = audit_gacha(exporter, native, gachas.get(ident), inputs, equipment if native[13] == '1' else characters)
            if gacha_audit['status'] != 'verified_static':
                base_blockers.append(blocker('gacha_odds_or_rule_mismatch', '卡池概率、奖励或规则依赖未闭合', details=gacha_audit))
        if typ in ['special_exchange_campaign', 'start_dash_exchange_campaign']:
            supported = ['exchange']
            constraints.update(required=True, rules=['仅既有票券或已保存资格兑换；不推定购买、新参与或发券'])
        if typ == 'multi_special_exchange_campaign':
            constraints.update(required=True, rules=['原生共同自选组队资格与票券分配、已保存资格及角色白名单'])
        if typ == 'pass_card_event':
            constraints.update(required=True, rules=['只允许一个原生当前期；保留原有免费/付费档位与已得资格，不授予新购买权益'])
        if typ in EVENT_TYPES:
            constraints.update(required=True, rules=['保留原生章节、开场剧情、关卡前置、星期及每日资格；运营开关不授予玩家解锁'])
        for action in supported:
            actions[action] = {'status': 'blocked' if base_blockers else 'passed', 'blockers': copy.deepcopy(base_blockers)}
        if collect_shop_only:
            actions['claim'] = {'status': 'not_applicable', 'blockers': [], 'reason': '原生kind1为兑换商店入口；无任务奖励，不应进入MissionScene'}
            actions['exchange'] = {'status': 'blocked' if base_blockers else 'passed', 'blockers': copy.deepcopy(base_blockers)}
            if not dependencies['productKeys']:
                for action in ['enter', 'exchange']:
                    actions[action] = {'status': 'blocked', 'blockers': [blocker('native_shop_scope_empty', '原生kind1要求进入兑换商店，但当前获胜商品表没有关联商品；不可补造价格或奖励', parentKey=key)]}
        static_checks = {}
        if typ in EVENT_TYPES and dependencies['questKeys']:
            checks = {
                'nativeFieldMapping': [member for member in dependencies['questKeys'] if quest_nodes[member]['battleReferences']['status'] != 'passed_native_field_mapping'],
                'effectiveServerFields': [member for member in dependencies['questKeys'] if quest_nodes[member].get('effectiveServerFieldParity', {}).get('status') != 'passed'
                                          or quest_nodes[member].get('additionalConsumedFieldAudit', {}).get('effectiveServerDifferences')],
                'rewardMembersAndConversions': [member for member in dependencies['questKeys'] if quest_nodes[member].get('nativeRewardStaticStatus') != 'passed'],
                'terrainReadAndDecode': [member for member in dependencies['questKeys'] if any(resources.get(logical, {}).get('syntax') != 'decoded_amf3'
                    for scene in quest_nodes[member]['battleReferences'].get('scenes', []) for logical in scene.get('terrainLogicals', []))],
                'singleNominalStaminaCredit': [member for member in dependencies['questKeys'] if quest_nodes[member]['category'] != 8
                    and quest_nodes[member].get('nativeKind') != 'Story'
                    and not quest_nodes[member].get('additionalConsumedFieldAudit', {}).get('nominalStamina', {}).get('preservedPolicy')
                    and not quest_nodes[member].get('additionalConsumedFieldAudit', {}).get('nominalStamina', {}).get('effectiveMatches', False)],
                'nativeChallengePointWiring': [] if daily_wiring_passed else [member for member in dependencies['questKeys'] if member in daily_keys],
            }
            static_checks = {name: {'status': 'blocked' if bad else 'passed', 'questKeys': bad} for name, bad in checks.items()}
            static_checks['excludedFromStaticPass'] = ['客户端实际导航和设备战斗', '地形内敌人及物件完整运行语义', '服务端未消费的原生客户端解锁/队伍/复活限制']
            actions['enter']['scope'] = {'questKeys': dependencies['questKeys'], 'source': 'Exact native parent/member relationship; no date projection or questMap owner guess',
                                         'preserveNativePersonalEligibility': True}
            for name, bad in checks.items():
                if bad:
                    actions['enter']['status'] = 'blocked'
                    message = ('原生挑战次数ID与既有存量已列明；成功后扣次、失败重试的服务端接线尚未核验'
                               if name == 'nativeChallengePointWiring' else '列明关卡的原生字段、实际服务端消费、场景或奖励静态依赖尚未闭合')
                    actions['enter']['blockers'].append(blocker('quest_static_' + name, message, questKeys=bad))
            if any(member in quest_collisions or member in quest_disagreements for member in dependencies['questKeys']):
                actions['enter']['status'] = 'blocked'
                actions['enter']['blockers'].append(blocker('quest_parent_ownership_conflict', '关卡存在多父或全局映射归属冲突'))
        if dependencies['missionKeys']:
            bad_rewards = [member for member in dependencies['missionKeys'] if mission_nodes[member]['rewardSemantics'] != 'passed']
            bad_rules = [member for member in dependencies['missionKeys'] if mission_nodes[member]['ruleSupport'] != 'passed']
            for action, bad in [('enter', sorted(set(bad_rules + bad_rewards))), ('claim', bad_rewards)]:
                if bad:
                    actions[action]['status'] = 'unreviewed' if not base_blockers else 'blocked'
                    actions[action]['blockers'].append(blocker('mission_static_dependency_review', '列明任务的事实规则或奖励解析/引用尚未闭合', missionKeys=bad))
        elif typ in ['collect_item_event', 'active_mission_event', 'pass_card_event'] and not collect_shop_only:
            for action in ['enter', 'claim']:
                actions[action]['status'] = 'unreviewed' if not base_blockers else 'blocked'
                actions[action]['blockers'].append(blocker('native_parent_mission_scope_empty', '当前原生任务表未找到显式归属任务，不能据此推定新任务可用', parentKey=key))
        if dependencies['productKeys']:
            retained_products = old.get('currentParentDefinitionEvidence', {}).get('reviewedExistingChildren')
            scope = ['event_item_shop:' + str(ident) for ident in retained_products] if retained_products is not None else dependencies['productKeys']
            actions['exchange']['scope'] = {'productKeys': sorted(scope), 'excludedUncataloguedProductKeys': dependencies['currentOnlyProductKeys']}
            bad = [member for member in scope if (children.get(member) or current_only_children[member])['staticStatus'] != 'verified_static']
            if old.get('currentParentDefinitionEvidence') and (captured['existingMatches'].get(key, {}).get('matchesCatalog')
                    or existing_rebind.get(key, {}).get('currentMatcherAfterLoaderRebind', {}).get('matchesCatalog')):
                retained_valid = [member for member in scope if children[member]['nativeRowMatchesCatalog'] and
                                  (children[member].get('existingDefinitionEvidenceMatch', {}).get('matchesCatalog') or
                                   existing_rebind.get(member, {}).get('currentMatcherAfterLoaderRebind', {}).get('matchesCatalog')) and not children[member]['fieldAudit']['issues']]
                actions['exchange']['scope']['validRetainedExactProductKeys'] = sorted(retained_valid)
                actions['exchange']['scope']['requiresReviewedDefinitionIdentityRebind'] = bool(existing_rebind.get(key))
                bad = [member for member in bad if member not in retained_valid]
            if bad:
                actions['exchange']['status'] = 'blocked'
                actions['exchange']['blockers'].append(blocker('product_dependencies_incomplete', '部分兑换商品规则或来源尚未闭合；不得随父项整体放开', productKeys=bad))
        if typ == 'box_gacha':
            parsed = captured['boxes'].get(key)
            bad = [member for member, reward in box_rewards.items() if reward['parentKey'] == key and reward['rewardSemantics'] != 'passed']
            if not parsed or not parsed['policyAccepted'] or bad:
                for action in ['enter', 'claim']:
                    actions[action]['status'] = 'blocked'
                    actions[action]['blockers'].append(blocker('box_policy_or_reward_static_dependency', '实际服务端策略解析或箱奖励引用不完整', policy=parsed, rewardKeys=bad))
        if typ == 'pass_card_event':
            bad = [member for member in dependencies['passRewardKeys'] if pass_rewards[member]['rewardSemantics'] != 'passed']
            if not captured['passEvents'].get(key) or bad:
                for action in ['enter', 'claim']:
                    actions[action]['status'] = 'blocked'
                    actions[action]['blockers'].append(blocker('pass_policy_or_reward_static_dependency', '实际通行证定义解析或档位奖励引用不完整', rewardKeys=bad))
        planned = controls.get(key)
        retained = {'preserveExistingProgress': True, 'preserveEarnedClaimsAndExchangeRights': True,
                    'plannedClaimOnly': bool(planned and planned['actionOverrides'].get('claim', {}).get('enabled') and not planned['actionOverrides'].get('enter', {}).get('enabled'))}
        if dependencies['challengePointQuestKeys']:
            retained.update(preserveRemainingChallengePoints=True, retroactiveChallengePointConsumption=False)
        if old.get('currentParentDefinitionEvidence'):
            retained['currentParentDefinitionEvidencePreserved'] = True
            retained['reviewedExistingProductKeys'] = ['event_item_shop:' + str(ident) for ident in old['currentParentDefinitionEvidence']['reviewedExistingChildren']]
            retained['unregisteredNewProductKeysRemainRejected'] = dependencies['currentOnlyProductKeys']
        rescue_missions = [member for member in dependencies['missionKeys'] if mission_nodes[member].get('ruleDecision', {}).get('mode') == 'successful_rescue_finish_once']
        if rescue_missions:
            retained['successfulRescueCompletionMissionKeys'] = rescue_missions
            retained['rescueProgressRule'] = '保留旧进度；可信随机救援报名绑定持久playId，成功完成后每次加一，未完成不计'
        if key == 'active_mission_event:150':
            retained.update(existingClaimsOnly=True, newParticipationDeferredByDecision=True, grantNewComebackQualification=False)
            actions['enter'] = {'status': 'blocked', 'blockers': [blocker('deferred_by_decision', '回归修行暂不新增回归资格；仅保留旧进度和领奖资格')]}
            constraints.update(required=True, rules=['已有回归资格与旧进度；本轮不新授回归资格'])
        if typ == 'gacha' and constraints.get('personalTimeWindowRequired'):
            retained.update(existingPersonalRightsOnly=True, grantNewPersonalPeriod=False, preserveCountersAndExchangePoints=True)
            actions['enter'] = {'status': 'blocked', 'blockers': [blocker('deferred_by_decision', '本轮不新增回归或星辰个人资格；保留已有进度、兑换和可信个人有效窗')],
                                'scope': {'requiresTrustedExistingPersonalPeriod': True, 'grantNewEligibility': False}}
        if typ == 'gacha' and constraints.get('pageKind') == 5:
            retained.update(crazyPaidSessionClaimPreserved=True, grantRewardsOnlyAfterFinalSelection=True)
            actions['claim']['scope'] = {'savedPaidSessionOnly': True, 'originalCandidateAndSaveSelectionProtocol': True}
        statuses = [value['status'] for value in actions.values() if value['status'] != 'not_applicable']
        static_status = 'mismatch' if base_blockers else 'unreviewed' if 'unreviewed' in statuses or 'blocked' in statuses else 'verified_static'
        title = presentation['rows'].get(key, {}).get('title', old['name'])
        native_entry = {'status': 'unreviewed', 'blockers': [blocker('native_entry_review', '等待逐项原生列表、文件夹、外传或父入口关联审查')]}
        if key in native_entry_rows:
            native_entry = native_entry_rows[key]
        if key in native_bridges:
            bridge = native_bridges[key]
            if bridge.get('boxKey') and bridge['boxKey'] not in dependencies['boxGachaKeys']:
                raise ValueError('controlled Box entry does not match native parent association: ' + key)
            native_entry.update(originalStatus=native_entry['status'], originalRoutes=copy.deepcopy(native_entry['routes']),
                                status='verified_controlled_bridge', blockers=[], controlledBridge=bridge)
        family = client_types.get(typ)
        if family:
            native_entry['helperSupportsHistoricalKeys'] = family.get('dynamicKey') is True and family.get('specificIdWhitelist') is False
            native_entry['nativeConsumers'] = family.get('nativeConsumer', [])
            native_entry['nativeLimits'] = family.get('limits', [])
            native_entry['simultaneous'] = family.get('simultaneous')
            if typ not in EVENT_TYPES and typ != 'box_gacha' and native:
                native_entry['status'] = 'verified_static_repository_enumeration'
                native_entry['blockers'] = []
        if typ == 'box_gacha':
            native_entry['originalParentRoutes'] = box_routes.get(key, [])
            native_entry['status'] = 'verified_static_parent_route' if box_routes.get(key) else 'blocked_absent_original_route'
            native_entry['blockers'] = [] if box_routes.get(key) else [blocker('box_parent_route_missing', '原生Raid或WorldStory父活动没有关联此箱池')]
        if collect_shop_only:
            native_entry.update(collectKind=1, collectKindLabel='收集与兑换', originalScene='EventItemExchangeShop(CollectItemEvent)',
                                missionSceneApplicable=False, sourceEvidence=external['collectKindEvidence'])
        if native_entry['status'] == 'blocked_absent_original_route':
            for action in ['visible', 'enter']:
                if actions[action]['status'] != 'not_applicable':
                    actions[action]['status'] = 'blocked'
                    actions[action]['blockers'].append(blocker('native_entry_missing', '未还原原生父活动参与入口；父到箱池的关联不证明箱池可返回关卡', details=native_entry))
        statuses = [value['status'] for value in actions.values() if value['status'] != 'not_applicable']
        static_status = 'mismatch' if base_blockers else 'unreviewed' if 'unreviewed' in statuses or 'blocked' in statuses else 'verified_static'
        rows.append({'key': key, 'type': typ, 'title': title, 'staticStatus': static_status, 'gameplayStatus': 'unreviewed',
                     **({'nativePage': {'kind': 'collect_item_exchange_shop', 'label': '活动兑换',
                                       'description': '在活动兑换商店使用原活动道具兑换商品；此类型不设活动任务。'}} if collect_shop_only else {}),
                     'boundedRuntimeVerification': runtime_rows.get(key, []),
                     'staticChecks': static_checks,
                     'actions': actions, 'dependencies': dependencies, 'retainedRights': retained,
                     'personalEligibility': constraints, 'exclusiveGroup': exclusive,
                     'nativeEntry': native_entry,
                     'configuration': {'planned': planned is not None, 'newParticipationPlanned': bool(planned and planned['actionOverrides'].get('enter', {}).get('enabled')),
                                       'defaultEnabledForNewHistory': False, 'source': 'content_july_controls.json only; live state not read'},
                     'definition': {'nativeRowMatchesCatalog': native_matches, 'catalogStatus': old.get('definitionEvidence', {}).get('status'),
                                    'currentStatus': definition_status, 'dateDifferencesOnly': bool(dated_only and definition_status == 'mismatch'),
                                    'issues': current_definition.get('issues', [])},
                     **({'gachaAudit': gacha_audit} if gacha_audit else {})})
    result = {'schemaVersion': 1, 'defaultEnabled': False,
              'scope': 'All 1020 historical catalog parents; evidence only, not a control plan or gameplay acceptance. Existing controls and player rights are never changed.',
              'statusMeaning': {'passed': '列明的原生定义及服务端消费静态依赖通过；不代表事务、设备流程或实际可玩验收，不授权运营开关',
                                'gameplayStatus': '逐活动动态流程另行验证；本清单不自行标记verified',
                                'clientNativeGuards': '保留原生前置、队伍及次数资格；不宣称RawQuest服务端已重新强制全部客户端条件'},
              'sourceSnapshot': {'catalogSha256': sha(catalog_bytes), 'planSha256': sha(plan_bytes),
                                 'manifestSha256': source['manifestSha256'], 'assetVersion': source['assetVersion'],
                                 'resourceMasterBytesRead': bytes_read, 'imageBytesDecoded': 0,
                                 'serverSources': server_sources, 'runtimeLoaderSets': captured['loaderSets'], 'externalEvidence': external},
              'boundedRuntimeEvidence': bounded_runtime,
              'rows': rows, 'childIndex': {'quests': quest_nodes, 'missions': mission_nodes, 'catalogChildren': children,
                                          'boxStages': box_stages, 'boxRewards': box_rewards, 'resources': resources,
                                          'questRewards': quest_rewards, 'passRewards': pass_rewards,
                                          'currentOnlyChildren': current_only_children},
              'ownership': {'duplicateQuestParents': quest_collisions, 'catalogQuestOwnerDisagreements': quest_disagreements,
                            'catalogMissionOwnerDisagreements': mission_disagreements,
                            'excludedCurrentOnlyNativeParents': excluded},
              'summary': {'parents': len(rows), 'types': len(PARENT_TYPES), 'plannedParents': sum(row['configuration']['planned'] for row in rows),
                          'newParticipationParents': sum(row['configuration']['newParticipationPlanned'] for row in rows),
                          'fixedJulyParents': sum(row['configuration']['planned'] and not row['retainedRights']['plannedClaimOnly'] for row in rows),
                          'retainedClaimOnlyParents': sum(row['retainedRights']['plannedClaimOnly'] for row in rows),
                          'exchangeOnlyPlannedParents': sum(row['configuration']['planned'] and row['type'] in ['special_exchange_campaign', 'start_dash_exchange_campaign'] for row in rows),
                          'staticStatusCounts': dict(Counter(row['staticStatus'] for row in rows)),
                          'gachaPageKindCounts': {str(kind): page_counts.get(str(kind), 0) for kind in range(9)},
                          'nativeUnimplementedPageKinds': {str(kind): [row['key'] for row in rows if row['type'] == 'gacha' and row['personalEligibility'].get('pageKind') == kind] for kind in [6, 7]},
                          'specialEligibilityGachaParents': sum(row['type'] == 'gacha' and row['personalEligibility']['required'] for row in rows),
                          'specialEligibilityGachaByKind': {name: [row['key'] for row in rows if row['type'] == 'gacha' and predicate(row)]
                                                           for name, predicate in {
                                                               'singleAccountTenDraw': lambda r: r['personalEligibility'].get('pageKind') == 1,
                                                               'ticketOnly': lambda r: r['personalEligibility'].get('pageKind') in [2, 3, 4, 5],
                                                               'comeback': lambda r: r['personalEligibility'].get('nativeComebackFlag'),
                                                               'stars': lambda r: r['personalEligibility'].get('nativeStarsFlag')}.items()},
                          'preciseProductReceipts': len(exact_receipts),
                          'preciseParentReceipts': len(parent_receipts),
                          'preciseDefinitionReceipts': len(exact_receipts) + len(parent_receipts),
                          'existingEvidenceRebindCandidates': len(existing_rebind),
                          'sceneReferenceCounts': {'questsWithCandidateFieldsOrFloors': sum(bool(node['battleReferences']['scenes']) for node in quest_nodes.values()),
                                                   'questsWithUnresolvedNativeLoaderMapping': sum(node['battleReferences']['status'] == 'unresolved_native_loader_mapping' for node in quest_nodes.values()),
                                                   'nativeKindCounts': dict(Counter(node.get('nativeKind', 'unreviewed') for node in quest_nodes.values())),
                                                   'nativeFieldMappingStatuses': dict(Counter(node['battleReferences']['status'] for node in quest_nodes.values())),
                                                   'terrainLogicals': len(terrain_logicals), 'terrainReadOrSyntaxFailures': terrain_failures},
                          'questServerFieldParityCounts': dict(Counter(node.get('serverFieldParity', {}).get('status', 'unreviewed') for node in quest_nodes.values())),
                          'questEffectiveServerFieldParityCounts': dict(Counter(node.get('effectiveServerFieldParity', {}).get('status', 'unreviewed') for node in quest_nodes.values())),
                          'questRewardMemberStatusCounts': dict(Counter(node.get('staticStatus', 'unreviewed') for node in quest_rewards.values())),
                          'nativeChallengePointRules': {'quests': len(daily_keys), 'parents': sum(bool(row['dependencies']['challengePointQuestKeys']) for row in rows),
                                                       'staticWiringStatus': 'passed' if daily_wiring_passed else 'unreviewed',
                                                       'existingServerRecoveryCounts': dict(Counter(str(quest_nodes[key]['challengePointRule']['existingServerLookup']['isRecovery']).lower() for key in daily_keys))},
                          'nativeEntryStatusCounts': dict(Counter(row['nativeEntry']['status'] for row in rows)),
                          'childCounts': {'quests': len(quest_nodes), 'missions': len(mission_nodes), 'catalogChildren': len(children),
                                          'boxStages': len(box_stages), 'boxRewards': len(box_rewards), 'passRewards': len(pass_rewards),
                                          'currentOnlyChildren': len(current_only_children)},
                          'currentOnlyChildTypes': dict(Counter(row['type'] for row in current_only_children.values())),
                          'missionRelationCounts': dict(Counter(node['relation'] for node in mission_nodes.values())),
                          'decisions': {'deferredNewParticipationParents': ['active_mission_event:150'],
                                        'successfulRescueFinishMissionKeys': [key for key, node in mission_nodes.items()
                                                                             if node.get('ruleDecision', {}).get('mode') == 'successful_rescue_finish_once']},
                          'typeCounts': {typ: {'total': sum(row['type'] == typ for row in rows),
                                              'staticStatuses': dict(Counter(row['staticStatus'] for row in rows if row['type'] == typ))}
                                         for typ in PARENT_TYPES}}}
    supplemental = {'schemaVersion': 1, 'source': result['sourceSnapshot'], 'rows': {**exact_receipts, **parent_receipts},
                    'existingEvidenceRebind': existing_rebind,
                    'scope': 'Strict native product/active-parent scoped row and dependency equality plus actual runtime selectors; no new capabilities or publication.'}
    if shop_getter_proof:
        supplemental['effectiveShopDefinitionEvidence'] = {'getterProof': shop_getter_proof,
            'rows': {key: child['effectiveFieldAudit'] for key, child in children.items() if 'effectiveFieldAudit' in child},
            'scope': 'Static effective definition equality; ledger and ownership reviews remain separate.'}
    runtime_source = 'src/lib/content-operations.ts'
    server_sources[runtime_source] = {'sha256': sha((repo / runtime_source).read_bytes())}
    preserved_definition = None
    if args.definition_evidence and Path(args.definition_evidence).is_file():
        existing_definition = load(args.definition_evidence)
        if equivalent_definition_receipts(existing_definition, supplemental):
            preserved_definition = existing_definition
    result['summary']['definitionEvidenceWriteMode'] = 'preserved_semantically_identical' if preserved_definition else 'regenerated'
    matrix = runtime_receipts(repo, [], runtime_catalog=catalog, runtime_evidence=preserved_definition or supplemental,
                               runtime_keys=sorted(original), runtime_details=True)
    for parent in rows:
        definition = matrix['runtimeDefinitions'][parent['key']]
        definition['sourceMismatches'] = [relative for relative in original[parent['key']].get('definitionEvidence', {}).get('serverSources', [])
             if not (repo / relative).is_file() or sha((repo / relative).read_bytes()) != catalog.get('serverResources', {}).get(relative, {}).get('sha256')]
        parent['runtimeDefinition'] = definition
        parent['definition']['supplementalExactReceipt'] = parent['key'] in parent_receipts
        if not definition['matchesCatalog']:
            for action in parent['actions'].values():
                if action['status'] != 'not_applicable':
                    action['status'] = 'blocked'
                    action['blockers'].append(blocker('runtime_definition_not_matched', '实际服务端定义门禁未通过；静态资料存在不代表可配置或可参与', sources=definition['sourceMismatches']))
            parent['staticStatus'] = 'unreviewed'
    result['summary']['runtimeDefinitionCounts'] = dict(Counter(str(row['runtimeDefinition']['matchesCatalog']).lower() for row in rows))
    result['summary']['runtimeDefinitionBlockedKeys'] = [row['key'] for row in rows if not row['runtimeDefinition']['matchesCatalog']]
    result['summary']['runtimeDefinitionMethod'] = matrix['method']
    for key, child in children.items():
        definition = matrix['runtimeDefinitions'][key]
        child['runtimeDefinition'] = {name: definition[name] for name in ['digest', 'matchesCatalog']}
        if not definition['matchesCatalog']:
            child['runtimeDefinition']['reason'] = {'baseMatchesCatalog': definition['base']['matchesCatalog'],
                'wholeSourceMismatches': definition['wholeSourceMismatches'],
                'historicalReceiptPresent': definition['historicalReceiptPresent'],
                'shopIdentityRequired': definition['shopIdentityRequired'], 'shopIdentityAvailable': definition['shopIdentityAvailable']}
    catalog_blocked = [key for key, definition in matrix['runtimeDefinitions'].items() if not definition['matchesCatalog']]
    result['summary']['runtimeCatalogDefinitionCounts'] = dict(Counter(str(value['matchesCatalog']).lower() for value in matrix['runtimeDefinitions'].values()))
    result['summary']['runtimeCatalogBlockedTypeCounts'] = dict(Counter(original[key]['type'] for key in catalog_blocked))
    result['summary']['runtimeCatalogBlockedKeys'] = catalog_blocked
    result['summary']['effectiveEventProductCounts'] = dict(Counter(child['effectiveFieldAudit']['status'] for child in children.values() if 'effectiveFieldAudit' in child))
    result['summary']['staticStatusCounts'] = dict(Counter(row['staticStatus'] for row in rows))
    for typ in PARENT_TYPES:
        result['summary']['typeCounts'][typ]['staticStatuses'] = dict(Counter(row['staticStatus'] for row in rows if row['type'] == typ))
    if manifest_before != (repo / 'assets/asset-patch/manifest.json').read_bytes() or catalog_bytes != catalog_path.read_bytes() or plan_bytes != plan_path.read_bytes():
        raise ValueError('read-only input changed during history capture')
    for relative, identity in server_sources.items():
        if sha((repo / relative).read_bytes()) != identity['sha256']:
            raise ValueError('server input changed during history capture: ' + relative)
    for path, raw in external_bytes.items():
        if Path(path).read_bytes() != raw:
            raise ValueError('external source evidence changed during capture: ' + path)
    if args.extra_field_evidence:
        write(args.extra_field_evidence, {'schemaVersion': 1, 'source': result['sourceSnapshot'], 'quests': extra_fields,
                                          'summary': {'rawDifferentFields': dict(Counter(change['field'] for row in extra_fields.values() for change in row['rawServerDifferences'])),
                                                      'effectiveDifferentFields': dict(Counter(change['field'] for row in extra_fields.values() for change in row.get('effectiveServerDifferences', []))),
                                                      'nominalStaminaDifferences': sum(not row['nominalStamina']['matches'] for row in extra_fields.values())}})
    write(args.output, result)
    if args.definition_evidence and not preserved_definition:
        write(args.definition_evidence, supplemental)
    write(args.evidence, {'schemaVersion': 1, 'summary': result['summary'], 'outputSha256': sha(Path(args.output).read_bytes()),
                          'definitionEvidenceSha256': sha(Path(args.definition_evidence).read_bytes()) if args.definition_evidence else None,
                          'ownership': result['ownership']})
    print(json.dumps(result['summary']))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', required=True)
    ap.add_argument('--resource-root', required=True)
    ap.add_argument('--exporter', required=True)
    ap.add_argument('--output')
    ap.add_argument('--evidence')
    ap.add_argument('--emit-raid-assets', action='store_true')
    ap.add_argument('--raid-only', action='store_true')
    ap.add_argument('--client-audit')
    ap.add_argument('--action-evidence')
    ap.add_argument('--entry-schema')
    ap.add_argument('--entry-history-output')
    ap.add_argument('--native-entry-bridge-evidence')
    ap.add_argument('--quest-schema')
    ap.add_argument('--quest-reward-schema')
    ap.add_argument('--quest-rules')
    ap.add_argument('--quest-rules-only', action='store_true')
    ap.add_argument('--quest-runtime-evidence')
    ap.add_argument('--runtime-evidence', action='append', default=[])
    ap.add_argument('--collect-kind-evidence')
    ap.add_argument('--extra-field-evidence')
    ap.add_argument('--product-schema')
    ap.add_argument('--shop-rules')
    ap.add_argument('--shop-rules-only', action='store_true')
    ap.add_argument('--shop-native-source')
    ap.add_argument('--shop-getter-evidence')
    ap.add_argument('--product-runtime-evidence', action='append', default=[])
    ap.add_argument('--definition-evidence')
    ap.add_argument('--refresh-definition-loaders', action='store_true')
    args = ap.parse_args()
    if args.quest_rules_only and not args.quest_rules:
        ap.error('--quest-rules-only requires --quest-rules')
    repo, resource_root = Path(args.repo).resolve(), Path(args.resource_root).resolve()
    manifest_before = (repo / 'assets/asset-patch/manifest.json').read_bytes()
    if manifest_before != (resource_root / 'assets/asset-patch/manifest.json').read_bytes():
        raise ValueError('target and read-only resource root have different winning chains')
    exporter = importer(args.exporter)
    if args.refresh_definition_loaders:
        refresh_definition_loaders(args, repo, manifest_before)
        return
    if args.shop_rules_only:
        build_shop_rules_only(args, repo, resource_root, exporter, manifest_before)
        return
    if args.raid_only:
        if not args.emit_raid_assets:
            raise ValueError('--raid-only requires --emit-raid-assets')
        inputs, source = exporter.resolve(resource_root, [RAID_MASTER, RAID_QUEST, RAID_OVERALL, RAID_RANKING, RANKING_REWARD])
        rules, rewards = build_raid_assets(exporter, inputs, source)
        write(repo / 'assets/raid_event_rules.json', rules)
        write(repo / 'assets/raid_event_overall_reward.json', rewards)
        ranking = build_ranking_assets(exporter, inputs, source)
        write(repo / 'assets/ranking_event_ranking_reward.json', ranking[RANKING_REWARD])
        write(repo / 'assets/raid_event_ranking_reward.json', ranking[RAID_RANKING])
        print(json.dumps({'raidEvents': len(rules['events']), 'overallRawRows': len(rewards['rows']),
                          'manifestSha256': source['manifestSha256']}))
        return
    if not args.output or not args.evidence:
        raise ValueError('full inventory requires --output and --evidence')
    build_readiness(args, repo, resource_root, exporter, manifest_before)


if __name__ == '__main__':
    main()
