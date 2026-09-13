"""Append missing custom mech acquisition routes to the effective client index.

Prepare sparse evidence with --work; --apply-source registers the checked CDN
edge in the source repository. No runtime, SWF, reward or player data is written.
"""
from __future__ import annotations

import argparse
import copy
import io
import json
import re
import subprocess
import zipfile
from pathlib import Path

import prepare_content as p
import fix_five_boss_icon_closure as icons
import five_boss_art_contract as art

BASE = '1.4.105'
VERSION = '1.4.106'
ARCHIVE = f'pinball-{BASE}-{VERSION}-1-mech-item-sources.zip'
AUDIT = f'assets/asset-patch/audit/mech-item-sources-{VERSION}'
SEARCH = 'master/search/item_quest_search.orderedmap'
ITEM = 'master/item/item.orderedmap'
HARD = 'master/quest/event/hard_multi_event_quest.orderedmap'
BOSS = 'master/quest/boss_battle_quest.orderedmap'
STAGE = 'master/quest/boss_battle_stage_node.orderedmap'
SCORE = 'master/reward/score_reward.orderedmap'
RARE = 'master/reward/rare_score_reward.orderedmap'
# The material's element differs from the enemy's. These are the actual server
# reward contracts, not a name/element-based guess.
TARGETS = {
    '40408': (1001001, 7000010, 700010),
    '40409': (1002001, 7000011, 700011),
    '40410': (1003001, 7000012, 700012),
    '40407': (1004001, 7000013, 700013),
    '40412': (1005001, 7000014, 700014),
    '40411': (1006001, 7000015, 700015),
    '10000095': (1060005, 11000948, None),
    '10000096': (1060005, 11000948, 3002),
}


def runtime_contract():
    """Use the public gameplay accessors, including their winning data sources."""
    code = """
const a = require('./out/lib/assets');
const hard = [1001001,1002001,1003001,1004001,1005001,1006001];
const quests = Object.fromEntries(hard.map(id => [id,a.getHardMultiEventQuest(id)]));
quests[1060005] = a.getBossBattleQuestSync(1060005);
const rare = {};
for (const q of Object.values(quests)) for (const row of q.scoreRewardGroup) {
    if (row.type === 1) rare[row.id] = a.getRareScoreRewardGroup(row.id);
}
console.log(JSON.stringify({quests,rare}));
"""
    result = subprocess.run(['node', '-e', code], cwd=p.REPO, capture_output=True,
                            text=True, encoding='utf-8', timeout=30, check=True)
    return json.loads(result.stdout)


