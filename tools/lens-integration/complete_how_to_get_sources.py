"""Complete the explicitly approved, unpublished .105 -> .106 resource edge.

The old .106 archive is hash-locked. --apply-source replaces only that edge;
published predecessors, the runtime mirror and pristine CDN remain untouched.
"""
from __future__ import annotations
import argparse
import copy
import io
import json
import math
import subprocess
import zipfile
from pathlib import Path

import prepare_content as p
import fix_mech_item_sources as mech
import build_how_to_get_sources as previous

OLD_ARCHIVE_SHA = 'f80e7e886100c64041f0929e0b482a775a3d8dadc305bb263a5fb98dd6331d3a'
RUSH = previous.RUSH
EXPERT = 'master/quest/event/expert_single_event_quest.orderedmap'
STAR_NOTE = '入手方式：追忆挑战各关首次达到SS评价时获得3个，每关仅可领取一次；重复通关不会再次获得该奖励。入手方法中的关卡仍保留原有解锁与挑战次数限制。'


def runtime_contract():
    result = subprocess.run(['node', str(Path(__file__).with_name('export_acquisition_contract.cjs'))],
        cwd=p.REPO, capture_output=True, text=True, encoding='utf-8', timeout=30, check=True)
    return json.loads(result.stdout)


def required_sources(runtime, read):
    """Derive each item/quest pair, including already indexed ordinary items."""
    result = {}
    groups = {}
    def add(item, ref, weight, group):
        key = str(item)
        assert len(ref) == 5 and math.isfinite(weight) and weight >= 0
        by_ref = result.setdefault(key, {})
        ref = tuple(ref)
        by_ref[ref] = by_ref.get(ref, 0) + weight
        groups.setdefault(group, set()).add((key, ref))
    def rush(item, event, stage, weight, group):
        add(item, ['16', str(event), '', str(stage), str(event * 1000 + stage)], weight, group)
    for key, rows in mech.sources_from_rewards(runtime, read).items():
        for row in rows: add(key, row[:5], float(row[5]), 'mech')
    mode = runtime['mode']
    assert mode['eventId'] == 700098
    assert set(map(int, mode['fixed'])) == {1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14}
    for stage, rewards in mode['fixed'].items():
        for reward in rewards:
            assert reward['count'] > 0
            rush(reward['id'], 700098, int(stage), reward['count'], 'fantasy_fixed')
    for stage, count in mode['bossTokens'].items():
        rush(mode['tokenId'], 700098, int(stage), count, 'fantasy_boss')
    for reward in mode['final']:
        assert reward['type'] == 0
        rush(reward['id'], 700098, 15, reward['count'], 'fantasy_final')
    config = runtime['rogue']
    assert config['rounds'] == 30 and not config.get('drop_pool'), 'review changed abyss drop pool'
    for drop in config['per_round_drops']:
        assert drop['type'] == 'item', 'new equipment reward requires equipment search support'
        low, high = drop.get('rounds', [1, 30])
        for stage in range(low, high + 1):
            if stage in drop.get('exclude_rounds', []): continue
            chance = drop.get('chance', 0)
            if isinstance(chance, dict):
                chance = chance['start'] + chance.get('per_round', 0) * (stage - chance.get('base_round', stage))
            chance = max(0, min(1, chance))
            slots = drop.get('slots', 1)
            guaranteed = max(0, min(slots, drop.get('guaranteed_slots', 0 if 'chance' in drop else slots)))
            weight = drop.get('count', 1) * (guaranteed + (slots - guaranteed) * chance)
            if weight > 0: rush(drop['id'], 700099, stage, weight, 'abyss_round')
    for reward in runtime['folderBase']:
        assert reward['type'] == 0 and reward['count'] > 0
        rush(reward['id'], 700099, 30, reward['count'], 'abyss_final_fixed')
    for reward in config['folder_clear_chance']:
        assert reward.get('type', 0) == 0
        weight = reward['count'] * max(0, min(1, reward['chance']))
        if weight > 0: rush(reward['id'], 700099, 30, weight, 'abyss_final_chance')
    for reward in config['folder_clear_random']:
        assert reward.get('type', 0) == 0
        pool = reward['pool']
        assert pool and len(set(pool)) == len(pool)
        lo, hi = reward['pick']
        assert 0 <= lo <= hi <= len(pool)
        # Uniform sampling without replacement: each member's inclusion chance
        # is average picks / pool size, not 100% for every member of the pool.
        weight = sum(reward['count']) / 2 * ((lo + hi) / 2) / len(pool) * reward.get('chance', 1)
        if weight > 0:
            for item in pool: rush(item, 700099, 30, weight, 'abyss_final_random')
    # Preserve the existing Five Boss contracts; all other custom families above
    # are derived from actual schedules rather than an item-ID allowlist.
    prior = previous.reward_sources(previous.verify_server_contract())
    for key, rows in prior.items():
        for row in rows:
            if row[0] == '2': add(key, row[:5], float(row[5]), 'five_boss')
    for entry in runtime['expert']:
        reward = entry['quest']['sPlusReward']
        assert reward == {'type': 0, 'id': 14040, 'count': 3}, 'review changed SS reward'
        qid = entry['id']
        # Zero is a neutral sorting hint for a one-time SS source, never an
        # assertion of repeatable expected yield.
        add(14040, ['12', str(qid // 1000), '', str(qid % 1000), str(qid)], 0, 'expert_first_ss')
    rows = {key: [list(ref) + [format(weight, '.12g')] for ref, weight in refs.items()]
            for key, refs in result.items()}
    validate_navigation(rows, read)
    return rows, {k: {'items': len({item for item, _ in refs}), 'pairs': len(refs)} for k, refs in groups.items()}


def validate_navigation(sources, read):
    rush = p.rawmap(read(RUSH))
    expert = p.rawmap(read(EXPERT))
    for rows in sources.values():
        for row in rows:
            if row[0] == '16':
                event, stage = row[1], int(row[3])
                assert event in ['700098', '700099'] and 1 <= stage <= (15 if event == '700098' else 30), 'hidden quest'
                quest = p.csvrows(p.rawmap(rush[event])[str(stage)])[0]
                assert quest[0] == row[4] and quest[2] == row[3]
                assert quest[7:9] == ['2000-01-01 12:00:00', '2099-12-29 23:59:59']
                if stage > 1:
                    gate = ['16', event, '', str(stage - 1), str(int(row[4]) - 1)]
                    assert quest[9:14] == gate, 'previous round gate drift'
                    if event == '700098': assert quest[36:41] == gate, 'Fantasy selection gate drift'
            elif row[0] == '12':
                quest = p.csvrows(p.rawmap(expert[row[1]])[row[3]])[0]
                # Expert columns 1/2 are grouping/display order, not the master
                # map keys used by QuestReferenceIdKind's multiplied ID.
                assert quest[0] == row[4]
                assert quest[8] == '(None)' and quest[9] in ['0', '9', '12'] and int(quest[13]) > 0, 'expert unlock gate drift'
            else:
                assert row[0] in ['2', '18']


def merge_index(before, expected):
    result = p.rawmap(before)
    for key, wanted in expected.items():
        old = p.csvrows(result[key]) if key in result else []
        rows = copy.deepcopy(old)
        for want in wanted:
            matches = [r for r in rows if r[:5] == want[:5]]
            if matches:
                assert len(matches) == 1 and math.isclose(float(matches[0][5]), float(want[5]), rel_tol=1e-10), ('existing custom source drift', key, want)
            else: rows.append(want)
        if rows != old: result[key] = p.packcsv(rows)
    return p.packmap(result)


def add_note(before):
    rows = p.rawmap(before)
    item = p.csvrows(rows['14040'])
    assert len(item) == 1 and len(item[0]) == 23 and STAR_NOTE not in item[0][5]
    item[0][5] += '\n\n' + STAR_NOTE
    rows['14040'] = p.packcsv(item)
    return p.packmap(rows)


def validate_thumbnails(read, item_ids):
    items = p.rawmap(read(mech.ITEM))
    atlases = {n: mech.icons.codec.decode_atlas(read(n + '.atlas.amf3.deflate')) for n in mech.icons.PRELOADED}
    checks = []
    for key in item_ids:
        row = p.csvrows(items[key])[0]
        # ItemThumbnailView uses setTexture(ItemThumbnail, thumbnail_id, callback)
        # before getTexture. A missing optional small_vector_icon_id on ordinary
        # materials does not route this asynchronous thumbnail through the
        # stage's synchronous DropItemContentsView.
        matches = [(n, frame) for n, frames in atlases.items() for frame in frames if frame['n'] == row[3]]
        if matches:
            assert len(matches) == 1
            name, frame = matches[0]
            image = mech.icons.strict_png(read(name + '.png'))
            x1, y1, x2, y2 = mech.icons.rect(frame)
            assert 0 <= x1 < x2 <= image.width and 0 <= y1 < y2 <= image.height
            size = [x2 - x1, y2 - y1]
        else:
            name = row[3] + '.png'
            image = mech.icons.strict_png(read(name))
            size = list(image.size)
        assert min(size) > 0
        checks.append(dict(item=key, thumbnail=row[3], source=name, size=size,
                           small_icon_present=row[4] != '(None)'))
    return checks


def validate(before, after, runtime, read):
    expected, groups = required_sources(runtime, read)
    old, new = p.rawmap(before[mech.SEARCH]), p.rawmap(after[mech.SEARCH])
    assert set(new) == set(old) | set(expected), 'missing or unexpected keys'
    missing = []
    added = 0
    changed = []
    for key, raw in new.items():
        old_rows = p.csvrows(old[key]) if key in old else []
        new_rows = p.csvrows(raw)
        assert new_rows[:len(old_rows)] == old_rows, ('old source changed', key)
        extra = [r for r in expected.get(key, []) if not any(r[:5] == x[:5] for x in old_rows)]
        assert new_rows[len(old_rows):] == extra, ('unexpected or missing added source', key)
        for want in expected.get(key, []):
            hits = [r for r in new_rows if r[:5] == want[:5]]
            if len(hits) != 1 or not math.isclose(float(hits[0][5]), float(want[5]), rel_tol=1e-10): missing.append((key, want))
        if extra:
            added += len(extra)
            changed.append(key)
        elif key in old: assert raw == old[key], ('untouched key recompressed', key)
    assert not missing, ('incomplete item/quest pairs', missing)
    assert after[mech.ITEM] == add_note(before[mech.ITEM]), 'non-description item change'
    return dict(base_search_keys=len(old), final_search_keys=len(new), new_keys=len(set(new) - set(old)),
        changed_keys=len(changed), appended_source_rows=added, changed_item_ids=sorted(changed, key=int),
        covered_items=len(expected), covered_pairs=sum(map(len, expected.values())), groups=groups,
        missing_expected_pairs=0, preserved_old_source_rows=sum(len(p.csvrows(v)) for v in old.values()))


def prepare(work):
    chain = p.Chain()
    assert chain.tail == mech.VERSION
    tail = chain.manifest['patches'][-1]
    assert tail['id'] == 'mech-item-sources-1.4.106' and tail['depends_on'] == mech.BASE
    archive = p.REPO / 'assets/asset-patch/active' / mech.ARCHIVE
    assert p.sha(archive.read_bytes()) == OLD_ARCHIVE_SHA, 'only the approved unpublished .106 may be replaced'
    cache = {}
    def read(name):
        if name not in cache:
            cache[name] = chain.get(('common', p.hrel(name)))
            assert cache[name] is not None, name
        return cache[name]
    # Resolve the pre-.106 index from the verified active predecessors, without
    # disabling the manifest or writing a temporary whole client store.
    index_member = p.member(('common', p.hrel(mech.SEARCH)))
    before_search = None
    for entry in reversed(chain.manifest['patches'][:-1]):
        if not entry.get('enabled'): continue
        for name in reversed(entry.get('chain') or [entry['archive']]):
            with zipfile.ZipFile(p.REPO / 'assets/asset-patch/active' / name) as z:
                if index_member in z.namelist(): before_search = z.read(index_member); break
        if before_search is not None: break
    assert before_search is not None
    before = {mech.SEARCH: before_search, mech.ITEM: read(mech.ITEM)}
    runtime = runtime_contract()
    # Prove the current .106 consists exactly of the original eight additions.
    mech.validate_index(before_search, read(mech.SEARCH), runtime, read)
    expected, _ = required_sources(runtime, read)
    after = {mech.SEARCH: merge_index(before_search, expected), mech.ITEM: add_note(before[mech.ITEM])}
    checks = validate(before, after, runtime, read)
    items = p.rawmap(before[mech.ITEM])
    checks['preloaded_icons'] = mech.validate_icons(read,
        [key for key in expected if p.csvrows(items[key])[0][4] != '(None)'])
    checks['thumbnails'] = validate_thumbnails(read, expected)
    checks['previous_mod_display_contract'] = mech.art.validate_display(read)
    payloads = {p.member(('common', p.hrel(n))): raw for n, raw in after.items()}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, raw in sorted(payloads.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 12, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, raw)
    payload = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        assert z.testzip() is None and z.namelist() == sorted(payloads)
        assert all(z.read(n) == raw for n, raw in payloads.items())
    integrity = dict(name=mech.ARCHIVE, size=len(payload), sha256=p.sha(payload), members=len(payloads), files=sorted(payloads))
    manifest = copy.deepcopy(chain.manifest)
    tail = manifest['patches'][-1]
    tail.update(name='机兵、幻想、深渊与追忆材料入手来源补全',
        description='同一.106增量补齐机兵材料、幻想固定奖励、深渊整轮固定及随机奖励和追忆首次SS来源，并补充一次性奖励说明。',
        archive_size=len(payload), archive_integrity=[integrity], files=sorted(payloads))
    mech.art.validate_manifest(manifest)
    report = dict(base_version=mech.BASE, version=mech.VERSION, archive=integrity, checks=checks,
        sources=expected, source_reads=chain.reads, source_manifest_before_sha256=p.sha(chain.manifest_bytes),
        superseded_unpublished_archive_sha256=OLD_ARCHIVE_SHA,
        replacement_authorization='用户：一起补齐呗，都做到.106的包里',
        runtime_synced=False, device_tested=False, swf_changed=False,
        save_impact='仅查询索引与星空记忆晶说明；ID、库存、进度、数据库及V1/V2存档格式不变。',
        resources={n: dict(before_sha256=p.sha(before[n]), after_sha256=p.sha(raw), member=p.member(('common', p.hrel(n)))) for n, raw in after.items()},
        limitations=['原生界面最多展示5项，保留其筛选与排序。', '首次SS已领取状态不能通过静态索引动态移除来源；说明已标注一次性。',
            '覆盖本次自定义奖励来源清单及现行奖励数据；不为停用、任务、排行榜等伪造关卡入口。'])
    report['source_applied'] = False
    report['source_paths'] = ['assets/asset-patch/manifest.json',
        'assets/asset-patch/active/' + mech.ARCHIVE, mech.AUDIT + '/report.json'] + [
        'assets/asset-patch/' + member for member in sorted(payloads)]
    report['excluded_nonbaseline_cdn_archives'] = p.readj(p.REPO / mech.AUDIT / 'report.json')['excluded_nonbaseline_cdn_archives']
    for label, resources in [('effective', cache), ('before', before), ('after', after)]:
        for name, raw in resources.items():
            dest = work / label / name; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(raw)
    (work / mech.ARCHIVE).write_bytes(payload)
    p.savej(work / 'runtime-contract.json', runtime)
    p.savej(work / 'manifest.after.json', manifest)
    p.savej(work / 'report.json', report)
    (work / 'manifest.before.json').write_bytes(chain.manifest_bytes)
    return chain, cache, after, payload, manifest, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--apply-source', action='store_true')
    args = parser.parse_args(); work = args.work.resolve()
    assert work.is_relative_to(Path('F:/codex/work').resolve())
    work.mkdir(parents=True, exist_ok=True)
    chain, cache, after, payload, manifest, report = prepare(work)
    if args.apply_source:
        report['source_applied'] = True
        p.savej(work / 'report.json', report)
        archive = p.REPO / 'assets/asset-patch/active' / mech.ARCHIVE
        delivery = {archive: payload, p.REPO / mech.AUDIT / 'report.json': (work / 'report.json').read_bytes()}
        for name, raw in after.items(): delivery[p.REPO / 'assets/asset-patch' / p.member(('common', p.hrel(name)))] = raw
        mpath = p.REPO / 'assets/asset-patch/manifest.json'
        assert mpath.read_bytes() == chain.manifest_bytes and p.sha(archive.read_bytes()) == OLD_ARCHIVE_SHA
        for name in after:
            path = p.REPO / 'assets/asset-patch' / p.member(('common', p.hrel(name)))
            assert path.read_bytes() == cache[name], ('loose source drift', name)
        delivery[mpath] = (work / 'manifest.after.json').read_bytes()
        for path in delivery:
            resolved = path.resolve()
            assert resolved.is_relative_to(p.REPO.resolve()) and not resolved.is_relative_to((p.REPO / '.cdn').resolve())
            backup = work / 'apply-backup' / path.relative_to(p.REPO)
            assert not backup.exists(), 'preserve previous replacement backup'
            backup.parent.mkdir(parents=True, exist_ok=True); backup.write_bytes(path.read_bytes())
        for path, raw in delivery.items(): path.write_bytes(raw)
        final = p.Chain()
        assert final.tail == mech.VERSION and final.manifest['patches'][:-1] == chain.manifest['patches'][:-1]
        assert all(final.get(('common', p.hrel(n))) == after.get(n, raw) for n, raw in cache.items())
    print(json.dumps(dict(archive=report['archive'], checks={k: v for k, v in report['checks'].items()
        if k not in ['preloaded_icons', 'thumbnails', 'previous_mod_display_contract', 'changed_item_ids', 'groups']}, source_applied=args.apply_source)))


if __name__ == '__main__': main()
