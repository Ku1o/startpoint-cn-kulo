#!/usr/bin/env python3
"""Read native parent names and original banners sparsely; never change the CDN or operations state."""
import argparse, hashlib, importlib.util, json, re, struct, sys
from pathlib import Path
sys.dont_write_bytecode = True

EVENTS = ['advent_event', 'ranking_event', 'story_event', 'daily_week_event', 'challenge_dungeon_event',
          'daily_exp_mana_event', 'world_story_event', 'tower_dungeon_event', 'expert_single_event',
          'carnival_event', 'raid_event', 'rush_event', 'solo_time_attack_event', 'hard_multi_event', 'score_attack_event']
RELATED = ['active_mission_event', 'collect_item_event', 'pass_card_event', 'box_gacha',
           'multi_special_exchange_campaign', 'special_exchange_campaign', 'start_dash_exchange_campaign']
# Generated native Values fields, zero-based. Scheduled banner cells retain their original order.
IMAGE_FIELDS = {'gacha': [3], 'pass_card_event': [2], 'active_mission_event': [8],
                'collect_item_event': [12, 14, 15], 'multi_special_exchange_campaign': [6, 7],
                'special_exchange_campaign': [8], 'start_dash_exchange_campaign': [5], 'box_gacha': []}
NAME_TWO = {'advent_event', 'ranking_event', 'story_event', 'world_story_event', 'hard_multi_event'}
CHINESE_DESCRIPTIONS = {'スターヒーローズガチャ': '星之英雄扭蛋', 'マテリアルトレーダー': '素材兑换活动',
                        'キャンペーンミッション': '特别任务活动', '限定込み★4以上扭蛋': '含限定角色的四星及以上扭蛋',
                        '新キャラピックアップガチャ': '新角色精选扭蛋', 'カムバック扭蛋': '回归扭蛋',
                        'バレンタイン纪念关卡': '情人节纪念关卡', 'リセマラ1000万回突破纪念关卡': '刷初始千万次纪念关卡',
                        '斗和キセキ联动Event': '斗和奇迹联动活动', '不諦の魔道士': '永不言弃的魔导士'}
