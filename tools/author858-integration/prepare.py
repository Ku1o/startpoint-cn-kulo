"""Prepare the user-selected author 858 content against the current active chain.

This command writes sparse candidates only to --work. Donor programs are never
executed. Applying files and registering the same-version part is a separate step.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import io
import json
import sys
import zipfile
import zlib
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools/lens-integration'))
import prepare_content as p
import wf_dsl
import wf_battle_atlas_repack as atlas
import optimize_battle_atlases as opt

NEW = {'119989', '149989', '169989', '149988'}
BOSSES = {'119993', '119994', '119995', '129993', '129994', '129995', '129996',
          '129998', '139996', '149991', '149992', '149993', '149994', '159999', '169993'}
FULL = NEW | BOSSES
DATES = {'129998', '149994', '159999', '149993', '119970', '129970', '139970', '149970'}
VOICES = {'119996', '169999'}
DONOR_SHA = 'a3c5960500c56b8000fb117d4457ea14dceadd7354b70dd66a202036f322fe68'
EXTENSIONS = {
    'character.json': ['character_rank_p5b.json'],
    'cdndata/character.json': ['cdndata/character_rank_p5b.json'],
    'cdndata/character_text.json': ['cdndata/character_text_rank_p5b.json'],
    'gacha.json': ['gacha_cnmod.json', 'gacha_rank_p5b.json'],
    'mana_node.json': ['mana_node_cnmod.json', 'mana_node_rank_p5b.json'],
    'mana_board.json': ['mana_board_cnmod.json'],
}

def readj(path): return json.loads(path.read_text('utf-8-sig'))
def sha(raw): return hashlib.sha256(raw).hexdigest()
def writej(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', 'utf-8')
def write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)

def node_bytes(node, old=None):
    if 'children' in node:
        rows = p.rawmap(old)
        for key, value in node['children'].items():
            rows[key] = node_bytes(value, rows.get(key))
        return p.packmap(rows)
    if node.get('empty'): return b''
    raw = base64.b64decode(node['raw'], validate=True)
    assert p.csvrows(raw) == node['csv']
    if old is not None:
        try:
            if p.csvrows(old) == node['csv']: return old
        except (zlib.error, UnicodeDecodeError): pass
    return raw

def decoded(raw):
    if raw == b'': return {'empty': True}
    try: return {'csv': p.csvrows(raw)}
    except (zlib.error, UnicodeDecodeError):
        return {'children': {k: decoded(v) for k, v in p.rawmap(raw).items()}}

def owner_ids(logical, key, node, codes):
    result = {cid for code, cid in codes.items()
              if key == cid or (key.startswith(cid) and key[len(cid):].isdigit()) or code in key}
    if logical.endswith('/unique_condition.orderedmap'):
        text = json.dumps(node, ensure_ascii=False)
        result.update(cid for code, cid in codes.items() if code in text)
    return result

def merge_ticket_pixels(old_png, old_atlas, donor_png, donor_atlas):
    before = atlas.decode_png(old_png)
    after = before.copy()
    donor = atlas.decode_png(donor_png)
    old_frames = {x['n']: x for x in atlas.decode_atlas(old_atlas)}
    donor_frames = {x['n']: x for x in atlas.decode_atlas(donor_atlas)}
    changed = [n for n in old_frames.keys() & donor_frames.keys()
               if opt.visible_signature(before, [old_frames[n]]) != opt.visible_signature(donor, [donor_frames[n]])]
    assert len(changed) == 2, changed
    for name in changed:
        a, b = old_frames[name], donor_frames[name]
        assert 'gacha' in name or 'ticket' in name, name
        assert (a['w'], a['h']) == (b['w'], b['h']) == (20, 20)
        assert all(a.get(k) == b.get(k) for k in set(a) | set(b) if k not in ('x', 'y'))
        crop = donor.crop((b['x'], b['y'], b['x'] + b['w'], b['y'] + b['h']))
        after.paste(crop, (a['x'], a['y']))
    for name, frame in old_frames.items():
        source, wanted = (donor, donor_frames[name]) if name in changed else (before, frame)
        assert opt.visible_signature(after, [frame]) == opt.visible_signature(source, [wanted]), name
    stream = io.BytesIO(); after.save(stream, format='PNG')
    encoded = p.wf_assets.png_encode(stream.getvalue())
    assert atlas.decode_png(encoded).tobytes() == after.tobytes()
    return encoded, {'changed_frames': sorted(changed), 'preserved_frames': len(old_frames) - 2,
                     'preserved_metadata_sha256': sha(old_atlas), 'dimensions': list(after.size)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--review', type=Path, required=True)
    ap.add_argument('--donor', type=Path, required=True)
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--skip-ios', action='store_true', help='prepare CPU jobs without executing them')
    args = ap.parse_args()
    work, review = args.work.resolve(), args.review.resolve()
    assert not work.is_relative_to((REPO / '.cdn').resolve())
    work.mkdir(parents=True, exist_ok=True)
    assert sha(args.donor.read_bytes()) == DONOR_SHA, 'donor identity changed'
    chain = p.Chain()
    assert chain.tail == '1.4.107', f'review same-version allocation first: {chain.tail}'
    print('Preparing against', chain.tail, 'with', len(chain.index), 'effective assets', flush=True)
    payload = readj(review / 'metadata/tables/client_payload.json')['tables']
    server_payload = readj(review / 'metadata/tables/server_payload.json')['files']
    manifest = readj(review / 'metadata/asset-manifest.json')
    roster = readj(review / 'metadata/roster/roster.json')['characters']
    codes = {x['code_name']: str(x['character_id']) for x in roster}
    full_codes = [k for k, v in codes.items() if v in FULL]
    asset_by_member = {x['member']: x for x in manifest['assets']}
    asset_by_key = {(x['root'], x['logical']): x for x in manifest['assets']}
    donor = {}
    with zipfile.ZipFile(args.donor) as outer:
        for part in manifest['archives']:
            raw = outer.read(part['path']); assert sha(raw) == part['sha256']
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                for name in z.namelist():
                    a = asset_by_member[name]; raw = z.read(name)
                    assert sha(raw) == a['sha256'] and len(raw) == a['size']
                    donor[a['root'], a['logical']] = raw
    current_cache, outgoing, changes, table_changes = {}, {}, [], []
    def current(root, logical):
        key = (root, logical)
        if key not in current_cache: current_cache[key] = chain.get((root, p.hrel(logical)))
        return current_cache[key]
    def put(root, logical, raw, reason):
        old = current(root, logical)
        if old == raw: return
        outgoing[root, logical] = raw
        changes.append({'root': root, 'logical': logical, 'reason': reason,
                        'before_sha256': sha(old) if old is not None else None, 'after_sha256': sha(raw)})
    for logical, table in payload.items():
        old = current('common', logical); rows = p.rawmap(old); original = dict(rows)
        for key, node in table['keys'].items():
            owners = owner_ids(logical, key, node, codes)
            select = bool(owners & FULL)
            if logical.endswith('/mana_board2_open_condition.orderedmap') and key in DATES: select = True
            if key in VOICES and logical in ('master/character/character.orderedmap',
                    'master/character/character_speech.orderedmap', 'master/character/character_text.orderedmap',
                    'master/character/character_gacha_sound.orderedmap'): select = True
            if logical == 'master/skill/switched_action_skill.orderedmap' and key in (
                    'ginovi_voice_ready', 'lion_swordman_reborn_voice_ready'): select = True
            if logical == 'master/character/character_text.orderedmap' and key == '149990': select = True
            if logical == 'master/skill/action_skill.orderedmap' and key == 'white_tiger_summer': select = True
            if logical == 'master/string/custom_ability_string.orderedmap' and key == 'change_skill_white_wolf_gerald': select = True
            if key == '179999' and logical in ('master/character/full_shot_image_attribute.orderedmap',
                    'master/generated/character_image.orderedmap'): select = True
            if logical == 'master/generated/trimmed_image.orderedmap' and key == 'character/black_wolf_knight_wt26/ui/full_shot_1440_1920_1': select = True
            if not select: continue
            before = rows.get(key); after = node_bytes(node, before)
            if before is not None and decoded(before) == decoded(after): after = before
            rows[key] = after
            if before != after:
                table_changes.append({'logical': logical, 'key': key, 'owners': sorted(owners),
                                      'before': decoded(before) if before is not None else None,
                                      'after': decoded(after)})
        # Narrow the existing broad exclusion while keeping all unrelated restrictions.
        if logical == 'master/string/ui_string.orderedmap':
            key = 'character_voice_exclude'; values = p.csvrows(rows[key]); tokens = values[0][0].split('|')
            if 'ruin_girl' in tokens:
                i = tokens.index('ruin_girl')
                replacements = ['character/ruin_girl/voice/', 'character/ruin_girl_3halfanv/voice/',
                    'character/ruin_girl_halfanv/voice/', 'character/ruin_girl_smr21/voice/',
                    'bgm/character_unique/ruin_girl', 'sound_effect/unique/se_ruin_girl_special_attack']
                tokens[i:i+1] = [x for x in replacements if x not in tokens]
                values[0][0] = '|'.join(tokens); rows[key] = p.packcsv(values)
                table_changes.append({'logical': logical, 'key': key, 'before': decoded(original[key]), 'after': decoded(rows[key])})
        if rows != original:
            raw = p.packmap(rows); assert p.rawmap(raw) == rows
            assert all(rows[k] == v for k, v in original.items() if not any(x['logical'] == logical and x['key'] == k for x in table_changes))
            put('common', logical, raw, 'selected client table keys')
    candidate = readj(review / 'gacha-review/selected-gacha-candidate-20260913.json')['pools']
    for gid, pool in candidate.items():
        prefix = 'cnmod_abyss_limited_gacha' if gid == '990001' else 'cnmod_ashen_verdict_gacha'
        for bucket, entries in pool['pool'].items():
            rank = 6 - int(bucket); name = f'{prefix}_character_{rank}'
            logical = f'master/gacha_odds/{name}.orderedmap'
            rows = p.rawmap(current('common', logical))
            values = [[str(x['id']), str(x['rank']), str(x['odds']), str(x['isRateUp']).lower(),
                       str(x['isLimited']).lower(), str(x['isExchangeable']).lower(), str(x['trialReadingForced']).lower()] for x in entries]
            rows[name] = p.packmap({str(i): p.packcsv([row]) for i, row in enumerate(values)})
            put('common', logical, p.packmap(rows), 'confirmed gacha rules')
        name = f'{prefix}_rarity'; logical = f'master/gacha_odds/{name}.orderedmap'
        rows = p.rawmap(current('common', logical))
        rows[name] = node_bytes(payload[logical]['keys'][name], rows.get(name))
        put('common', logical, p.packmap(rows), 'author rank rates')
    note = (review / '卡池注意事项-改写稿.md').read_text('utf-8')
    import html
    for title, logical in [('深渊限定扭蛋注意事项', 'rich_text/cnmod_abyss_limited_gacha_note.html.deflate'),
                           ('深渊竞速池注意事项', 'rich_text/cnmod_ashen_verdict_gacha_note.html.deflate')]:
        section = note.split('## ' + title + '\n', 1)[1].split('\n## ', 1)[0]
        paragraphs = [x[2:] for x in section.splitlines() if x.startswith('- ')]
        rendered = '<html><body>\n' + '<br/><br/>\n'.join(html.escape(x) for x in paragraphs) + '\n</body></html>'
        put('common', logical, zlib.compress(rendered.encode('utf-8'), wbits=-15), 'rewrite final pool notice')
    builtin = readj(review / 'current-apk-builtin-check.json')
    builtin_same = {x['logical'] for x in builtin['rows'] if x['current_apk_matches']}
    for (root, logical), raw in donor.items():
        a = asset_by_key[root, logical]
        owned_ids = set(map(str, a['character_ids']))
        take = any(code in logical for code in full_codes) or (len(owned_ids) == 1 and bool(owned_ids & FULL) and a['classification'] == 'owned')
        if current(root, logical) is None and owned_ids & NEW and logical not in builtin_same: take = True
        if logical.startswith(tuple(f'character/{x}/ui/' for x in ('white_tiger_summer', 'lion_swordman_reborn', 'claude_wolf_assassin_ex'))): take = True
        if logical.startswith(('character/ginovi/voice/', 'character/lion_swordman_reborn/voice/')): take = True
        if logical in ('dynamic/gacha_list_banner/cnmod_ashen_verdict_gacha.png', 'dynamic/gacha_banner/cnmod_ashen_verdict_gacha.png'): take = True
        if logical.startswith('battle/action/skill/action/rare5/') and any(logical.endswith(f'/{code}${code}_{form}.action.dsl.amf3.deflate') for code in ('white_tiger_summer', 'white_wolf_gerald') for form in (1, 2)): take = True
        if logical.startswith(('rich_text/', 'item/')): take = False
        # Native generateVoicePaths reads a contiguous skill_0.. sequence. Keep
        # the five approved formal recordings and omit the donor trial slots.
        if logical.startswith('character/lion_swordman_reborn/voice/battle/skill_') and logical.rsplit('/', 1)[-1] in {f'skill_{i}.mp3' for i in range(7)}:
            take = False
        if take: put(root, logical, raw, 'approved character media or dependency')
    voice_mapping = []
    for dest_suffix, source_suffix in enumerate((0, 1, 4, 5, 6)):
        source = f'character/lion_swordman_reborn/voice/battle/skill_{source_suffix}.mp3'
        dest = f'character/lion_swordman_reborn/voice/battle/skill_{dest_suffix}.mp3'
        raw = donor['common', source]
        put('common', dest, raw, 'native contiguous formal voice sequence; exclude trial recordings')
        voice_mapping.append({'source_logical': source, 'logical': dest, 'sha256': sha(raw)})
    writej(work / 'native-voice-mapping.json', {'mapping': voice_mapping, 'requires_apk_change': False,
        'skill_reader': 'CharacterShortVoiceLogic/generateVoicePaths', 'max_native_entries': 512,
        'ready_behavior': 'existing native normal/matched ready paths; no added alternation',
        'extra_ready_audio': 'retained as author resources; native reader does not select _alt_1'})
    # The donor has an ActionDslExpression.Block where the native constructor
    # requires IfTargetNotFound. This is a type correction, not a balance edit.
    fix_logical = 'battle/action/skill/action/ability_skill/ruin_girl_campus$ruin_girl_campus_multiball_direct.action.dsl.amf3.deflate'
    original_fix = donor['common', fix_logical]
    fix_tree = wf_dsl.parse_dsl(zlib.decompress(original_fix, -15))['tree']
    original_tree = copy.deepcopy(fix_tree)
    command = fix_tree[11][1][1][1]
    assert command[0] == 'FindAllSubjects' and command[8] == ['Block', []]
    command[8] = ['DoNothing']
    fix_raw = zlib.compress(wf_dsl.encode_amf3(fix_tree), wbits=-15)
    assert wf_dsl.parse_dsl(zlib.decompress(fix_raw, -15))['tree'] == fix_tree
    restored = copy.deepcopy(fix_tree); restored[11][1][1][1][8] = ['Block', []]
    assert restored == original_tree
    put('common', fix_logical, fix_raw, 'repair invalid IfTargetNotFound enum at FindAllSubjects p8')
    writej(work / 'technical-fixes.json', [{'logical': fix_logical, 'command': 'FindAllSubjects',
        'parameter_1based': 8, 'before': ['Block', []], 'after': ['DoNothing'],
        'donor_sha256': sha(original_fix), 'selected_sha256': sha(fix_raw),
        'all_other_tree_values_preserved': True}])
    png_key, atlas_key = ('common', 'item/sprite_sheet.png'), ('common', 'item/sprite_sheet.atlas.amf3.deflate')
    png, ticket_report = merge_ticket_pixels(current(*png_key), current(*atlas_key), donor[png_key], donor[atlas_key])
    put(*png_key, png, 'replace two blue ticket frames; preserve atlas and custom icons')
    ios_jobs = []
    for (root, logical), raw in donor.items():
        if root != 'android': continue
        required = ('android', logical) in outgoing or (any(code in logical for code in full_codes) and current('ios', logical) is None)
        if not required: continue
        source_logical = logical.replace('.atf.deflate', '.png')
        source = donor.get(('medium', source_logical)) or donor.get(('common', source_logical))
        assert source, ('missing iOS PNG source', logical)
        source = p.wf_assets.png_decode_stored(source)
        output = work / 'ios' / logical
        ios_jobs.append((logical, source, raw, str(output)))
    writej(work / 'ios-jobs.json', [{'logical': x[0], 'source_png_sha256': sha(x[1]), 'android_sha256': sha(x[2]), 'output': x[3]} for x in ios_jobs])
    ios_receipts = []
    if not args.skip_ios:
        with ProcessPoolExecutor(max_workers=4) as executor:
            for receipt in executor.map(p.ios_job, ios_jobs):
                ios_receipts.append(receipt)
                put('ios', receipt['logical'], Path(receipt['path']).read_bytes(), 'paired iOS ETC2 cut-in')
                print('iOS paired', receipt['logical'], flush=True)
    server_before, server_after, server_changes = {}, {}, []
    def get_server(rel):
        if rel not in server_after:
            path = REPO / 'assets' / rel
            raw = path.read_bytes() if path.exists() else b'{}'
            server_before[rel] = raw; server_after[rel] = json.loads(raw)
        return server_after[rel]
    def set_server(base, key, value):
        for rel in [base, *EXTENSIONS.get(base, [])]:
            dest = get_server(rel)
            if rel != base and key not in dest: continue
            if dest.get(key) != value:
                server_changes.append({'file': 'assets/' + rel, 'key': key, 'before': dest.get(key), 'after': value})
                dest[key] = copy.deepcopy(value)
    for base in ('character.json', 'cdndata/character.json', 'cdndata/character_text.json', 'mana_board.json', 'mana_node.json'):
        for cid in sorted(FULL): set_server(base, cid, server_payload[base][cid])
    for cid in sorted(VOICES):
        set_server('cdndata/character.json', cid, server_payload['cdndata/character.json'][cid])
        set_server('cdndata/character_text.json', cid, server_payload['cdndata/character_text.json'][cid])
    set_server('cdndata/character_text.json', '149990', server_payload['cdndata/character_text.json']['149990'])
    for gid, value in candidate.items(): set_server('gacha.json', gid, value)
    assets_report = []
    for (root, logical), raw in sorted(outgoing.items()):
        if logical.endswith('.png'):
            assert raw[:8] == p.wf_assets.PNG_FAKE
            with p.Image.open(io.BytesIO(p.wf_assets.png_decode_stored(raw))) as im: im.load()
        if '.dsl.amf3.deflate' in logical:
            tree = wf_dsl.parse_dsl(zlib.decompress(raw, -15))['tree']
            assert wf_dsl.parse_dsl(wf_dsl.encode_amf3(tree))['tree'] == tree
        member = p.member((root, p.hrel(logical)))
        write(work / 'prepared-client' / member, raw)
        old = current(root, logical)
        if old is not None: write(work / 'before-client' / member, old)
        assets_report.append({'root': root, 'logical': logical, 'member': member, 'size': len(raw),
                              'sha256': sha(raw), 'before_sha256': sha(old) if old is not None else None})
    server_files = []
    for rel, obj in server_after.items():
        if json.loads(server_before[rel]) == obj: continue
        raw = (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        write(work / 'before-server/assets' / rel, server_before[rel])
        write(work / 'prepared-server/assets' / rel, raw)
        server_files.append({'path': 'assets/' + rel, 'before_sha256': sha(server_before[rel]), 'sha256': sha(raw)})
    writej(work / 'table-changes.json', table_changes)
    writej(work / 'server-changes.json', server_changes)
    writej(work / 'changes.json', changes)
    writej(work / 'ios-pairs.json', ios_receipts)
    report = {'status': 'prepared_not_installed', 'donor_sha256': DONOR_SHA, 'baseline_version': chain.tail,
              'same_version_edge': ['1.4.106', '1.4.107'], 'manifest_before_sha256': sha(chain.manifest_bytes),
              'assets': assets_report, 'server_files': server_files, 'ticket_atlas': ticket_report,
              'ios_required': len(ios_jobs), 'ios_completed': len(ios_receipts), 'ios_skipped': args.skip_ios,
              'full_character_ids': sorted(FULL), 'new_character_ids': sorted(NEW),
              'save_impact': 'four new character IDs and 41 nodes each; existing IDs preserved; no schema or player writes'}
    writej(work / 'prepared.json', report)
    print(json.dumps({'assets': len(assets_report), 'bytes': sum(x['size'] for x in assets_report),
                     'server_files': len(server_files), 'client_keys': len(table_changes), 'ios': len(ios_jobs),
                     'roots': dict(Counter(x['root'] for x in assets_report))}, ensure_ascii=False), flush=True)

if __name__ == '__main__': main()
