"""Collect bound verification receipts for the final local CDN-only integration."""
import argparse
import ast
import copy
import json
from pathlib import Path

import prepare as m


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--work', type=Path, required=True); args = ap.parse_args()
    w = args.work.resolve(); audit = m.REPO / 'assets/asset-patch/audit/author858-selected-1.4.107'
    prepared = m.readj(w / 'prepared.json'); prepared_sha = m.sha((w / 'prepared.json').read_bytes())
    release = m.readj(w / 'apply-report.json')
    manifest = m.REPO / 'assets/asset-patch/manifest.json'
    assert m.sha(manifest.read_bytes()) == release['manifest_after_sha256']
    receipts = ('static-verification.json', 'selection-verification.json', 'candidate-runtime-verification.json',
                'installed-runtime-verification.json', 'native-voice-verification.json')
    for name in receipts:
        result = m.readj(w / name)
        assert result['status'] == 'passed' and result['prepared_sha256'] == prepared_sha, name
    route = m.readj(w / 'release-verification.json')
    assert route['status'] == 'passed' and route['manifest_sha256'] == release['manifest_after_sha256']
    changes = m.readj(w / 'server-changes.json'); server_report = []
    for row in prepared['server_files']:
        path = m.REPO / row['path']; current = path.read_bytes()
        assert m.sha(current) == row['sha256']
        old = m.readj(w / 'before-server' / row['path']); new = json.loads(current)
        selected = [x for x in changes if x['file'] == row['path']]
        restored = copy.deepcopy(new)
        for change in selected:
            key = change['key']; assert new[key] == change['after']
            if key in old: restored[key] = old[key]
            else: del restored[key]
        assert restored == old, ('unrelated server keys changed', row['path'])
        assert set(old) <= set(new)
        server_report.append({'path': row['path'], 'selected_keys': len(selected),
            'unaffected_keys_preserved': len(old) - sum(x['key'] in old for x in selected),
            'sha256': row['sha256']})
    chain = m.p.Chain(); assert chain.tail == '1.4.107'
    part1 = m.readj(m.REPO / 'assets/asset-patch/audit/weapon-caps-practice-hp-1.4.107/report.json')
    for scope in part1['scope']:
        assert m.sha(chain.get(('common', m.p.hrel(scope['logical'])))) == scope['after_sha256']
    for file in Path(__file__).parent.glob('*.py'): ast.parse(file.read_text('utf-8'), filename=str(file))
    author_note = Path('F:/给合并方的说明.md').read_bytes()
    assert m.sha(author_note) == 'dad2b681c5057aa87643e231c7e590928027064a43ef04c8146deb34c6839460'
    (audit / 'author-confirmation.md').write_bytes(author_note)
    note_receipt = {'source': 'F:/给合并方的说明.md', 'sha256': m.sha(author_note),
        'author_confirmed_exact_fix': True, 'donor_archive': 'assets/full68-005.zip',
        'original_resource_sha256': '04d452d5af27ab06f5fce3a034d308a9e32d87d0166364a8f94f6e822dd7f5d8',
        'apk_change_required_for_dsl_fix': False, 'author_note_is_evidence_not_execution_authority': True}
    m.writej(audit / 'author-confirmation.json', note_receipt)
    m.writej(audit / 'server-scope-verification.json', {'status': 'passed', 'files': server_report,
        'unrelated_server_keys_preserved': True, 'existing_root_keys_preserved': True, 'player_database_accessed': False})
    for name in (*receipts, 'release-verification.json', 'prepared.json', 'native-gachas.json',
                 'native-voice-mapping.json', 'technical-fixes.json'):
        (audit / name).write_bytes((w / name).read_bytes())
    m.writej(audit / 'client-runtime-inspection.json', m.readj(w / 'client/inspection.json'))
    semantic = {'source_swf_sha256': m.readj(w / 'client/inspection.json')['swf_sha256'],
        'signature_only_nullable_parameters': [
            {'command': 'CreateSummonsMultiball', 'parameter_1based': 13, 'meaning': 'null selects context SLv; ActionEvaluator case 36'},
            {'command': 'MultiballNumberVariable', 'parameter_1based': 3, 'meaning': 'null matches all multiballs; ActionEvaluator case 107 -> SquadImpl.matchMultiball'},
        ], 'serialized_nulls_preserved': True,
        'summer_bai_damage_origin': 'CreateHitArea parameter 24: 2 is ability damage; multiplier 75 in both forms',
        'all_other_summer_dsl_values_preserved': True,
        'method_hashes_in': 'client-runtime-inspection.json', 'device_tested': False}
    m.writej(audit / 'semantic-evidence.json', semantic)
    files = [*prepared['server_files'],
             {'path': 'assets/asset-patch/manifest.json', 'sha256': release['manifest_after_sha256']},
             {'path': 'assets/asset-patch/active/' + release['archive']['name'], 'sha256': release['archive']['sha256']}]
    m.writej(audit / 'release-files.json', {'runtime_files': files,
        'same_version_required_part1': part1['archive'], 'requires_current_prior_chain': True,
        'apk_or_ipa_included': False, 'loose_production_included': False,
        'commit_or_sync_authorized': False, 'cloud_overlay_created': False})
    release.update(status='complete_locally_unreleased', requires_apk_change=False,
        verification_receipts=[*receipts, 'release-verification.json', 'server-scope-verification.json'],
        donor_fix_confirmed_by_author=True, source_git=m.readj(w / 'git-finish.json'),
        runtime_files_copied=[], runtime_backup_created=False, cloud_overlay_created=False,
        player_database_accessed=False, remaining_device_validation=['new character battle/boards',
          'campus Nephtim multiball creation/despawn gain', 'voice playback and illustrations'])
    # Avoid copying other tasks' full dirty-file inventory into a deliverable.
    release['source_git'] = {k: release['source_git'][k] for k in ('branch', 'head', 'upstream')}
    m.writej(w / 'apply-report.json', release); m.writej(audit / 'report.json', release)
    print(json.dumps({'status': release['status'], 'part': 2, 'edge': release['edge'],
        'assets': len(prepared['assets']), 'server_files': len(prepared['server_files']),
        'apk_required': False, 'author_fix_confirmed': True, 'unrelated_server_keys_preserved': True,
        'source_git': release['source_git'], 'audit': str(audit)}, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
