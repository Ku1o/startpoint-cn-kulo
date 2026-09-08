"""Prepare the native Five Boss 35-stamina preview on all cumulative scenes."""
import argparse
import copy
import io
import json
from pathlib import Path
import zipfile
import prepare_content as p

LOGICAL = 'master/quest/boss_battle_quest.orderedmap'
BASE, VERSION = '1.4.107', '1.4.108'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', type=Path, required=True)
    w = ap.parse_args().work.resolve()
    assert not w.is_relative_to((p.REPO/'.cdn').resolve())
    w.mkdir(parents=True, exist_ok=True)
    c = p.Chain()
    assert c.tail == BASE
    before = c.get(('common', p.hrel(LOGICAL)))
    chapters = p.rawmap(before); stages = p.rawmap(chapters['1']); quests = p.rawmap(stages['99'])
    old_quests = dict(quests)
    ids = []
    for key, raw in quests.items():
        row = p.csvrows(raw)[0]
        assert len(row) == 124 and row[69] == '18' and row[119] == '1'
        ids.append(int(row[0])); row[69] = '35'; quests[key] = p.packcsv([row])
    assert set(ids) == set(range(1099001, 1099024))
    stages['99'] = p.packmap(quests); chapters['1'] = p.packmap(stages); after = p.packmap(chapters)
    a, b = p.rawmap(before), p.rawmap(after)
    assert {k:v for k,v in a.items() if k!='1'} == {k:v for k,v in b.items() if k!='1'}
    a, b = p.rawmap(a['1']), p.rawmap(b['1'])
    assert {k:v for k,v in a.items() if k!='99'} == {k:v for k,v in b.items() if k!='99'}
    readback = p.rawmap(b['99'])
    assert list(readback) == list(old_quests)
    for key, raw in readback.items():
        old, new = p.csvrows(old_quests[key])[0], p.csvrows(raw)[0]
        assert new[69] == '35' and old[:69]+old[70:] == new[:69]+new[70:]
    name = f'pinball-{BASE}-{VERSION}-1-five-boss-stamina-35.zip'
    member = p.member(('common',p.hrel(LOGICAL)))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        info = zipfile.ZipInfo(member, (2026,9,8,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED
        z.writestr(info,after)
    archive = buf.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert z.testzip() is None and z.namelist()==[member] and z.read(member)==after
    integrity = {'name':name,'size':len(archive),'sha256':p.sha(archive),'members':1,'files':[member]}
    manifest = copy.deepcopy(c.manifest)
    manifest['patches'].append({'id':'five-boss-stamina-35-'+VERSION,'type':'patch',
        'name':'五重决战单人及多人房主体力35','description':'五重决战整轮开战消耗35体力，门票仍为1张；多人由房主支付。',
        'version':VERSION,'depends_on':BASE,'enabled':True,'archive':name,'archive_size':len(archive),
        'chain':[name],'archive_integrity':[integrity],'files':[member],'created_at':'2026-09-08',
        'local_test_only':True,'required_local_platform':'android'})
    manifest['cdn_version'] = VERSION
    for folder,data in [('client-before',before),('prepared',after)]:
        dest = w/folder/member;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    (w/name).write_bytes(archive);(w/'manifest.before.json').write_bytes(c.manifest_bytes)
    p.savej(w/'manifest.after.json',manifest)
    report={'base':BASE,'version':VERSION,'archive':integrity,'quest_ids':sorted(ids),
        'column':69,'stamina_cost':35,'one_continue_preserved':True,'other_fields_preserved':True,
        'native_proof':'BossBattleQuestValues.as:1271: battle_stamina_cost = int(Std.parseInt(param1[69]));',
        'source_reads':c.reads,'swf_changed':False,'device_tested':False}
    p.savej(w/'report.json',report);print(json.dumps(integrity))


if __name__ == '__main__': main()
