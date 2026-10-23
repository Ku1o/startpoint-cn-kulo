#!/usr/bin/env python3
"""Classify fixed-July candidates left outside the evidence-bound initialization."""
import argparse, collections, json, hashlib, importlib.util, sys, zipfile
from pathlib import Path

EVENT_TYPES = ['advent_event', 'ranking_event', 'story_event', 'daily_week_event', 'challenge_dungeon_event',
               'daily_exp_mana_event', 'world_story_event', 'tower_dungeon_event', 'expert_single_event',
               'carnival_event', 'raid_event', 'rush_event', 'solo_time_attack_event', 'hard_multi_event', 'score_attack_event']
RELATED_TYPES = ['active_mission_event', 'collect_item_event', 'pass_card_event', 'box_gacha',
                 'multi_special_exchange_campaign', 'special_exchange_campaign', 'start_dash_exchange_campaign']
START, END = 1752940800000, 1753027200000
def in_day(row):
    return not row.get('personalWindow') and (row['originalStartMs'] is None or row['originalStartMs'] <= START) and (row['originalEndMs'] is None or row['originalEndMs'] >= END - 1000)

def coverage_main(a):
    """Select by the fixed day and real child windows, never the old capture-time candidate booleans."""
    sys.dont_write_bytecode = True
    repo = Path(a.repo).resolve()
    catalog = json.loads((repo / 'assets/content_catalog.json').read_text(encoding='utf8'))
    plan_path = repo / 'assets/content_july_controls.json'
    plan = json.loads(plan_path.read_text(encoding='utf8'))
    controls = {row['key']: row for row in plan['controls']}
    rows = {row['key']: row for row in catalog['rows']}
    # The current HardMulti server table additionally contains exactly the known core bosses.
    # The original seasonal rows were compared with the unchanged native rows before this refresh.
    core_quests = {2080001,2081001,2082001,2083001,2084001,2085001,2086001,2087001,2088001,
                   2035001,2037001,2038001,2039001,2040001,2041001,2025001,2026001,2027001,
                   2028001,2029001,2030001,2051001,2052001,2053001,2054001,2055001,2056001}
    hard_source = 'assets/hard_multi_event_quest.json'
    hard_bytes = (repo / hard_source).read_bytes()
    hard_table = json.loads(hard_bytes)
    seasonal = {int(key.split(':')[1]) for key, parent in catalog['questMap'].items() if parent.startswith('hard_multi_event:')}
    if {int(key) for key in hard_table} != seasonal | core_quests: raise ValueError('unexpected HardMulti seasonal/core source set')
    current_hard_sha = hashlib.sha256(hard_bytes).hexdigest()
    if catalog['serverResources'][hard_source]['sha256'] != current_hard_sha:
        catalog['serverResources'][hard_source]['sha256'] = current_hard_sha
        catalog['fixedJulyDefinitionRefresh'] = {'reason': '27 independently excluded core boss additions; original 12 seasonal native/server rows unchanged',
            'source': hard_source, 'sourceSha256': current_hard_sha, 'excludedCoreQuestIds': sorted(core_quests)}
    spec = importlib.util.spec_from_file_location('july_catalog_exporter', a.exporter)
    exporter = importlib.util.module_from_spec(spec); spec.loader.exec_module(exporter)
    # Native Values getters are the authority for these columns; do not scan for date-looking strings.
    columns = {'rush_event': (7, 8), 'raid_event': (7, 8), 'score_attack_event': (7, 8),
               'expert_single_event': (7, 8), 'carnival_event': (7, 8),
               'solo_time_attack_event': (6, 7), 'daily_week_event': (4, 5)}
    categories = {typ: cats for typ, _, _, _, _, _, cats in exporter.TABLES}
    quest_records = collections.defaultdict(list)
    for logical, identity in catalog['resources'].items():
        if not logical.startswith('master/quest/event/') or not logical.endswith('_quest.orderedmap'): continue
        stem = Path(logical).name[:-len('.orderedmap')]
        typ = stem.replace('_boss_battle_quest', '').replace('_single_quest', '').replace('_quest', '')
        if typ not in EVENT_TYPES: continue
        cats = [19] if stem == 'world_story_event_boss_battle_quest' else [18] if typ == 'world_story_event' else categories[typ]
        with zipfile.ZipFile(repo / identity['archive']) as archive: raw = archive.read(identity['member'])
        if hashlib.sha256(raw).hexdigest() != identity['sha256']: raise ValueError('catalog child receipt replaced: ' + logical)
        start_col, end_col = columns.get(typ, (5, 6))
        for event, members in exporter.nested_rows(raw, logical, 2).items():
            parent = rows.get(f'{typ}:{event}')
            if not parent or not in_day(parent): continue
            for member, values in members.items():
                if len(values) != 1: raise ValueError('ambiguous native quest row: ' + logical + '/' + member)
                value = values[0]
                start, end = exporter.timestamp(value[start_col]), exporter.timestamp(value[end_col])
                eligible = (start is None or start <= START) and (end is None or end >= END - 1000)
                for category in cats:
                    key = f'{category}:{value[0]}'
                    if catalog['questMap'].get(key) != parent['key']: raise ValueError('quest mapping differs: ' + key)
                    quest_records[parent['key']].append({'key': key, 'source': logical, 'row': member,
                        'startMs': start, 'endMs': end, 'fixedDayCandidate': eligible})
    targets = [row for row in catalog['rows'] if row['type'] in EVENT_TYPES + RELATED_TYPES + ['gacha'] and in_day(row)]
    def override(evidence, **scope): return dict(enabled=True, endsAtMs=None, readiness='verified', evidence=evidence, **scope)
    for row in targets:
        key, typ = row['key'], row['type']
        old = controls.get(key)
        actions = dict(old['actionOverrides']) if old else {}
        if typ in EVENT_TYPES:
            scope = sorted(record['key'] for record in quest_records[key] if record['fixedDayCandidate'])
            if not scope: raise ValueError('no target-day native child quest scope: ' + key)
            evidence = 'Native parent and child target-day windows; exact original quest mapping; existing unlock/payment/weekday/settlement rules retained'
            actions.update(visible=override(evidence), enter=override(evidence, questKeys=scope))
            if typ == 'rush_event': actions['claim'] = override(evidence, questKeys=scope)
        elif typ == 'gacha':
            evidence = 'Fixed-day ordinary non-personal pool; native/server definition matched; existing pool/payment/ticket/earned-point rules retained'
            actions.update({action: override(evidence) for action in ['visible', 'enter', 'exchange']})
        elif typ == 'active_mission_event':
            evidence = 'Fixed-day original active mission instance; exact mission scope; durable evaluator/qualification/reward ledger retained'
            scope = sorted(row.get('missionKeys', []))
            if not scope: raise ValueError('active mission scope absent: ' + key)
            actions.update(visible=override(evidence), enter=override(evidence, missionKeys=scope), claim=override(evidence, missionKeys=scope))
        elif typ == 'box_gacha':
            evidence = 'Fixed-day original box definition and reset policy; original ticket deduction, box progression and durable stock retained'
            actions.update({action: override(evidence) for action in ['visible', 'enter', 'claim']})
        elif typ == 'pass_card_event' and row['id'] == 14:
            # Proven battle facts: sent emotion; advent multiplayer; exact ordinary-boss selectors.
            # Rescue mission 7:56 keeps earned claim rights until its native acceptance timing is decided.
            actions['enter'] = dict(actions['enter'], missionKeys=sorted(set(actions['enter']['missionKeys']) | {'7:55', '8:81', '8:85'}))
        elif typ in ['special_exchange_campaign', 'start_dash_exchange_campaign']:
            evidence = 'Existing-ticket exchange only; matched native definition and saved qualification; no ticket grant, purchase or new entitlement inferred'
            actions['exchange'] = override(evidence)
        elif not old:
            raise ValueError('unreviewed associated candidate requires an explicit rule: ' + key)
        if row.get('definitionEvidence', {}).get('status') != 'matched' and not old:
            raise ValueError('unmatched new candidate definition: ' + key)
        controls[key] = {'key': key, 'group': 'permanent', 'expectedDefinitionDigest': row['definitionDigest'],
                         'expectedServerDefinitionDigest': row['serverDefinitionDigest'],
                         'evidence': 'Fixed 2025-07-20 parent/child closure; original business qualification retained', 'actionOverrides': actions}
    ordered = list(dict.fromkeys([row['key'] for row in plan['controls']] + [row['key'] for row in targets]))
    plan['controls'] = [controls[key] for key in ordered]
    plan['planVersion'] = 2
    plan['previousInitializationPlanDigest'] = '3cffb5dea4436042b3487e2a0cb37a7ff324c1c826698f9da6bb04a6b5eb5446'
    records = []
    for row in catalog['rows']:
        if row['type'] not in EVENT_TYPES + RELATED_TYPES + ['gacha']: continue
        control = controls.get(row['key'])
        records.append({'key': row['key'], 'name': row['name'], 'type': row['type'], 'fixedDayCandidate': in_day(row),
            'sourceStartMs': row['originalStartMs'], 'sourceEndMs': row['originalEndMs'],
            'personalWindow': row.get('personalWindow', False), 'controlled': control is not None,
            'enabledActions': [name for name, value in control['actionOverrides'].items() if value['enabled']] if control else [],
            'exchangeOnlyExistingRights': row['type'] in ['special_exchange_campaign', 'start_dash_exchange_campaign'] and in_day(row),
            'quests': quest_records.get(row['key'], []),
            'missionScopes': {action: value['missionKeys'] for action, value in control['actionOverrides'].items() if 'missionKeys' in value} if control else {}})
    source_evidence = {}
    if a.gacha_closure:
        source_evidence['gachaOddsClosure'] = {'file': Path(a.gacha_closure).name,
            'sha256': hashlib.sha256(Path(a.gacha_closure).read_bytes()).hexdigest()}
    pending = []
    if a.remaining_audit:
        previous = json.loads(Path(a.remaining_audit).read_text(encoding='utf8'))
        pending = [dict(row, category=category) for category, group in previous['categories'].items()
                   for row in group['rows'] if row['key'] not in controls]
    result = {'schemaVersion': 2, 'referenceDate': '2025-07-20', 'timeZone': 'UTC+08:00',
              'scope': 'fixed-day parent and child candidates; player unlock, weekday, personal and transaction eligibility remain runtime business checks',
              'typeCounts': {typ: {'total': sum(r['type'] == typ for r in records),
                                  'fixedDay': sum(r['type'] == typ and r['fixedDayCandidate'] for r in records)}
                             for typ in EVENT_TYPES + RELATED_TYPES + ['gacha']}, 'rows': records,
              'planControls': len(plan['controls']), 'sourceEvidence': source_evidence,
              'remainingSeparateCatalogReview': pending,
              'partialMissionScopes': [{'key': row['key'], 'claimOnlyMissionKeys': sorted(set(row['missionScopes'].get('claim', []))
                                      - set(row['missionScopes'].get('enter', [])))} for row in records
                                      if row['fixedDayCandidate'] and row['missionScopes'].get('claim')
                                      and set(row['missionScopes']['claim']) - set(row['missionScopes'].get('enter', []))],
              'notDeviceAcceptance': True}
    plan['sourceEvidence']['fixedDayCoverageSha256'] = hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if a.build_plan:
        (repo / 'assets/content_catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    Path(a.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'types': len(result['typeCounts']), 'fixedDayCandidates': len(targets), 'planControls': len(plan['controls']),
                      'eligibleQuestScopes': sum(record['fixedDayCandidate'] for rows in quest_records.values() for record in rows),
                      'excludedQuestScopes': sum(not record['fixedDayCandidate'] for rows in quest_records.values() for record in rows), 'planWritten': a.build_plan}))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--audit')
    ap.add_argument('--output', required=True)
    ap.add_argument('--campaign-capabilities')
    ap.add_argument('--repo')
    ap.add_argument('--exporter')
    ap.add_argument('--build-plan', action='store_true')
    ap.add_argument('--gacha-closure')
    ap.add_argument('--remaining-audit')
    a = ap.parse_args()
    if a.repo:
        if not a.exporter: ap.error('--repo requires --exporter')
        return coverage_main(a)
    if not a.audit: ap.error('--audit or --repo is required')
    audit = json.loads(Path(a.audit).read_text(encoding='utf8'))
    campaign = ({row['key']: row for row in json.loads(Path(a.campaign_capabilities).read_text(encoding='utf8'))['records']}
                if a.campaign_capabilities else {})
    blocked = {row['key']: row for row in audit['blocked']}
    next_evidence = {
        'shop_stock_mismatch': 'Resolve exact client cumulative/once limit against durable server stock and old player history.',
        'shop_ownership_rule_unproven': 'Prove the client equipment-only possession-one check in the live shop route.',
        'shop_reward_or_cost_definition_mismatch': 'Resolve mismatched reward and missing server reward/cost definition.',
        'shop_parent_current_definition_changed': 'Review the current complete parent child set and mapping delta before opening exchange.',
        'exchange_rule_matched_but_no_new_ticket_or_entitlement_proof': 'Existing-ticket exchange is matched; do not infer ticket purchase or new eligibility.',
        'mission_progress_and_claim_scope_unreviewed': 'Check each mission key, durable progress, claim rule and action guard.',
        'pool_or_box_transaction_scope_unreviewed': 'Check current odds/box rows, transaction guard and retained rights by key.',
        'mode_specific_entry_and_settlement_scope_unreviewed': 'Check current quest/entry mapping and settlement behavior for each mode.'}
    groups = collections.defaultdict(list)
    for row in audit['remainingCandidates']:
        key, typ = row['key'], row['key'].split(':')[0]
        detail = blocked.get(key, {})
        if detail.get('reason') == 'prior action/resource audit incomplete':
            issues = detail.get('issues', [])
            missing = detail.get('missing', [])
            if any('cumulativeStock' in issue for issue in issues): category = 'shop_stock_mismatch'
            elif any('equipment_only_possession_one' in issue for issue in missing): category = 'shop_ownership_rule_unproven'
            else: category = 'shop_reward_or_cost_definition_mismatch'
        elif detail.get('reason') == 'parent exact dependencies changed': category = 'shop_parent_current_definition_changed'
        elif typ in ('special_exchange_campaign', 'start_dash_exchange_campaign'):
            category = 'exchange_rule_matched_but_no_new_ticket_or_entitlement_proof'
        elif typ in ('mission_daily', 'mission_event', 'active_mission_event'):
            category = 'mission_progress_and_claim_scope_unreviewed'
        elif typ in ('gacha', 'box_gacha'): category = 'pool_or_box_transaction_scope_unreviewed'
        else: category = 'mode_specific_entry_and_settlement_scope_unreviewed'
        current = campaign.get(key)
        entry = {'key': key, 'type': typ, 'issues': detail.get('issues', []),
                                 'missing': detail.get('missing', []), 'changedDependencies':
                                 detail.get('details', {}).get('details', []) if isinstance(detail.get('details'), dict) else [],
                                 'capabilities': current['serverCapabilities'] if current else row.get('capabilities', []),
                                 'currentDefinitionReady': current['definitionReady'] if current else None}
        entry['historicalReviewGaps' if current else 'priorGaps'] = row.get('priorGaps', [])
        groups[category].append(entry)
    result = {'schemaVersion': 1, 'referenceDate': audit['referenceDate'],
              'remainingCount': len(audit['remainingCandidates']),
              'currentCampaignCapabilityReceipt': Path(a.campaign_capabilities).name if a.campaign_capabilities else None,
              'categories': {name: {'count': len(rows), 'nextEvidence': next_evidence[name], 'rows': rows}
                             for name, rows in sorted(groups.items())},
              'scope': 'offline classification; unreviewed modes can be checked independently; no activation grant'}
    Path(a.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({name: len(rows) for name, rows in sorted(groups.items())}))

if __name__ == '__main__':
    main()
