"""Read only the gacha masters selected by the verified active resource chain."""
from __future__ import annotations
import contextlib
import json
import zipfile
import prepare_content as p

GACHA = 'master/gacha/gacha.orderedmap'


def load():
    chain = p.Chain()
    raw, reads, odds = {}, {}, {}
    with contextlib.ExitStack() as stack:
        archives = {}
        def read(name):
            if name in raw:
                return raw[name]
            key = ('common', p.hrel(name))
            assert key in chain.index, ('missing effective resource', name)
            archive, member = chain.index[key]
            if archive not in archives:
                archives[archive] = stack.enter_context(zipfile.ZipFile(archive))
            raw[name] = archives[archive].read(member)
            reads[name] = dict(archive=str(archive), member=member, sha256=p.sha(raw[name]))
            return raw[name]
        rows = {k: p.csvrows(v) for k, v in p.rawmap(read(GACHA)).items()}
        assert all(len(v) == 1 for v in rows.values()), 'review multi-row banners'
        for group in rows.values():
            r = group[0]
            for col in [11] + ([14, 15, 16] if r[13] == '0' else [22, 23, 24]):
                oid = r[col]
                if oid in ('', '(None)') or oid in odds:
                    continue
                outer = p.rawmap(read(f'master/gacha_odds/{oid}.orderedmap'))
                assert set(outer) == {oid}, ('wrong odds root', oid)
                odds[oid] = {k: p.csvrows(v)[0] for k, v in p.rawmap(outer[oid]).items()}
    return chain, rows, odds, raw, reads


def export(rows, odds):
    result = dict(rarity={}, character={}, equipment={})
    for group in rows.values():
        r = group[0]
        for col in [11] + ([14, 15, 16] if r[13] == '0' else [22, 23, 24]):
            oid = r[col]
            if oid in ('', '(None)'):
                continue
            kind = 'rarity' if col == 11 else ('character' if r[13] == '0' else 'equipment')
            entries = []
            for entry in odds[oid].values():
                if kind == 'rarity':
                    entries.append(dict(rarity=int(entry[0]), weight=int(entry[1])))
                else:
                    obj = {('characterId' if kind == 'character' else 'equipmentId'): int(entry[0]),
                           'rarity': int(entry[1]), 'weight': int(entry[2]),
                           'oddsUp': entry[3] == 'true', 'isLimited': entry[4] == 'true',
                           'isExchangeable': entry[5] == 'true'}
                    if kind == 'character':
                        obj['trialReadingForced'] = entry[6] == 'true'
                    entries.append(obj)
            result[kind][oid] = dict(entries=entries)
    return dict(gachaRows=rows, oddsExport=result)


if __name__ == '__main__':
    chain, rows, odds, _, reads = load()
    print(json.dumps(dict(export(rows, odds), version=chain.tail, sourceReads=reads), ensure_ascii=False))
