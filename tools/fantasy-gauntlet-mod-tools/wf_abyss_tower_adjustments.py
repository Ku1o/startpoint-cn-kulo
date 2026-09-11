"""Explicit post-roll policies; ordinary curse merge and default RNG stay intact."""
from __future__ import annotations

import copy
from decimal import Decimal
import hashlib
import json
import random

import wf_rogue_build as rb
import wf_rogue_element_channel as channel

POLICY = 'abyss-thunder-free-pf-half-v1'
# These columns are encounter data. Everything else remains in its floor slot.
ENCOUNTER_COLUMNS = {3, 5, 69, 70, *range(71, 81), *range(86, 102)}


def policy_rng(seed: int, purpose: str):
    digest = hashlib.sha256(f'{POLICY}:{seed}:{purpose}'.encode('ascii')).digest()
    return random.Random(int.from_bytes(digest, 'big'))


def select_pf_floors(seed: int, count=15, floors=30):
    if not 0 <= count <= floors:
        raise ValueError('PF 层数越界')
    return sorted(policy_rng(seed, 'pf').sample(range(1, floors + 1), count))


def remove_element(picks: list[dict], excluded: int):
    """Remove only explicitly excluded atoms, preserving all other effects."""
    result, changes = [], []
    for source in picks:
        card = copy.deepcopy(source)
        atoms = card.get('element_resistance', [])
        kept = [a for a in atoms if int(a[0]) != excluded]
        if len(kept) == len(atoms):
            result.append(card)
            continue
        # Refuse a future mixed-effect card rather than silently erase its text.
        unknown = set(card) - {'name', 'text', 'element_resistance', 'element_ban_guarantee'}
        if unknown:
            raise ValueError(f'混合属性卡需独立文案处理: {card["name"]}, {unknown}')
        changes.append({'name': card['name'], 'removed_atoms': [a for a in atoms if int(a[0]) == excluded]})
        if kept:
            card['element_resistance'] = kept
            if card.get('element_ban_guarantee'):
                card['text'] = '·'.join(rb.ELEMENT_DATA_CN[int(a[0])] for a in kept) + '属性封锁补足'
            else:
                card['text'] = '·'.join(rb.ELEMENT_DATA_CN[int(e)] + '属性' + rb.resistance_label(v)
                                        for e, v, _ in kept)
                if card['name'] == '三相封界':
                    card['name'] = '元素封界'
            result.append(card)
    return result, changes


def add_pf_modifier(conditions, delta='-0.15'):
    """Add percentage points AFTER ordinary same-kind max merging.

    This is an explicit modifier, not another rolled curse card: ordinary curse
    merging intentionally rejects opposite signs and does not add magnitudes.
    """
    out = [list(c) for c in conditions]
    kinds = [str(c[0]) for c in out]
    if len(kinds) != len(set(kinds)) or len(out) > 5:
        raise ValueError('初始条件重复或超过 5 槽')
    before = Decimal(out[kinds.index('2')][1]) if '2' in kinds else Decimal(0)
    after = before + Decimal(delta)
    if not before.is_finite() or not after.is_finite():
        raise ValueError('PF 条件强度非法')
    value = format(after.normalize(), 'f') if after else '0'
    if '2' in kinds:
        out[kinds.index('2')][1] = value
    else:
        out.append(['2', value])
    if len(out) > 5:
        raise ValueError('额外 PF 条件超过 5 槽，禁止截断')
    return out, {'kind': 2, 'delta': float(Decimal(delta)), 'before': float(before),
                 'after': float(after), 'channel': 'quest.c71-c80', 'additive': True}


def adjust_floors(original, seed: int):
    if [f['r'] for f in original] != list(range(1, 31)):
        raise ValueError('需要完整有序的 30 层塔配置')
    if any(f.get('adjustment_policy') for f in original):
        raise ValueError('禁止重复施加调校；请从记录的前置版本重建')
    selected = select_pf_floors(seed)
    result, receipts = [], []
    for slot in original:
        r = slot['r']
        source_r = {26: 30, 30: 26}.get(r, r)
        source = original[source_r - 1]
        floor = copy.deepcopy(source)
        floor['r'] = r
        row = copy.deepcopy(slot['row'])
        for i in ENCOUNTER_COLUMNS:
            row[i] = source['row'][i]
        floor['row'] = row
        if r == 26:
            floor['pick']['label'] = floor['pick']['label'].replace('终局Boss·', '领主战·')
        elif r == 30:
            floor['pick']['label'] = floor['pick']['label'].replace('领主战·', '终局Boss·')
        cleaned, removed = remove_element(source['curse']['picks'], 3)
        picks, ban = rb.guarantee_element_bans(cleaned, policy_rng(seed, f'ban:{r}'),
                                              minimum=2, excluded_elements=(3,))
        curse = rb.apply_picks(copy.deepcopy(source['curse']), picks, source['curse'].get('combo'))
        for key in ('hp', 'atk', 'tp', 'fever', 'time', 'gimmick', 'caster', 'casters',
                    'damage_resistance', 'stacked_resistance'):
            if json.dumps(curse[key], sort_keys=True) != json.dumps(source['curse'][key], sort_keys=True):
                raise ValueError(f'第 {r} 层非属性诅咒漂移: {key}')
        totals = rb._resistance_totals_by_target(picks, 'element_resistance')
        assert 3 not in totals and 2 <= len(rb.immunity_axes(picks)[1]) <= 5
        before_totals = rb._resistance_totals_by_target(source['curse']['picks'], 'element_resistance')
        for e, v in before_totals.items():
            if e != 3 and e not in ban['added_banned']:
                assert totals[e] == v
        modifier = None
        if r in selected:
            curse['conds'], modifier = add_pf_modifier(curse['conds'])
            curse['desc'] += ' 「PF调校」PF抗性额外-15个百分点'
        block = channel.encode(totals)
        curse['element_ban_receipt'] = dict(ban, channel='quest_initial_conditions',
            config_block=block, totals=totals, original_non_thunder_effects_preserved=True,
            explicitly_removed_element=3, configuration_verified=True, round=r,
            quest_id=row[0], original_subtitle=slot['row'][3])
        row[3] = curse['desc'] + ' ' + block
        curse['element_ban_receipt']['final_subtitle'] = row[3]
        row[71:81] = ['(None)', ''] * 5
        assert len(curse['conds']) <= 5
        for i, (kind, value) in enumerate(curse['conds']):
            row[71 + 2*i:73 + 2*i] = [str(kind), str(value)]
        floor['curse'] = curse
        floor['adjustment_policy'] = dict(id=POLICY, seed=seed, source_round=source_r,
            removed_thunder=removed, pf_modifier=modifier)
        receipts.append(dict(round=r, source_round=source_r, removed_thunder=removed,
            banned=ban['final_banned'], added_banned=ban['added_banned'],
            element_totals=totals, pf_modifier=modifier, condition_slots=len(curse['conds'])))
        result.append(floor)
    return result, dict(policy=POLICY, seed=seed, pf_floors=selected, floors=receipts)
