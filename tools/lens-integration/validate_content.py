"""Validate a sparse prepared graft without activating it or editing SWFs."""
import argparse
import json
import re
from pathlib import Path
import prepare_content as pc
import wf_dsl
import wf_dsl_sig
from wf_siete_balance import _normalize_for_signature


def strings(value):
    if isinstance(value, str): yield value
    elif isinstance(value, list):
        for child in value: yield from strings(child)
    elif isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from strings(child)


def table_strings(payload):
    try:
        for child in pc.rawmap(payload).values(): yield from table_strings(child)
    except Exception:
        try: yield from strings(pc.csvrows(payload))
        except Exception: return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    inventory = pc.readj(work / 'resources.json')
    recovered = pc.readj(work / 'recovered-paths.json')
    prepared = pc.readj(work / 'prepare-report.json')
    chain = pc.Chain()
    assert pc.sha(chain.manifest_bytes) == prepared['baseline_manifest_sha256'], 'rebase candidate against the changed active chain'
    blobs = {}
    dsl_results, references, baseline_references = [], set(), set()
    for row in inventory:
        key = row['root'], row['rel']
        payload = (work / 'resources' / pc.ROOTS[row['root']] / row['rel']).read_bytes()
        assert pc.sha(payload) == row['sha256']
        before = chain.get(key)
        assert (pc.sha(before) if before is not None else None) == row['before_sha256']
        logical = row['logical'] or recovered.get(row['rel'])
        if logical:
            assert pc.hrel(logical) == row['rel']
            row['logical'] = logical
        blobs[key] = payload
        if payload[1:4] in (b'png', b'PNG'):
            assert payload[:8] == pc.wf_assets.PNG_FAKE, f'unencoded PNG: {logical}'
            image = pc.Image.open(pc.io.BytesIO(pc.wf_assets.png_decode_stored(payload)))
            image.load()
        if key[0] != 'common': continue
        if logical and logical.endswith('.orderedmap'):
            references.update(table_strings(payload))
            if before is not None: baseline_references.update(table_strings(before))
        try: tree = wf_dsl.parse_dsl(pc.wf_atf.inflate(payload))['tree']
        except (ValueError, IndexError, pc.zlib.error, UnicodeDecodeError): continue
        references.update(strings(tree))
        if not isinstance(tree, list) or not tree or tree[0] != 'ActionDsl': continue
        wf_dsl_sig.validate_action_dsl(_normalize_for_signature(tree, logical or row['rel']))
        decoded = wf_dsl.parse_dsl(wf_dsl.encode_amf3(tree))['tree']
        assert decoded == tree
        wf_dsl_sig.validate_action_dsl(_normalize_for_signature(decoded, logical or row['rel']))
        dsl_results.append({'logical': logical, 'rel': row['rel'], 'signature': 'pass', 'round_trip': True})
    checked, missing, preexisting_missing = [], [], []
    for text in sorted(references):
        for logical in re.findall(r'battle/(?:action|terrain)/[A-Za-z0-9_/$.-]+', text):
            if logical.startswith('battle/action/'):
                if '$' not in logical: continue
                if not logical.endswith('.action.dsl.amf3.deflate'): logical += '.action.dsl.amf3.deflate'
            elif not logical.endswith('.amf3.deflate'): logical += '.amf3.deflate'
            key = ('common', pc.hrel(logical))
            exists = key in blobs or key in chain.index
            if exists: checked.append(logical)
            elif logical.removesuffix('.action.dsl.amf3.deflate').removesuffix('.amf3.deflate') in baseline_references:
                preexisting_missing.append(logical)
            else: missing.append(logical)
    assert not missing, f'missing referenced DSL/terrain: {missing}'
    report = {'status': 'sparse_payload_checks_passed_release_held_for_client', 'baseline_version': chain.tail,
        'resources': len(inventory), 'dsl_signature_and_round_trip': dsl_results,
        'action_terrain_references': sorted(set(checked)), 'unresolved_paths': [r for r in inventory if not r['logical']],
        'preexisting_missing_references': sorted(set(preexisting_missing)),
        'ios_pairs': pc.readj(work / 'ios-pairs.json'),
        'remaining_release_gates': ['user_paused_swf_integration', 'boss_terrain_compatibility_closure', 'resolve_unmapped_payload_provenance', 'device_acceptance']}
    pc.savej(work / 'resources.json', inventory)
    pc.savej(work / 'validation-report.json', report)
    print(json.dumps({k: report[k] for k in ['status', 'baseline_version', 'resources']}))
    print(f'DSL: {len(dsl_results)}; verified direct action/terrain references: {len(set(checked))}; unresolved names: {len(report["unresolved_paths"])}')


if __name__ == '__main__': main()
