"""Audit prepared five-boss scenes with the existing fail-closed terrain gate.

Reads sparse candidate + active-chain resources. Never edits client code or CDN.
Unproved closure is reported as a release gate, not converted to a whitelist.
"""
import argparse
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
import prepare_content as pc
import wf_dsl
import wf_rogue_bundle as bundle
from terrain_closure import bounded_action, spawned_gate, nested_anchor_errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    work = parser.parse_args().work.resolve()
    chain = pc.Chain()
    prepared = pc.readj(work / 'prepare-report.json')
    assert pc.sha(chain.manifest_bytes) == prepared['baseline_manifest_sha256']
    index = {(r['root'], r['rel']): r for r in pc.readj(work / 'resources.json')}
    reads = {}

    @lru_cache(maxsize=None)
    def read(logical):
        key = ('common', pc.hrel(logical))
        row = index.get(key)
        if row:
            payload = (work / 'resources/upload' / key[1]).read_bytes()
            assert pc.sha(payload) == row['sha256']
        else:
            payload = chain.get(key)
        if payload is None: raise FileNotFoundError(logical)
        reads[logical] = {'sha256': pc.sha(payload), 'source': 'candidate' if row else 'active_chain'}
        return payload

    @lru_cache(maxsize=None)
    def table(logical): return bundle.q.parse_node(read(logical))

    def dsl(logical, suffix):
        if not logical.endswith(suffix): logical += suffix
        return wf_dsl.parse_dsl(pc.wf_atf.inflate(read(logical)))['tree']

    def terrain(logical): return dsl(logical, '.amf3.deflate')

    fields = table('master/battle/field_data.orderedmap')
    zones = table('master/battle/zone.orderedmap')
    general = table(bundle.TABLE_LOGICALS['general_boss'])
    standard = table(bundle.TABLE_LOGICALS['standard_boss'])
    states = table('master/battle/boss/general_boss_state.orderedmap')
    action_loader = lambda logical: bounded_action(dsl(logical, '.action.dsl.amf3.deflate'))
    spawned_receipts = {}
    loaders = {'general_boss': general, 'standard_boss': standard, 'general_boss_state': states,
        'action_loader': action_loader,
        'esdl_loader': lambda logical: dsl(logical, '.esdl.amf3.deflate')}
    loaders['spawned_ref_gate'] = spawned_gate(table, action_loader, spawned_receipts)
    scenes = []
    for field in sorted(k for k in fields if k.startswith('mod_five_boss_')):
        caps = bundle.load_terrain_layer_caps(field, fields, zones, terrain)
        slots = bundle.active_boss_slots(field, fields, zones, terrain)
        terrain_path, zone, zone_rows = bundle._field_context(field, fields, zones)
        selected = []
        initial_positions = []
        for slot in slots:
            assert slot.single == slot.multi, f'single/multi roster divergence: {field}/{slot}'
            ref = slot.single
            assert ref is not None and ref.kind in (1, 8), f'unaudited constructor: {slot}'
            # The approved quest uses level 100 and all supplied actors carry
            # an exact 100 row. Do not invent a floor/ceiling fallback.
            row = bundle._cells(general[ref.code]['100'])
            selected.append((slot.layer, slot.slot, 100))
            positions, _ = bundle._state_requirements(row[42], states)
            if row[41] not in ('', '(None)'): positions.add(row[41])
            available = dict(next(c for c in caps if c.layer == slot.layer).custom_positions)
            initial_positions.append({'layer': slot.layer, 'slot': slot.slot, 'boss': ref.code,
                'positions': sorted(positions), 'missing': sorted(p for p in positions if available.get(p) != 1)})
        native = bundle.NativeBossBundle(field, field, field, field, field, zone,
            terrain_path, tuple(c.layer for c in caps), slots, None, '', 'five_boss',
            terrain_caps=caps, selected_levels=tuple(selected), source_level=100,
            active_zone_rows=tuple((c.layer, tuple(bundle._cells(zone_rows[c.layer]))) for c in caps))
        requirements = bundle.boss_terrain_requirements(native, 100, loaders)
        compatibility = bundle.terrain_compatibility(native, native, requirements)
        # The generic checker compares two fields for portability: comparing
        # the same field cannot detect an absent funnel group on both sides.
        # Also require every primary/nested group's presence in this field.
        closure_errors = []
        if requirements.ok:
            for layer in requirements.requirements.layers:
                cap = next(c for c in caps if c.layer == layer.layer)
                closure_errors.extend(nested_anchor_errors(layer,cap,spawned_receipts))
        scenes.append({'field': field, 'terrain': terrain_path, 'slots': [asdict(s) for s in slots],
            'caps': [asdict(c) for c in caps], 'initial_and_state_positions': initial_positions,
            'requirements': asdict(requirements), 'compatibility': asdict(compatibility),
            'nested_terrain_errors': sorted(set(closure_errors))})
    missing = [dict(field=s['field'], **r) for s in scenes for r in s['initial_and_state_positions'] if r['missing']]
    pending = [s['field'] for s in scenes if not s['compatibility']['ok'] or s['nested_terrain_errors']]
    report = {'baseline_version': chain.tail, 'scene_count': len(scenes),
        'position_errors': missing, 'closure_pending_scenes': pending, 'scenes': scenes,
        'resource_reads': reads, 'spawned_receipts': spawned_receipts,
        'status': 'passed' if not pending and not missing else 'release_held'}
    pc.savej(work / 'five-boss-terrain-audit-v2.json', report)
    print(f"scenes={len(scenes)}, position_errors={len(missing)}, closure_pending={len(pending)}, resources_read={len(reads)}")
    for reason in sorted({s['requirements']['detail'] for s in scenes if not s['requirements']['ok']}): print(reason)
    for reason in sorted({e for s in scenes for e in s['nested_terrain_errors']}): print(reason)
    if missing: print(missing)


if __name__ == '__main__': main()
