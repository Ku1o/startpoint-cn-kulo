"""Prepare sparse client recipe/reward data for the approved local balance change."""
import argparse
import copy
import io
import json
from pathlib import Path
import zipfile
import prepare_content as p
import wf_battle_atlas_repack as codec

BASE, VERSION = '1.4.105', '1.4.106'
SHOP = 'master/equipment_enhancement/equipment_enhancement_shop.orderedmap'
FOLDER = 'master/quest/event/rush_event_quest_folder.orderedmap'
ADDITIONAL = 'master/reward/event/additional_reward.orderedmap'
ROGUE = 'master/quest/event/cnmod_rogue_event.orderedmap'
IDS = [str(i) for i in range(59001101, 59001107)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', type=Path, required=True)
    w = ap.parse_args().work.resolve()
    assert not w.is_relative_to((p.REPO / '.cdn').resolve())
    w.mkdir(parents=True, exist_ok=True)
    c = p.Chain()
    assert c.tail == BASE, 'review current chain before applying this historical edge'
    before = {logical: c.get(('common', p.hrel(logical))) for logical in (SHOP, FOLDER, ADDITIONAL, ROGUE)}
    assert all(before.values())
    after, changes = {}, {}
    server_shop = p.readj(p.REPO / 'assets/equipment_enhancement_shop.json')
    rows = p.rawmap(before[SHOP])
    for key in IDS:
        old = p.csvrows(rows[key])[0]
        new = list(old)
        costs = server_shop[key]['costs']
        assert server_shop[key]['enhancementPurchaseMode'] == 'per_level'
        assert new[29:32] == ['5900101', str(server_shop[key]['enhancementMaxLevel']), '5']
        for i in range(4):
            new[14 + 2*i:16 + 2*i] = ([str(costs[i]['id']), str(costs[i]['amount'])]
                                      if i < len(costs) else ['(None)', ''])
        if new != old:
            rows[key] = p.packcsv([new])
        assert old[:14] + old[22:] == new[:14] + new[22:]
    after[SHOP] = p.packmap(rows)
    changes[SHOP] = [k for k in rows if rows[k] != p.rawmap(before[SHOP])[k]]
    assert set(changes[SHOP]) == {'59001102', '59001104', '59001105', '59001106'}

    # Native fixed preview shows the guaranteed minimum. The second Abyss
    # ticket is rolled by the server's inclusive 1..2 full-folder reward.
    server_folders = p.readj(p.REPO / 'assets/rush_event_quest_folder.json')
    rows = p.rawmap(before[FOLDER])
    for event in ('700098', '700099'):
        folders = p.rawmap(rows[event])
        old = p.csvrows(folders['1'])[0]
        new = list(old)
        rewards = list(server_folders[event]['1'])
        if event == '700099':
            rewards.append({'type': 0, 'id': 10000143, 'count': 1})
        for i in range(10):
            new[7 + 3*i:10 + 3*i] = ([str(rewards[i][k]) for k in ('type', 'id', 'count')]
                                      if i < len(rewards) else ['(None)', '', '(None)'])
        assert old[:7] == new[:7] and len(old) == len(new) == 37
        folders['1'] = p.packcsv([new])
        rows[event] = p.packmap(folders)
    after[FOLDER] = p.packmap(rows)
    changes[FOLDER] = ['700098/1', '700099/1']

    rows = p.rawmap(before[ADDITIONAL])
    group = p.rawmap(rows['237009700'])
    assert set(group) == {'1', '2'}
    group['3'] = p.packcsv([['mode15_full_clear_deep_ticket', '0', '10000143', '1', '1']])
    rows['237009700'] = p.packmap(group)
    after[ADDITIONAL] = p.packmap(rows)
    changes[ADDITIONAL] = ['237009700/3']

    rows = p.rawmap(before[ROGUE])
    cfg = p.readj(p.REPO / 'assets/rogue_event.json')['events']['700099']
    # This custom source describes chance rewards only; the guaranteed ticket
    # is already represented by the native minimum preview above.
    rows['700099'] = p.packcsv([['1', str(r['type']), str(r['id']), str(r['count']), str(r['chance'])]
                               for r in cfg['folder_clear_chance']])
    after[ROGUE] = p.packmap(rows)
    changes[ROGUE] = ['700099']

    # Keep every unrelated native row byte-identical, including nested rows.
    allowed = {SHOP: set(IDS), FOLDER: {'700098', '700099'},
               ADDITIONAL: {'237009700'}, ROGUE: {'700099'}}
    for logical in before:
        a, b = p.rawmap(before[logical]), p.rawmap(after[logical])
        assert list(a) == list(b)
        assert {k: v for k, v in a.items() if k not in allowed[logical]} == {
            k: v for k, v in b.items() if k not in allowed[logical]}
    for event in ('700098', '700099'):
        a, b = [p.rawmap(p.rawmap(data[FOLDER])[event]) for data in (before, after)]
        assert {k:v for k,v in a.items() if k != '1'} == {k:v for k,v in b.items() if k != '1'}
    a, b = [p.rawmap(p.rawmap(data[ADDITIONAL])['237009700']) for data in (before, after)]
    assert all(b[k] == v for k,v in a.items())

    # Existing small-vector consumers have preloaded frames. Ultimate Totem
    # uses the native nullable-small-icon path and its existing large PNG;
    # it already appears in other enhancement recipes on the current client.
    item_rows = p.rawmap(c.get(('common', p.hrel('master/item/item.orderedmap'))))
    frames = {r['n'] for base in ('item', 'item_sec', 'item_icon') for r in
              codec.decode_atlas(c.get(('common', p.hrel(base + '/sprite_sheet.atlas.amf3.deflate'))))}
    icon_checks = []
    for item_id in (2370097, 2370100, 10000143, 10000145, 10000147):
        row = p.csvrows(item_rows[str(item_id)])[0]
        if row[4] != '(None)':
            assert row[4] in frames, f'not preloaded: {item_id} {row[4]}'
        else:
            raw = c.get(('common', p.hrel(row[3] + '.png')))
            assert raw and p.wf_assets.png_decode_stored(raw)
            assert any('2370097' in p.csvrows(v)[0][14:22] for k,v in p.rawmap(before[SHOP]).items() if k not in IDS)
        icon_checks.append({'id':item_id, 'name':row[2], 'small_icon':row[4]})

    name = f'pinball-{BASE}-{VERSION}-1-recipe-ticket-rewards.zip'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for logical, raw in sorted(after.items()):
            info = zipfile.ZipInfo(p.member(('common',p.hrel(logical))), (2026,9,8,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, raw)
    archive = buf.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert z.testzip() is None and len(z.namelist()) == len(after)
        for logical, raw in after.items(): assert z.read(p.member(('common', p.hrel(logical)))) == raw
    integrity = {'name':name, 'size':len(archive), 'sha256':p.sha(archive), 'members':len(after),
                 'files':sorted(p.member(('common',p.hrel(x))) for x in after)}
    manifest = copy.deepcopy(c.manifest)
    manifest['patches'].append({'id':'recipe-ticket-rewards-'+VERSION, 'type':'patch',
        'name':'终式强化材料与连战门票奖励', 'description':'死亡使者终式逐级配方更新；幻想15关门票1张；深渊30层门票必得1～2张及奖励预览对齐。',
        'version':VERSION, 'depends_on':BASE, 'enabled':True, 'archive':name,
        'archive_size':len(archive), 'chain':[name], 'archive_integrity':[integrity], 'files':integrity['files'],
        'created_at':'2026-09-08', 'local_test_only':True, 'required_local_platform':'android'})
    manifest['cdn_version'] = VERSION
    for folder, blobs in [('client-before',before),('prepared',after)]:
        for logical, raw in blobs.items():
            dest = w/folder/p.member(('common',p.hrel(logical)))
            dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(raw)
    (w/name).write_bytes(archive)
    p.savej(w/'manifest.after.json',manifest)
    report = {'base':BASE,'version':VERSION,'archive':integrity,'changes':changes,'icon_checks':icon_checks,
              'source_reads':c.reads,'swf_changed':False,'device_tested':False}
    p.savej(w/'report.json',report)
    print(json.dumps({'archive':integrity,'changes':changes,'icon_checks':icon_checks},ensure_ascii=False))


if __name__ == '__main__': main()