# An explicitly reviewed display order, never an interpretation of original issue numbers or attributes.
RUSH_SAME_NAME_KEYS = ['rush_event:700011', 'rush_event:700012', 'rush_event:700013', 'rush_event:700014',
                       'rush_event:700015', 'rush_event:700016', 'rush_event:700017']

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', required=True); ap.add_argument('--exporter', required=True)
    ap.add_argument('--resource-root')
    ap.add_argument('--output', required=True); ap.add_argument('--evidence', required=True)
    a = ap.parse_args(); repo = Path(a.repo).resolve()
    spec = importlib.util.spec_from_file_location('presentation_native_exporter', a.exporter)
    exporter = importlib.util.module_from_spec(spec); spec.loader.exec_module(exporter)
    resource_root = Path(a.resource_root).resolve() if a.resource_root else repo
    if (resource_root / 'assets/asset-patch/manifest.json').read_bytes() != (repo / 'assets/asset-patch/manifest.json').read_bytes():
        raise ValueError('resource-root chain differs from the target checkout')
    catalog = json.loads((repo / 'assets/content_catalog.json').read_text(encoding='utf8'))
    parents = [row for row in catalog['rows'] if row['type'] in EVENTS + RELATED + ['gacha']]
    logicals = sorted({row['source'] for row in parents})
    masters, source = exporter.resolve(resource_root, logicals)
    parsed = {logical: exporter.parse_rows(raw, logical) for logical, (raw, _) in masters.items()}
    rows = {}; native = {}; image_fields = {}
    gacha_aliases = {}
    for relative in ['assets/gacha.json', 'assets/gacha_cnmod.json', 'assets/gacha_rank_p5b.json', 'assets/gacha_midautumn_2026.json']:
        for ident, value in json.loads((repo / relative).read_text(encoding='utf8')).items():
            gacha_aliases['gacha:' + ident] = (value.get('name', ''), relative)
    for row in parents:
        values = parsed[row['source']].get(str(row['id']))
        if not values or len(values) != 1: raise ValueError('missing/ambiguous native parent ' + row['key'])
        fields = values[0]; native[row['key']] = fields
        name_index = 2 if row['type'] in NAME_TWO else 1
        fields_for_images = IMAGE_FIELDS.get(row['type'], [4, 5] if row['type'] in NAME_TWO else [3, 4])
        candidates = []
        for index in fields_for_images:
            for raw_path in fields[index].replace('\\', '/').split(','):
                logical = raw_path.strip()
                if '/' not in logical or any(char in logical for char in (' ', '\n', ':', '<', '>')) or '..' in logical: continue
                if not logical.endswith('.png'): logical += '.png'
                if logical not in candidates: candidates.append(logical)
        is_box = row['type'] == 'box_gacha'
        title = fields[name_index] if not is_box else '奖励箱池'
        rows[row['key']] = {'title': title, 'type': row['type'], 'nativeName': fields[0] if is_box else title,
            'titleSource': {'kind': 'missing_native_title' if is_box else 'native_master', 'logicalPath': row['source'],
                            'rowId': row['id'], 'fieldIndex': 0 if is_box else name_index},
            'images': candidates, 'gachaPrizeKind': int(fields[13]) if row['type'] == 'gacha' else None}
        image_fields[row['key']] = fields_for_images
        if is_box: rows[row['key']]['subtitle'] = '游戏内资源代号：' + fields[0]
    for key, row in rows.items():
        original = row['title']
        if not re.search('[\u3040-\u30ff]', original): continue
        alias, alias_source = gacha_aliases.get(key, ('', ''))
        if re.search('[\u4e00-\u9fff]', alias) and not re.search('[\u3040-\u30ff]', alias):
            row['title'] = alias
            row['displayTitleSource'] = {'kind': 'native_chinese_alias', 'source': alias_source}
            row['subtitle'] = '旧资料原名：' + original
        else:
            row['title'] = CHINESE_DESCRIPTIONS.get(original, '历史扭蛋' if row['type'] == 'gacha' else '历史活动')
            row['displayTitleSource'] = {'kind': 'descriptive_chinese', 'officialTranslationConfirmed': False}
            row['subtitle'] = '中文说明名称，非已确认官方译名；旧资料原名：' + original
        row['titleSource']['originalText'] = original
    if any(rows.get(key, {}).get('nativeName') != '狂热激战' for key in RUSH_SAME_NAME_KEYS):
        raise ValueError('same-name Rush display group changed; review the explicit disambiguation list')
    for index, key in enumerate(RUSH_SAME_NAME_KEYS, 1):
        rows[key]['subtitle'] = f'同名活动 {index} / 7（后台区分序号，不代表原版期数或属性）'
        rows[key]['subtitleSource'] = {'kind': 'admin_disambiguation', 'sequence': index, 'total': 7,
                                      'meaning': '仅用于区分后台条目，不代表原版期数或属性'}
    # These are explicit native foreign keys, not guesses from similar names or dates.
    for key, fields in native.items():
        typ = rows[key]['type']; index = 18 if typ == 'raid_event' else 14 if typ == 'world_story_event' else None
        if index is None or not fields[index].isdigit(): continue
        box_key = 'box_gacha:' + fields[index]
        if box_key not in rows: continue
        box = rows[box_key]
        if box['titleSource']['kind'] != 'missing_native_title': continue
        box['title'] = rows[key]['title'] + ' · 奖励箱'
        box['titleSource'] = {'kind': 'associated_native_title', 'parentKey': key, 'linkFieldIndex': index,
                              'logicalPath': rows[key]['titleSource']['logicalPath'], 'rowId': int(key.split(':')[1])}
        box['images'] = list(rows[key]['images'])
        box['subtitle'] = '对应活动的原生奖励箱'
    wanted = sorted({logical for row in rows.values() for logical in row['images']})
    images, image_source = exporter.resolve(resource_root, wanted)
    if source['manifestSha256'] != image_source['manifestSha256']: raise ValueError('resource chain changed during presentation build')
    resources = {}; invalid = []; total = 0
    for logical, (raw, identity) in images.items():
        total += len(raw)
        if total > 256 * 1024 * 1024: raise ValueError('presentation image read exceeded bounded 256 MiB budget')
        if len(raw) < 33 or raw[:8] not in [b'\x89png\r\n\x1a\n', b'\x89PNG\r\n\x1a\n'] or raw[12:16] != b'IHDR':
            invalid.append(logical); continue
        width, height = struct.unpack('>II', raw[16:24])
        resources[logical] = dict(identity, member=exporter.member(logical), bytes=len(raw), width=width, height=height)
    missing = []
    for key, row in rows.items():
        row['images'] = [logical for logical in row['images'] if logical in resources]
        if not row['images']:
            row['imageMissingReason'] = '游戏资源未提供可用的独立横幅'
            missing.append(key)
    result = {'schemaVersion': 1, 'source': {'assetVersion': source['assetVersion'], 'manifestSha256': source['manifestSha256']},
              'rows': rows, 'resources': resources}
    Path(a.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    evidence = {'schemaVersion': 1, 'source': result['source'], 'parents': len(rows), 'types': len({r['type'] for r in rows.values()}),
        'withImages': len(rows) - len(missing), 'withoutImages': missing, 'uniqueImages': len(resources), 'imageBytesRead': total,
        'chineseDisplayFallbacks': [key for key, row in rows.items() if row.get('displayTitleSource')],
        'adminDisambiguatedKeys': RUSH_SAME_NAME_KEYS,
        'invalidImageResources': invalid, 'nativeTitleMissing': [key for key, row in rows.items() if row['titleSource']['kind'] == 'missing_native_title'],
        'nativeImageFieldColumns': image_fields,
        'manifestSha256': hashlib.sha256(Path(a.output).read_bytes()).hexdigest(),
        'scope': 'all catalog parent rows, including history; no date filtering, player-state access, CDN write or asset export'}
    Path(a.evidence).parent.mkdir(parents=True, exist_ok=True)
    Path(a.evidence).write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: value for key, value in evidence.items() if key not in ['nativeImageFieldColumns', 'withoutImages']}))

if __name__ == '__main__': main()