def sources_from_rewards(runtime, read):
    hard = p.rawmap(read(HARD))
    boss = p.rawmap(p.rawmap(read(BOSS))['1'])
    score, rare = p.rawmap(read(SCORE)), p.rawmap(read(RARE))
    sources = {}
    for item, (quest_id, group_id, rare_id) in TARGETS.items():
        quest = runtime['quests'][str(quest_id)]
        assert quest['scoreRewardGroupId'] == group_id, ('runtime group drift', item)
        client_scores = [p.csvrows(raw)[0] for raw in p.rawmap(score[str(group_id)]).values()]
        if rare_id is None:
            rows = [r for r in quest['scoreRewardGroup'] if r['type'] == 0
                    and r['reward_type'] == 0 and str(r['id']) == item]
            assert len(rows) == 1 and rows[0]['count'] > 0, ('missing runtime drop', item)
            weight = rows[0]['count']
            assert any(r[1:5] == ['0', '0', item, str(weight)] for r in client_scores)
        else:
            pools = [r for r in quest['scoreRewardGroup'] if r['type'] == 1 and r['id'] == rare_id]
            assert len(pools) == 1 and 0 < pools[0]['rarity'] <= 1, ('missing rare pool', item)
            rewards = runtime['rare'][str(rare_id)]
            assert len(rewards) == 1 and rewards[0]['type'] == 0 and str(rewards[0]['id']) == item
            assert rewards[0]['count'] > 0
            # Client sorting hint uses the configured base rate. It is not a UI
            # probability claim and does not change the server's roll semantics.
            weight = pools[0]['rarity'] * rewards[0]['count']
            assert any(r[1] == '1' and r[6] == str(rare_id)
                       and float(r[7]) == pools[0]['rarity'] for r in client_scores)
            client_rare = [p.csvrows(raw)[0] for raw in p.rawmap(rare[str(rare_id)]).values()]
            assert len(client_rare) == 1 and client_rare[0][1:4] == ['0', item, str(rewards[0]['count'])]
        if quest_id == 1060005:
            ref = ['2', '1', '60', '5', str(quest_id)]
            row = p.csvrows(p.rawmap(boss['60'])['5'])[0]
            assert row[70] == str(group_id)
            assert row[7:12] == ['2', '1', '60', '4', '1060004'], 'previous difficulty gate drift'
        else:
            event = str(quest_id // 1000)
            # Master QuestReferenceIdKind.HardMultiEvent = 18. Server API quest
            # category 26 is a DIFFERENT enum and must never go in this table.
            ref = ['18', event, '', '1', str(quest_id)]
            row = p.csvrows(p.rawmap(hard[event])['1'])[0]
            assert row[7:12] == ['7', '1', '', '38', '1038'], 'story unlock gate drift'
        assert row[0] == str(quest_id), 'wrong quest'
        assert row[5] == '2025-07-10 12:00:00' and row[6] == '(None)', 'closed/historical quest'
        sources[item] = [ref + [format(weight, '.12g')]]
    return sources


def build_index(before, sources):
    rows = p.rawmap(before)
    for item, source in sources.items():
        assert item not in rows, ('already indexed; review new preimage', item)
        rows[item] = p.packcsv(source)
    return p.packmap(rows)


def validate_index(before, after, runtime, read):
    expected = sources_from_rewards(runtime, read)
    old, new = p.rawmap(before), p.rawmap(after)
    assert set(new) - set(old) == set(TARGETS), 'missing or unexpected source keys'
    assert all(new.get(k) == v for k, v in old.items()), 'existing source changed'
    for key, rows in expected.items():
        assert p.csvrows(new[key]) == rows, ('wrong acquisition source', key)
    return {'preserved_search_keys': len(old), 'new_search_keys': len(expected),
            'new_source_rows': sum(map(len, expected.values()))}


def validate_icons(read, additional_ids=()):
    items = p.rawmap(read(ITEM))
    atlases = {n: icons.codec.decode_atlas(read(n + '.atlas.amf3.deflate')) for n in icons.PRELOADED}
    stage = p.csvrows(p.rawmap(p.rawmap(read(STAGE))['1'])['60'])[0]
    required = set(TARGETS) | {str(i) for i in range(40401, 40407)} | set(stage[7:10]) | set(map(str, additional_ids))
    checks = []
    for item in sorted(required, key=int):
        row = p.csvrows(items[item])[0]
        matches = [(name, frame) for name, frames in atlases.items() for frame in frames if frame['n'] == row[4]]
        assert len(matches) == 1, ('small icon not preloaded', item, row[4])
        name, frame = matches[0]
        assert frame['w'] > 0 and frame['h'] > 0
        image = icons.strict_png(read(name + '.png'))
        x1, y1, x2, y2 = icons.rect(frame)
        assert 0 <= x1 < x2 <= image.width and 0 <= y1 < y2 <= image.height
        checks.append({'item': item, 'icon': row[4], 'atlas': name})
    return checks


def audit_unindexed(read):
    """Inventory every concrete score/rare item, not just the mech allowlist."""
    index, items = p.rawmap(read(SEARCH)), p.rawmap(read(ITEM))
    score = p.readj(p.REPO / 'assets/score_reward.json')
    rare = p.readj(p.REPO / 'assets/rare_score_reward.json')
    referenced = set()
    for path in (p.REPO / 'assets').glob('*quest.json'):
        for row in p.readj(path).values():
            if isinstance(row, dict):
                referenced.add(str(row.get('scoreRewardGroupId')))
    missing = {}
    for group, rows in score.items():
        for row in rows:
            rewards = [dict(type=row.get('reward_type'), id=row.get('id'))] if row['type'] == 0 else rare.get(str(row['id']), [])
            for reward in rewards:
                item = str(reward.get('id'))
                if reward.get('type') == 0 and item in items and item not in index:
                    entry = missing.setdefault(item, dict(name=p.csvrows(items[item])[0][2], groups=[]))
                    if group not in entry['groups']: entry['groups'].append(group)
    for item, row in missing.items():
        row['referenced_by_quest_score_group'] = bool(set(row['groups']) & referenced)
        row['repaired_here'] = item in TARGETS
    assert {k for k, v in missing.items() if v['referenced_by_quest_score_group']} == set(TARGETS)
    return missing


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--apply-source', action='store_true')
    args = ap.parse_args()
    work = args.work.resolve()
    assert work.is_relative_to(Path('F:/codex/work').resolve())
    work.mkdir(parents=True, exist_ok=True)
    chain = p.Chain()
    assert chain.tail == BASE, 'select the exact current preimage; do not rewrite an old edge'
    cache = {}
    def read(name):
        if name not in cache:
            cache[name] = chain.get(('common', p.hrel(name)))
            assert cache[name] is not None, ('missing resource', name)
        return cache[name]
    runtime = runtime_contract()
    before = read(SEARCH)
    sources = sources_from_rewards(runtime, read)
    after = build_index(before, sources)
    checks = validate_index(before, after, runtime, read)
    checks['preloaded_icons'] = validate_icons(read)
    inventory = audit_unindexed(read)
    checks['previous_mod_display_contract'] = art.validate_display(read)
    member = p.member(('common', p.hrel(SEARCH)))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        info = zipfile.ZipInfo(member, (2026, 9, 12, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, after)
    payload = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        assert z.testzip() is None and z.namelist() == [member] and z.read(member) == after
        validate_index(before, z.read(member), runtime, read)
    integrity = dict(name=ARCHIVE, size=len(payload), sha256=p.sha(payload), members=1, files=[member])
    manifest = copy.deepcopy(chain.manifest)
    manifest['cdn_version'] = VERSION
    manifest['patches'].append(dict(id=f'mech-item-sources-{VERSION}', type='patch',
        name='机兵蒸气核与菲诺梅那材料入手来源',
        description='补齐六种蒸气核及全能齿轮、融珠蒸气核的原生关卡跳转；保留既有来源、解锁条件和掉落。',
        version=VERSION, depends_on=BASE, enabled=True, archive=ARCHIVE, archive_size=len(payload),
        chain=[ARCHIVE], archive_integrity=[integrity], files=[member], created_at='2026-09-12',
        audit=dict(directory=AUDIT, report='report.json')))
    art.validate_manifest(manifest)
    excluded = [str(f) for f in (p.REPO / '.cdn/cn').resolve().glob('archive-*/*.zip')
                if '-full' not in f.parent.name and
                (not (match := re.match(r'pinball-1\.4\.\d+-1\.4\.(\d+)-(\d+)-', f.name)) or int(match[1]) > 54)]
    report = dict(base_version=BASE, version=VERSION, archive=integrity, checks=checks,
        sources=sources, unindexed_reward_audit=inventory, source_reads=chain.reads,
        excluded_nonbaseline_cdn_archives=excluded, before_sha256=p.sha(before), after_sha256=p.sha(after),
        source_manifest_before_sha256=p.sha(chain.manifest_bytes), runtime_synced=False, device_tested=False,
        swf_changed=False, save_impact='仅新增查询索引；物品/关卡 ID、库存、存档 V1/V2 和数据库均不变。',
        sorting_hint='按配置基础掉落权重生成，仅供原生排序，不改变服务端随机数或奖励。')
    report['source_paths'] = ['assets/asset-patch/manifest.json',
        f'assets/asset-patch/active/{ARCHIVE}', f'assets/asset-patch/{member}', f'{AUDIT}/report.json']
    report['source_applied'] = args.apply_source
    for name, raw in cache.items():
        dest = work / 'before' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
    (work / ARCHIVE).write_bytes(payload)
    p.savej(work / 'runtime-contract.json', runtime)
    p.savej(work / 'report.json', report)
    p.savej(work / 'manifest.after.json', manifest)
    (work / 'manifest.before.json').write_bytes(chain.manifest_bytes)
    if args.apply_source:
        assert (p.REPO / 'assets/asset-patch/manifest.json').read_bytes() == chain.manifest_bytes
        dest = p.REPO / 'assets/asset-patch/active' / ARCHIVE
        loose = p.REPO / 'assets/asset-patch' / member
        audit = p.REPO / AUDIT
        assert not dest.exists() and not audit.exists(), 'refuse existing deliverable'
        # The native direct-download route prefers this sparse local copy. Keep
        # it equal to the archive; cloud overlays still exclude loose resources.
        assert loose.read_bytes() == before, 'direct-download preimage differs from active chain'
        cdn = (p.REPO / '.cdn').resolve()
        for path in [dest, loose, audit, p.REPO / 'assets/asset-patch/manifest.json']:
            assert path.resolve().is_relative_to(p.REPO.resolve()) and not path.resolve().is_relative_to(cdn)
        dest.write_bytes(payload)
        loose.write_bytes(after)
        p.savej(audit / 'report.json', report)
        p.savej(p.REPO / 'assets/asset-patch/manifest.json', manifest)
        final = p.Chain()
        assert final.tail == VERSION and final.get(('common', p.hrel(SEARCH))) == after
        assert loose.read_bytes() == after
        assert all(final.get(('common', p.hrel(n))) == raw for n, raw in cache.items() if n != SEARCH)
    print(json.dumps(dict(archive=integrity, checks={k: v for k, v in checks.items() if k in
        ['preserved_search_keys', 'new_search_keys', 'new_source_rows']}, source_applied=args.apply_source)))


if __name__ == '__main__':
    main()
