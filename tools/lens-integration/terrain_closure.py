"""Analysis-only adapters for the approved five-boss resource closure.

Single reference points create exactly one ActionHitArea. ActionEvaluator then
evaluates their callback once for that list entry. Other formations retain the
strict generic check; no gameplay payload is rewritten by this adapter.
"""
import copy
import wf_rogue_bundle as bundle


def nested_anchor_errors(layer, cap, receipts):
    errors=[]
    positions,funnels=dict(cap.custom_positions),dict(cap.funnel_groups)
    for f in layer.funnels:
        if f.max_commands and not funnels.get(f.group):
            errors.append(f'layer {layer.layer}: missing FUNNEL_SPAWN{f.group}')
    seen=set()
    def child(kind,code):
        key=f'{kind}|{code}|100'
        if key in seen:return
        seen.add(key);receipt=receipts[key]
        for position in receipt['positions']:
            if positions.get(position)!=1:
                errors.append(f'layer {layer.layer}: {code} missing position {position}')
        for group,count in receipt['funnels'].items():
            if count and not funnels.get(group):
                errors.append(f'layer {layer.layer}: {code} missing FUNNEL_SPAWN{group}')
        for ref in receipt['references']:child(ref['kind'],ref['code'])
    for ref in layer.spawned_refs:child(ref.source_kind,ref.code)
    return errors


def bounded_action(tree):
    tree = copy.deepcopy(tree)
    def visit(value):
        if not isinstance(value, list):
            return value
        if len(value) == 2 and value[0] == 'Command':
            command = value[1]
            if (isinstance(command, list) and len(command) == 12
                    and command[0] == 'CreateReferencePoint'
                    and command[8] == ['Single']):
                return visit(command[11])
        return [visit(child) for child in value]
    return visit(tree)


def spawned_gate(table, action_loader, receipts):
    selected_tables = {
        'Funnel': 'master/battle/boss/funnel/general_funnel.orderedmap',
        'StandardFunnel': 'master/battle/boss/funnel/standard_funnel.orderedmap',
        'Zako': 'master/battle/zako/general_zako.orderedmap',
        'GeneralBoss': 'master/battle/boss/general_boss.orderedmap',
    }
    cache, visiting = {}, set()
    def validate(kind, code, level):
        key = kind, code, level
        if key in cache: return cache[key]
        if key in visiting:
            return bundle.GateResult(False, 'REFERENCE', detail=f'cyclic spawned actor:{key}')
        visiting.add(key)
        try:
            logical = selected_tables[kind]
            node = table(logical)[code]
            tiers = sorted(int(k) for k in node if str(k).isdigit() and int(k) >= level)
            if not tiers: raise ValueError(f'no tier >= {level}')
            selected = tiers[0]
            cells = bundle._cells(node[str(selected)])
            roots = sorted({s.strip() for cell in cells for s in cell.split(',')
                            if s.strip().startswith('battle/action/')})
            closures, summaries = [], []
            positions, references = set(), set()
            if kind != 'GeneralBoss':
                if kind != 'Funnel' or len(cells) != 140:
                    raise ValueError('spawned actor row schema needs separate audit')
                if any('.esdl' in c for c in cells):
                    raise ValueError('spawned ESDL schema needs separate audit')
                positions = {cells[i] for i in (36,40,43,47,51)
                             if cells[i] not in ('', '(None)', '*spawn-point*', '*start-point*')}
                state_positions, references = bundle._state_requirements(cells[37],
                    table('master/battle/boss/funnel/general_funnel_state.orderedmap'))
                # FunnelImpl.initialize registers *start-point* itself.
                positions.update(state_positions - {'*spawn-point*', '*start-point*'})
                if cells[32] not in ('','(None)'):
                    references.add(bundle.SpawnedRef('GeneralBoss',cells[32]))
                for root in roots:
                    summary = bundle._analyze_action_program(root, action_loader, set())
                    summaries.append(summary)
                    references.update(summary.spawned_refs)
                    positions.update(summary.positions)
                    closures.extend(summary.action_closure)
                for ref in references:
                    child = validate(ref.source_kind, ref.code, level)
                    if not child.ok: raise ValueError(child.detail)
            # GeneralBossAlive dependencies must be in the same layer and are
            # already walked by boss_terrain_requirements as primary actors.
            receipts['|'.join(map(str,key))] = {'table':logical,'selected_level':selected,
                'row_columns':len(cells),'action_roots':roots,'action_closure':sorted(set(closures)),
                'positions':sorted(positions),
                'funnels':dict(bundle._summary_sum(summaries).funnels),
                'references':[{'kind':r.source_kind,'code':r.code} for r in sorted(references,key=lambda r:(r.source_kind,r.code))]}
            result = bundle.GateResult(True, selected_level=selected, source_table=logical)
        except (KeyError, TypeError, ValueError, FileNotFoundError) as exc:
            result = bundle.GateResult(False, 'REFERENCE', detail=f'{key}: {exc}')
        finally:
            visiting.remove(key)
        cache[key] = result
        return result
    return validate
