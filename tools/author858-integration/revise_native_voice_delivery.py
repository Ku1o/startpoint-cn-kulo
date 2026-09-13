"""Revise our unpublished part 2 to use native multi-voice without an APK dependency."""
import argparse
import copy
import io
import json
import zipfile
from pathlib import Path

import prepare as m
import native_voices


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--work', type=Path, required=True); args = ap.parse_args()
    w = args.work.resolve(); report_path = w / 'apply-report.json'
    release = m.readj(report_path); prepared = m.readj(w / 'prepared.json')
    active = m.REPO / 'assets/asset-patch/active' / release['archive']['name']
    raw_zip = active.read_bytes(); assert m.sha(raw_zip) == release['archive']['sha256']
    manifest_path = m.REPO / 'assets/asset-patch/manifest.json'; raw_manifest = manifest_path.read_bytes()
    assert m.sha(raw_manifest) == release['manifest_after_sha256']
    manifest = json.loads(raw_manifest); patch, = [x for x in manifest['patches'] if x.get('version') == '1.4.107']
    chain = m.p.Chain()
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as z: payloads = {name: z.read(name) for name in z.namelist()}
    old_assets = copy.deepcopy(prepared['assets']); index = {(x['root'], x['logical']): x for x in old_assets}
    prefix = native_voices.PREFIX
    mapping, sources = [], {}
    for dest_suffix, source_suffix in enumerate(native_voices.FORMAL):
        src = prefix + f'battle/skill_{source_suffix}.mp3'
        sources[dest_suffix] = chain.get(('common', m.p.hrel(src)))
        assert sources[dest_suffix] is not None
        mapping.append({'source_logical': src, 'logical': prefix + f'battle/skill_{dest_suffix}.mp3',
                        'sha256': m.sha(sources[dest_suffix])})
    assert len({x['sha256'] for x in mapping}) == 5
    old_trial_hashes = {index['common', prefix + f'battle/skill_{i}.mp3']['sha256'] for i in (2, 3)}
    assert not old_trial_hashes & {x['sha256'] for x in mapping}
    numbered = {prefix + f'battle/skill_{i}.mp3' for i in range(7)}
    final_assets = [x for x in old_assets if x['logical'] not in numbered]
    for i in range(2, 7):
        entry = index['common', prefix + f'battle/skill_{i}.mp3']
        assert entry['before_sha256'] is None, 'published baseline has numbered voice; needs a different migration'
        del payloads[entry['member']]
    for i in range(2, 5):
        entry = copy.deepcopy(index['common', prefix + f'battle/skill_{i}.mp3'])
        data = sources[i]; entry.update(size=len(data), sha256=m.sha(data))
        payloads[entry['member']] = data; final_assets.append(entry)
    # No client installed the provisional source-tree part. Resource 5/6 did
    # not exist in the incoming baseline; removing them needs no delete entry.
    m.writej(w / 'native-voice-mapping.json', {'mapping': mapping, 'requires_apk_change': False,
        'skill_reader': 'CharacterShortVoiceLogic/generateVoicePaths', 'max_native_entries': 512,
        'ready_behavior': 'existing native normal/matched ready paths; no added alternation',
        'extra_ready_audio': 'retained as author resources; native reader does not select _alt_1'})
    removed_keys = {('common', m.p.hrel(prefix + f'battle/skill_{i}.mp3')) for i in (5, 6)}
    def effective(root, logical):
        key = (root, m.p.hrel(logical)); member = m.p.member(key)
        if key in removed_keys: return None
        return payloads[member] if member in payloads else chain.get(key)
    native_voices.verify(w, effective)
    members = sorted(payloads); candidate_zip = w / 'native-voice-revision.zip'
    assert not candidate_zip.exists()
    with zipfile.ZipFile(candidate_zip, 'x') as z:
        for member in members:
            info = zipfile.ZipInfo(member, (2026, 9, 13, 0, 0, 0)); info.external_attr = 0o644 << 16
            z.writestr(info, payloads[member], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    with zipfile.ZipFile(candidate_zip) as z:
        assert z.testzip() is None and z.namelist() == members
        assert all(z.read(name) == raw for name, raw in payloads.items())
    untouched = [x for x in old_assets if x['logical'] not in numbered]
    assert all(m.sha(payloads[x['member']]) == x['sha256'] for x in untouched)
    final_assets.sort(key=lambda x: (x['root'], x['logical']))
    prepared['assets'] = final_assets
    prepared['status'] = 'installed_native_voice_delivery'
    prepared['native_voice_mapping'] = mapping
    prepared['requires_apk_change'] = False
    archive = {'name': active.name, 'size': candidate_zip.stat().st_size,
               'sha256': m.sha(candidate_zip.read_bytes()), 'members': len(members), 'files': members}
    integrity, = [x for x in patch['archive_integrity'] if x['name'] == active.name]
    integrity.clear(); integrity.update(archive)
    patch['archive_size'] = sum(x['size'] for x in patch['archive_integrity'])
    patch['files'] = sorted({name for x in patch['chain'] for name in
                            (members if x == active.name else zipfile.ZipFile(active.with_name(x)).namelist())})
    patch['changes'].append('火狮王五条正式技能语音重排为原生连续编号，通过 CDN 接入；准备音沿用原生播放，不新增 APK 轮换逻辑。')
    revised_manifest = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    history = w / 'history/apk-dependent-prototype'; history.mkdir(parents=True, exist_ok=False)
    for name in ('prepared.json', 'static-verification.json', 'selection-verification.json',
                 'candidate-runtime-verification.json', 'apply-report.json'):
        (history / name).write_bytes((w / name).read_bytes())
    (history / 'manifest.json').write_bytes(raw_manifest)
    # Preserve our provisional unpublished bytes for traceability, then replace
    # only our part. The other task's archive and all server files stay exact.
    assert manifest_path.read_bytes() == raw_manifest and active.read_bytes() == raw_zip
    (history / active.name).write_bytes(raw_zip)
    candidate_zip.replace(active); manifest_path.write_bytes(revised_manifest)
    for row in final_assets:
        (w / 'prepared-client' / row['member']).write_bytes(payloads[row['member']])
    m.writej(w / 'prepared.json', prepared)
    release.update(status='installed_native_voice_delivery_pending_final_checks', archive=archive,
        prepared_sha256=m.sha((w / 'prepared.json').read_bytes()), manifest_after_sha256=m.sha(revised_manifest),
        requires_apk_change=False, extra_ready_alternation_enabled=False,
        provisional_apk_candidate_excluded=True, native_voice_revision_history=str(history))
    m.writej(report_path, release)
    audit = m.REPO / 'assets/asset-patch/audit/author858-selected-1.4.107'
    for name in ('prepared.json', 'native-voice-mapping.json', 'native-voice-verification.json'):
        (audit / name).write_bytes((w / name).read_bytes())
    m.writej(audit / 'report.json', release)
    print(json.dumps({k: v for k, v in archive.items() if k != 'files'} | {'requires_apk_change': False,
        'other_asset_payloads_preserved': len(untouched), 'server_files_unchanged': True}, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
