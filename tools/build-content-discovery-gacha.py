#!/usr/bin/env python3
"""Rebuild read-only gacha/campaign search relationships from actual consumers and winning masters.

Verified means a metadata relationship was checked; it never grants participation or exchange rights.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
TYPES = {'gacha', 'special_exchange_campaign', 'multi_special_exchange_campaign', 'start_dash_exchange_campaign'}
GACHA_FILES = ['assets/gacha.json', 'assets/gacha_cnmod.json', 'assets/gacha_rank_p5b.json', 'assets/gacha_midautumn_2026.json']
TEXT = 'master/character/character_text.orderedmap'
CHARACTER = 'master/character/character.orderedmap'
SPECIAL = 'master/campaign/special_exchange/special_exchange_campaign_character.orderedmap'
MULTI = 'master/campaign/multi_special_exchange/multi_special_exchange_campaign_character.orderedmap'
EQUIPMENT = 'master/item/equipment.orderedmap'
SPECIAL_EQUIPMENT = 'master/campaign/special_exchange/special_exchange_campaign_equipment.orderedmap'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_output(path, resource_root, repo):
    target = Path(path).resolve()
    inventory = subprocess.run(['git', '-c', 'core.quotePath=false', 'worktree', 'list', '--porcelain'],
                               cwd=Path(__file__).resolve().parent.parent, check=True,
                               encoding='utf8', stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    worktrees = [Path(line[9:]).resolve(strict=True) for line in inventory.stdout.splitlines()
                 if line.startswith('worktree ')]
    if not worktrees:
        raise ValueError('Cannot establish protected Git worktree inventory')
    for root in (*worktrees, resource_root.resolve()):
        if target == root or root in target.parents:
            raise ValueError('output overlaps protected source/resource root: ' + str(target))
    if '.cdn' in [part.lower() for part in target.parts]:
        raise ValueError('output overlaps read-only .cdn: ' + str(target))
    # Generated data belongs outside every checkout; only this script/tests are source artifacts.
    if target == repo.resolve() or repo.resolve() in target.parents:
        raise ValueError('generated data must be outside target checkout')
    return target


def named_character(ident, texts):
    values = texts.get(str(ident))
    if not values or len(values) != 1 or len(values[0]) < 4:
        raise ValueError('native character text absent/ambiguous: ' + str(ident))
    name, title = values[0][0], values[0][3]
    if not name or name == '(None)' or '\ufffd' in name + title:
        raise ValueError('reliable native character text absent: ' + str(ident))
    # Use the game's actual epithet, preserving variant identities without inventing seasonal labels.
    return name + ('（' + title + '）' if title and title != '(None)' else ''), name


def pool_links(pool, rank_rates=None):
    """Zero-weight entries are not drawable; exchange checks use the first matching pool item."""
    rank_rates = rank_rates or {'normal': [50, 250, 700], 'multiGuarantee': [50, 950]}
    active = set()
    for weights in (rank_rates['normal'], rank_rates['multiGuarantee']):
        positive = {str(index + 1) for index, weight in enumerate(weights) if weight > 0}
        active.update(positive or {'1'})  # actual consumer's null index fallback
    out, first = set(), {}
    for bucket in sorted(pool, key=int):  # JS Object.values enumerates integer keys numerically
        entries = pool[bucket]
        drawable = [item for item in entries if item.get('odds', 0) > 0] or entries[:1]
        for item in entries:
            ident = int(item['id'])
            first.setdefault(ident, item)
            if bucket in active and item in drawable:
                out.add((ident, 'pool'))
                if item.get('isRateUp') is True:
                    out.add((ident, 'up'))
    for ident, item in first.items():
        if item.get('isExchangeable') is True:
            out.add((ident, 'exchange'))
    return sorted(out)


def native_entries(exporter, raw, logical, odds_id, is_character=True):
    outer = exporter.nested_rows(raw, logical, 2)
    if set(outer) != {odds_id}:
        raise ValueError('unexpected native odds outer key: ' + logical)
    rows = outer[odds_id]
    result = []
    for group in rows.values():
        if len(group) != 1 or len(group[0]) < (7 if is_character else 6):
            raise ValueError('unexpected native character odds row: ' + logical)
        v = group[0]
        result.append({'id': int(v[0]), 'rank': int(v[1]), 'odds': int(v[2]),
                       'isRateUp': v[3].lower() == 'true', 'isLimited': v[4].lower() == 'true',
                       'isExchangeable': v[5].lower() == 'true',
                       'trialReadingForced': v[6].lower() == 'true' if is_character else False})
    return result


def signature(entries):
    fields = ['id', 'rank', 'odds', 'isRateUp', 'isLimited', 'isExchangeable', 'trialReadingForced']
    return sorted(tuple(item.get(field, False if field.startswith('is') or field == 'trialReadingForced' else None)
                        for field in fields) for item in entries)


def ensure_keys(rows, parents):
    if set(rows) != {row['key'] for row in parents}:
        raise ValueError('parent coverage changed')
    for key, row in rows.items():
        if row['status'] not in ('verified', 'unavailable', 'not_applicable') or not row['evidence']:
            raise ValueError('missing explicit state/evidence: ' + key)
        if row['status'] != 'verified' and row['characters'] and not row.get('missingCharacterIds'):
            raise ValueError('unverified relationships leaked: ' + key)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', required=True)
    ap.add_argument('--resource-root', required=True)
    ap.add_argument('--exporter', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--report', required=True)
    a = ap.parse_args()
    repo, root = Path(a.repo).resolve(), Path(a.resource_root).resolve()
    output, report = safe_output(a.output, root, repo), safe_output(a.report, root, repo)
    if output == report:
        raise ValueError('output and report must differ')
    resources, snapshots = [], []

    def read(path, location='repo'):
        base = repo if location == 'repo' else root
        p = base / path
        raw = p.read_bytes()
        resources.append({'kind': 'file', 'root': location, 'path': path, 'sha256': sha(raw)})
        snapshots.append((p, sha(raw)))
        return raw

    catalog_raw, presentation_raw = read('assets/content_catalog.json'), read('assets/content_presentation.json')
    catalog, presentation = json.loads(catalog_raw), json.loads(presentation_raw)
    manifest = read('assets/asset-patch/manifest.json')
    if read('assets/asset-patch/manifest.json', 'resource-root') != manifest:
        raise ValueError('resource-root manifest differs from target')
    if presentation['source']['manifestSha256'] != sha(manifest):
        raise ValueError('presentation chain identity is stale')
    # The existing catalog is a parent-ID inventory retained across resource edges.
    # Its file hash is bound below; each relationship is re-read from the current winning chain.
    parents = [row for row in catalog['rows'] if row['type'] in TYPES and row['key'] in presentation['rows']]
    expected = {key for key, value in presentation['rows'].items() if value['type'] in TYPES}
    if {row['key'] for row in parents} != expected:
        raise ValueError('catalog does not cover presentation parents')
    spec = importlib.util.spec_from_file_location('discovery_native_exporter', a.exporter)
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    exporter_path = Path(a.exporter).resolve()
    resources.append({'kind': 'tool', 'path': str(exporter_path), 'sha256': sha(exporter_path.read_bytes())})
    for dependency in (exporter.core, exporter.chain, exporter.store):
        dependency_path = Path(dependency.__file__).resolve()
        resources.append({'kind': 'tool', 'path': str(dependency_path), 'sha256': sha(dependency_path.read_bytes())})
    read('tools/build-content-discovery-gacha.py')
    logicals = sorted({row['source'] for row in parents} | {TEXT, CHARACTER, SPECIAL, MULTI, EQUIPMENT, SPECIAL_EQUIPMENT})
    native, source = exporter.resolve(root, logicals)
    required = {TEXT, CHARACTER, SPECIAL, MULTI, EQUIPMENT, SPECIAL_EQUIPMENT} | {row['source'] for row in parents}
    if required - set(native):
        raise ValueError('native master absent: ' + ','.join(sorted(required - set(native))))
    parsed = {logical: exporter.parse_rows(value[0], logical) for logical, value in native.items()}
    texts, character_master = parsed[TEXT], parsed[CHARACTER]
    gachas, winners = {}, {}
    for relative in GACHA_FILES:
        table = json.loads(read(relative))
        gachas.update(table)
        winners.update({key: relative for key in table})
    loader = read('src/lib/content-master.ts').decode('utf8')
    if not re.search(r'serverGachas\s*=\s*\{\s*\.\.\.baseGachas,\s*\.\.\.cnmodGachas,\s*\.\.\.rankP5bGachas,\s*\.\.\.midautumnGachas\s*\}', loader):
        raise ValueError('server gacha precedence changed')
    # Bind relationship semantics to actual transaction consumers, not banners/names.
    for relative in ['src/lib/assets.ts', 'src/lib/gacha.ts', 'src/lib/gacha-rules.ts',
                     'src/routes/api/gacha.ts', 'src/lib/exchange-campaign-entitlements.ts',
                     'src/lib/exchange-campaign-routes.ts', 'src/lib/multi-special-exchange.ts',
                     'src/routes/api/multiSpecialExchange.ts']:
        read(relative)
    definitions = read('src/lib/exchange-campaign-definitions.ts').decode('utf8')
    match = re.search(r'SPECIAL_EXCHANGE_DEFINITIONS[^=]*=\s*(\{.*?\})\s*export const START_DASH', definitions, re.S)
    if not match:
        raise ValueError('special exchange declaration changed')
    specials = json.loads(match.group(1))
    multi_server = json.loads(read('assets/multi_special_exchange_campaign_character.json'))
    odds_logicals = set()
    for parent in parents:
        if parent['type'] != 'gacha':
            continue
        v = parsed[parent['source']][str(parent['id'])][0]
        odds_logicals.update('master/gacha_odds/' + v[i] + '.orderedmap' for i in ((14, 15, 16) if v[13] == '0' else (22, 23, 24)) if v[i] not in ('', '(None)'))
    odds, odds_source = exporter.resolve(root, sorted(odds_logicals))
    if source['manifestSha256'] != odds_source['manifestSha256'] or source['actualChain'] != odds_source['actualChain']:
        raise ValueError('winning chain changed during native capture')
    native.update(odds)
    for logical, (raw, identity) in native.items():
        resources.append(dict(identity, kind='archive_member', root='resource-root', logicalPath=logical,
                              member=exporter.member(logical), sha256=sha(raw)))
    rows, mismatches, name_failures = {}, {}, {}
    name_cache = {}

    def characters(links):
        result, missing = [], {}
        for ident, relation in sorted(set(links)):
            try:
                if str(ident) not in character_master:
                    raise ValueError('native character definition absent: ' + str(ident))
                if ident not in name_cache:
                    name_cache[ident] = named_character(ident, texts)
            except ValueError as exc:
                missing[ident] = str(exc)
                continue
            name, base_name = name_cache[ident]
            result.append({'id': ident, 'name': name, 'relation': relation, 'aliases': [base_name] if base_name != name else []})
        return result, missing

    for parent in parents:
        key, typ, ident = parent['key'], parent['type'], str(parent['id'])
        if len(parsed[parent['source']].get(ident, [])) != 1:
            raise ValueError('native parent absent/ambiguous: ' + key)
        v = parsed[parent['source']][ident][0]
        evidence = [{'kind': 'native_parent', 'logicalPath': parent['source'], 'rowId': ident}]
        row = {'characters': [], 'rewards': [], 'notes': [], 'publicNotes': [], 'status': 'verified', 'evidence': evidence}
        links, issues = [], []
        if typ == 'gacha':
            evidence.append({'kind': 'native_gacha_kind', 'fieldIndex': 13, 'value': v[13]})
            is_character = v[13] == '0'
            server = gachas.get(ident)
            if server is None or server.get('type') != int(v[13]):
                issues.append('服务端缺少同编号同奖励类型卡池定义')
            native_pool = {}
            for bucket, column in ([('3', 14), ('2', 15), ('1', 16)] if is_character else [('3', 22), ('2', 23), ('1', 24)]):
                oid = v[column]
                if oid in ('', '(None)'):
                    continue
                logical = 'master/gacha_odds/' + oid + '.orderedmap'
                evidence.append({'kind': 'native_character_odds' if is_character else 'native_equipment_odds', 'logicalPath': logical, 'parentFieldIndex': column,
                                 'outerKey': oid, 'fields': {'id': 0, 'rank': 1, 'odds': 2, 'isRateUp': 3, 'isExchangeable': 5}})
                if logical not in odds:
                    issues.append('原生概率表缺失：' + logical)
                    continue
                native_pool[bucket] = native_entries(exporter, odds[logical][0], logical, oid, is_character)
                if server is not None and signature(server.get('pool', {}).get(bucket, [])) != signature(native_pool[bucket]):
                    sv, nv = signature(server.get('pool', {}).get(bucket, [])), signature(native_pool[bucket])
                    if sorted(x[:3] + x[4:] for x in sv) == sorted(x[:3] + x[4:] for x in nv):
                        changed = sorted({x[0] for x in set(sv) ^ set(nv)})
                        row['notes'].append('原生展示与服务端UP标记存在差异；检索按当前服务端定义标记UP，池内及兑换关系已核对一致。')
                        row['publicNotes'].append('部分装备的UP标记在客户端与服务端资料中不一致，此处仅列出已核实的产出与兑换关系。')
                        evidence.append({'kind': 'native_server_rate_up_difference', 'nativeLogicalPath': logical,
                                         'nativeFieldIndex': 3, 'serverPath': winners[ident], 'serverField': 'pool/' + bucket + '/*/isRateUp',
                                         'ids': changed, 'resolution': 'runtime server flags authoritative; draw weights and exchange flags agree'})
                    else:
                        issues.append('原生/服务端概率行不一致：bucket ' + bucket)
            if server:
                if set(server.get('pool', {})) != set(native_pool):
                    issues.append('原生/服务端概率分组不一致')
                server_links = pool_links(server.get('pool', {}), server.get('rankRates'))
                native_links = pool_links(native_pool, server.get('rankRates'))
                if {(i, r) for i, r in server_links if r != 'up'} != {(i, r) for i, r in native_links if r != 'up'}:
                    issues.append('原生/服务端池内或兑换关系不一致')
                links = server_links
                evidence.append({'kind': 'runtime_gacha', 'path': winners[ident], 'jsonPointer': '/' + ident + '/pool',
                                 'consumer': 'src/lib/gacha.ts#drawGachaWithMetadataSync',
                                 'relations': {'up': 'drawable by runtime rank/odds selection AND isRateUp=true', 'pool': 'runtime rank/odds selection (including consumer null-index fallback)',
                                               'exchange': 'src/lib/gacha-rules.ts#getExchangeableGachaItem first match isExchangeable=true'}})
                if not any(relation == 'up' for _, relation in links):
                    row['notes'].append('概率表未标记UP；池内成员不等同于UP。')
            if not is_character:
                row.update(characterStatus='not_applicable')
                row['notes'].append('装备卡池，角色语义不适用；装备关系读取原生及服务端概率表。')
        elif typ == 'special_exchange_campaign':
            evidence.append({'kind': 'native_reward_kind', 'fieldIndex': 3, 'value': v[3]})
            is_character = v[3] == '0'
            special_logical = SPECIAL if is_character else SPECIAL_EQUIPMENT
            ids = [int(group[0]) for group in parsed[special_logical].get(ident, [])]
            definition = specials.get(ident)
            if not ids or not definition or definition.get('rewardType') != int(v[3]) or definition.get('rewardIds') != ids:
                issues.append('原生/服务端自选奖励白名单未闭合')
            if definition and definition.get('ticketItemId') != int(v[9]):
                issues.append('原生/服务端自选票券身份不一致')
            links = [(cid, 'exchange') for cid in ids]
            evidence.append({'kind': 'campaign_character_whitelist' if is_character else 'campaign_equipment_whitelist', 'logicalPath': special_logical, 'outerKey': ident,
                             'fieldIndex': 0, 'consumer': 'src/lib/exchange-campaign-entitlements.ts#getExchangeEntitlementSync',
                             'serverDefinition': 'src/lib/exchange-campaign-definitions.ts#SPECIAL_EXCHANGE_DEFINITIONS/' + ident})
            row['notes'].append('奖励白名单仅供检索；兑换仍需要既有资格及对应票券。')
            row['publicNotes'].append('可选奖励仅供查询；兑换仍需已有资格及对应票券。')
            if not is_character:
                row.update(characterStatus='not_applicable')
                row['notes'].append('装备自选，角色语义不适用。')
        elif typ == 'multi_special_exchange_campaign':
            tickets = [v[i] for i in (10, 12, 14) if v[i] not in ('', '(None)')]
            allocation = re.search(r'\[' + re.escape(ident) + r',\s*\{\s*campaignId:\s*' + re.escape(ident)
                                   + r',\s*ticketItemIds:\s*\[([^\]]+)\]',
                                   (repo / 'src/lib/multi-special-exchange.ts').read_text(encoding='utf8'))
            if not allocation or [int(x.strip()) for x in allocation.group(1).split(',')] != [int(x) for x in tickets]:
                issues.append('原生/服务端共同自选票券分配不一致')
            for ticket in tickets:
                ids = [int(group[0]) for group in parsed[MULTI].get(ticket, [])]
                if not ids or multi_server.get(ticket) != ids:
                    issues.append('原生/服务端票券角色白名单不一致：' + ticket)
                links.extend((cid, 'exchange') for cid in ids)
                evidence.append({'kind': 'ticket_character_whitelist', 'logicalPath': MULTI, 'outerKey': ticket,
                                 'parentTicketFields': [10, 12, 14], 'fieldIndex': 0,
                                 'consumer': 'src/lib/multi-special-exchange.ts#isMultiSpecialExchangeCharacter'})
            row['notes'].append('检索合并本活动各票券白名单；实际可选角色取决于分配到的票券及既有资格。')
            row['publicNotes'].append('此处合并展示各票券可选角色；实际可选范围取决于获得的票券及已有资格。')
        else:
            row.update(status='unavailable', notes=['角色清单依玩家已保存的gachaId与termIndex、四/五星非限定及排除表动态生成，不能提供唯一静态自选清单。'])
            row['publicNotes'].append('可选角色依玩家已有资格及当时绑定的卡池动态确定，暂无统一的静态角色清单。')
            evidence.append({'kind': 'player_dependent_character_selection',
                             'consumer': 'src/lib/exchange-campaign-entitlements.ts#getExchangeEntitlementSync',
                             'definition': 'src/lib/exchange-campaign-definitions.ts#START_DASH_EXCHANGE_DEFINITIONS/' + ident,
                             'requiredPlayerFields': ['gachaId', 'termIndex'], 'filters': ['rank in [4,5]', 'isLimited=false', 'campaign term exclusions']})
        if issues:
            row.update(status='unavailable', notes=row['notes'] + issues)
            mismatches[key] = issues
        elif row['status'] == 'verified' and row.get('characterStatus') == 'not_applicable':
            for cid, relation in sorted(set(links)):
                equip = parsed[EQUIPMENT].get(str(cid))
                if not equip or len(equip) != 1 or not equip[0][1] or '\ufffd' in equip[0][1]:
                    row.update(status='unavailable', rewards=[], notes=row['notes'] + ['原生装备名称缺失：' + str(cid)])
                    break
                row['rewards'].append({'kind': 'equipment', 'id': cid, 'name': equip[0][1], 'relation': relation})
            evidence.append({'kind': 'native_equipment_names', 'logicalPath': EQUIPMENT, 'fieldIndex': 1})
        elif row['status'] == 'verified':
            row['characters'], missing = characters(links)
            if missing:
                row.update(status='unavailable', missingCharacterIds=sorted(missing),
                           notes=row['notes'] + ['部分角色缺可靠中文资料，以下仅收录已核对的角色；未收录ID：' + ', '.join(map(str, sorted(missing)))])
                name_failures[key] = missing
                evidence.append({'kind': 'missing_chinese_names', 'logicalPath': TEXT,
                                 'rows': [{'id': cid, 'nativeName': texts.get(str(cid), [['']])[0][0], 'reason': reason}
                                          for cid, reason in sorted(missing.items())]})
            untranslated = sorted({c['id'] for c in row['characters'] if re.search('[\u3040-\u30ff]', c['name'])})
            if untranslated:
                row['untranslatedCharacterIds'] = untranslated
                row['notes'].append('部分角色未提供已确认中文译名，保留游戏原始名称检索；不自动添加猜测译名。')
                row['publicNotes'].append('部分角色名称沿用原版文字，尚无已确认的中文译名。')
        if row['characters']:
            evidence.append({'kind': 'native_character_names', 'logicalPath': TEXT, 'fields': {'name': 0, 'epithet': 3},
                             'format': 'name（epithet）', 'definitionLogicalPath': CHARACTER})
        rows[key] = row
    ensure_keys(rows, parents)
    for path, digest in snapshots:
        if sha(path.read_bytes()) != digest:
            raise ValueError('input changed during generation: ' + str(path))
    if sha((root / 'assets/asset-patch/manifest.json').read_bytes()) != source['manifestSha256']:
        raise ValueError('source manifest changed during generation')
    document = {'schemaVersion': 1, 'source': {'manifestSha256': sha(manifest), 'presentationSha256': sha(presentation_raw),
                                             'catalogSha256': sha(catalog_raw)},
                'resources': resources, 'rows': rows,
                'sourceInputs': {r['path']: r['sha256'] for r in resources if r['kind'] == 'file' and r['root'] == 'repo'},
                'summary': {'parents': len(rows), 'types': dict(Counter(p['type'] for p in parents)),
                            'statuses': dict(Counter(row['status'] for row in rows.values())),
                            'relations': dict(Counter(c['relation'] for row in rows.values() for c in row['characters'])),
                            'equipmentRelations': dict(Counter(c['relation'] for row in rows.values() for c in row['rewards'])),
                            'characters': len(name_cache), 'metadataOnly': True}}
    receipt = {'schemaVersion': 1, 'source': document['source'], 'summary': document['summary'],
               'catalogManifestSha256': catalog['source']['manifestSha256'],
               'mismatches': mismatches, 'nameFailures': name_failures,
               'unavailable': {key: row['notes'] for key, row in rows.items() if row['status'] == 'unavailable'},
               'notApplicable': [key for key, row in rows.items() if row['status'] == 'not_applicable'],
               'winningNativeResources': len(native), 'scope': '全量父项检索关系；不代表玩法、资格、原生页面或设备验收。'}
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    report.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(document['summary'], ensure_ascii=True))


if __name__ == '__main__':
    main()
