"""Recover the verified C2265 condition fix without reverting current speech text."""
import argparse
import copy
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/lens-integration'))
import prepare_content as p

NAME = 'pinball-1.4.108-1.4.109-2-c2265-character-speech.zip'
LOGICAL = 'master/character/character_speech.orderedmap'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verified-backup', type=Path, required=True)
    ap.add_argument('--work', type=Path, required=True)
    args = ap.parse_args()
    chain = p.Chain()
    assert chain.tail == '1.4.109'
    archive_bytes = args.verified_backup.read_bytes()
    assert p.sha(archive_bytes) == 'a20bf694e18e82aafa4c96acfccf0a96584c6dd59b40436994c00e78b0d6f3d0'
    key = ('common', p.hrel(LOGICAL))
    member = p.member(key)
    before = chain.get(key)
    rows = p.rawmap(before)
    with zipfile.ZipFile(args.verified_backup) as z:
        assert z.namelist() == [member] and z.testzip() is None
        historical = p.rawmap(z.read(member))
    assert rows.keys() == historical.keys()
    assert [k for k in rows if rows[k] != historical[k]] == ['149988']
    speech = p.csvrows(rows['149988'])
    successful = p.csvrows(historical['149988'])
    i = next(i for i, row in enumerate(speech) if row[-1] == 'home/home_0')
    assert speech[i][1] == '1' and successful[i][1] == '0'
    expected = copy.deepcopy(speech)
    expected[i][1] = '0'
    updated = dict(rows)
    updated['149988'] = p.packcsv(expected)
    after = p.packmap(updated)
    decoded = p.rawmap(after)
    assert all(decoded[k] == value for k, value in rows.items() if k != '149988')
    assert p.csvrows(decoded['149988']) == expected
    # All text, audio paths and every field except the initial visibility condition stay exact.
    assert [(j, c) for j in range(len(speech)) for c in range(len(speech[j]))
            if speech[j][c] != expected[j][c]] == [(i, 1)]
    args.work.mkdir(parents=True, exist_ok=True)
    archive = args.work / NAME
    assert not archive.exists()
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        info = zipfile.ZipInfo(member, (2026, 9, 15, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, after)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and z.read(member) == after
    receipt = dict(name=NAME, size=archive.stat().st_size, sha256=p.sha(archive.read_bytes()), members=1, files=[member])
    manifest = copy.deepcopy(chain.manifest)
    patch = next(x for x in manifest['patches'] if x.get('enabled') and x['version'] == '1.4.109')
    assert len(patch['chain']) == 2
    patch['chain'].insert(1, NAME)
    patch['archive_integrity'].insert(1, receipt)
    patch['archive_size'] = sum(x['size'] for x in patch['archive_integrity'])
    patch['files'] = sorted(set(patch['files'] + [member]))
    patch['changes'].append('第2分包：149988 未进化时允许 home_0 主页台词，修复台词全部被过滤导致的 C2265；保留当前台词文字与其余行。')
    patch['audit']['c2265_directory'] = 'assets/asset-patch/audit/c2265-1.4.109'
    p.savej(args.work / 'manifest.json', manifest)
    p.savej(args.work / 'report.json', dict(receipt=receipt, logical=LOGICAL, source=chain.reads,
        verified_backup_sha256=p.sha(archive_bytes), before_sha256=p.sha(before), after_sha256=p.sha(after),
        rows_preserved=len(rows)-1, character='149988', only_changed_field='home/home_0 condition: 1 -> 0',
        historical_text_omission_excluded=True, save_format_changed=False, device_retest=False))
    print(json.dumps(receipt))

if __name__ == '__main__':
    main()
