"""Prepare the native one-continue limit on all Five Boss scenes, without SWF edits."""
import argparse
import copy
import io
import json
from pathlib import Path
import zipfile
import prepare_content as p

BASE, VERSION = '1.4.104', '1.4.105'
LOGICAL = 'master/quest/boss_battle_quest.orderedmap'
IDS = set(range(1099001, 1099024))


def validate(before, after):
    old, new = p.rawmap(before), p.rawmap(after)
    assert list(old) == list(new)
    assert {k: v for k, v in old.items() if k != '1'} == {k: v for k, v in new.items() if k != '1'}
    old_stages, stages = p.rawmap(old['1']), p.rawmap(new['1'])
    assert list(old_stages) == list(stages)
    assert {k: v for k, v in old_stages.items() if k != '99'} == {k: v for k, v in stages.items() if k != '99'}
    old_quests, quests = p.rawmap(old_stages['99']), p.rawmap(stages['99'])
    assert list(old_quests) == list(quests)
    seen = set()
    for key, raw in quests.items():
        a, b = p.csvrows(old_quests[key]), p.csvrows(raw)
        assert len(a) == len(b) == 1 and len(a[0]) == len(b[0]) == 124
        assert a[0][119] == '(None)' and b[0][119] == '1'
        assert a[0][:119] + a[0][120:] == b[0][:119] + b[0][120:]
        seen.add(int(b[0][0]))
    assert seen == IDS
    return {'quest_ids': sorted(seen), 'native_max_continue_count_column': 119,
            'max_continue_count': 1, 'all_other_fields_and_quests_preserved': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    w = args.work.resolve()
    assert not w.is_relative_to((p.REPO / '.cdn').resolve())
    w.mkdir(parents=True, exist_ok=True)
    chain = p.Chain()
    assert chain.tail == BASE, 'review current chain before rebuilding this historical edge'
    before = chain.get(('common', p.hrel(LOGICAL)))
    chapters = p.rawmap(before)
    stages = p.rawmap(chapters['1'])
    quests = p.rawmap(stages['99'])
    for key, raw in quests.items():
        rows = p.csvrows(raw)
        assert int(rows[0][0]) in IDS and rows[0][119] == '(None)'
        rows[0][119] = '1'
        quests[key] = p.packcsv(rows)
    stages['99'] = p.packmap(quests)
    chapters['1'] = p.packmap(stages)
    after = p.packmap(chapters)
    checks = validate(before, after)
    member = p.member(('common', p.hrel(LOGICAL)))
    name = f'pinball-{BASE}-{VERSION}-1-five-boss-continue-limit.zip'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        info = zipfile.ZipInfo(member, (2026, 9, 8, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, after)
    archive = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert z.testzip() is None and z.namelist() == [member]
        validate(before, z.read(member))
    integrity = {'name': name, 'size': len(archive), 'sha256': p.sha(archive), 'members': 1, 'files': [member]}
    manifest = copy.deepcopy(chain.manifest)
    manifest['patches'].append({'id': 'five-boss-continue-limit-' + VERSION, 'type': 'patch',
        'name': '五重决战每人整轮复活一次',
        'description': '原生复活次数上限设为一次，覆盖入口、两大战区和全部随机变体，换场继续累计。',
        'version': VERSION, 'depends_on': BASE, 'enabled': True, 'archive': name,
        'archive_size': len(archive), 'chain': [name], 'archive_integrity': [integrity],
        'files': [member], 'created_at': '2026-09-08', 'local_test_only': True, 'required_local_platform': 'android'})
    manifest['cdn_version'] = VERSION
    for folder, raw in [('before', before), ('prepared', after)]:
        dest = w / folder / member
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
    (w / name).write_bytes(archive)
    (w / 'manifest.before.json').write_bytes(chain.manifest_bytes)
    p.savej(w / 'manifest.after.json', manifest)
    report = {'base': BASE, 'version': VERSION, 'archive': integrity, 'checks': checks,
        'source_reads': chain.reads, 'swf_changed': False, 'runtime_delivered': False, 'device_tested': False}
    p.savej(w / 'report.json', report)
    print(json.dumps({k: report[k] for k in ('version', 'archive', 'checks')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
