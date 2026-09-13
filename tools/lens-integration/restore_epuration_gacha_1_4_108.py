"""Restore 179981 in both pools; append the authorized .108 part, preserving prior bytes."""
from __future__ import annotations
import argparse
import copy
import io
import json
import math
import zipfile
import zlib
from pathlib import Path
import prepare_content as p

PART = 'pinball-1.4.107-1.4.108-2-epuration-gacha.zip'
AUDIT = 'assets/asset-patch/audit/epuration-gacha-1.4.108'
TARGET = 179981
SPECS = [('990001', 'gacha_cnmod.json', 'cnmod_abyss_limited_gacha', 1000),
         ('990002', 'gacha_rank_p5b.json', 'cnmod_ashen_verdict_gacha', 10000)]


def encoded(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def adjust(pool, weight):
    after = copy.deepcopy(pool)
    rows = after['pool']['1']
    target = next(x for x in rows if x['id'] == TARGET)
    assert target['odds'] == 0 and target['isRateUp'], 'unexpected target preimage'
    # Retain every other MOD's exact chance and the star-rank totals. Ordinary
    # five-stars fund the restored share proportionally, with stable integer rounding.
    ordinary = [x for x in rows if not x['isRateUp'] and x['odds'] > 0]
    assert all(x['id'] < 179970 or x['id'] == 261089 for x in ordinary)
    budget = sum(x['odds'] for x in ordinary)
    quotients = [divmod(x['odds'] * (budget - weight), budget) for x in ordinary]
    remainder = budget - weight - sum(q for q, _ in quotients)
    extra = set(sorted(range(len(ordinary)), key=lambda i: (-quotients[i][1], i))[:remainder])
    for i, row in enumerate(ordinary):
        row['odds'] = quotients[i][0] + (i in extra)
        assert row['odds'] > 0
    target.update(odds=weight, isExchangeable=True)
    total = sum(x['odds'] for x in rows)
    assert total == sum(x['odds'] for x in pool['pool']['1'])
    for old, new in zip(pool['pool']['1'], rows):
        if new['odds'] != old['odds']:
            new['rarity'] = math.floor(new['odds'] / total * 100000 + .5) / 100
        if old['isRateUp'] and old['id'] != TARGET:
            assert old == new
        assert {k:v for k,v in old.items() if k not in ('odds','rarity','isExchangeable')} == {
            k:v for k,v in new.items() if k not in ('odds','rarity','isExchangeable')}
        if old['id'] != TARGET:
            assert old['isExchangeable'] == new['isExchangeable']
    assert after['pool']['2'] == pool['pool']['2'] and after['pool']['3'] == pool['pool']['3']
    return after


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    work = args.work.resolve()
    assert work.is_relative_to(Path('F:/codex/work').resolve()) and not work.exists()
    chain = p.Chain()
    assert chain.tail == '1.4.108'
    original = chain.manifest
    patch = original['patches'][-1]
    assert patch['version'] == '1.4.108' and patch['depends_on'] == '1.4.107'
    prior = patch.get('chain') or [patch['archive']]
    assert len(prior) == 1 and not (p.REPO/'assets/asset-patch/active'/PART).exists()
    preimages, writes, resources, evidence = {}, {}, {}, {}
    for rel in ['assets/gacha.json','assets/gacha_cnmod.json','assets/gacha_rank_p5b.json']:
        preimages[rel] = (p.REPO/rel).read_bytes()
    server = {rel:json.loads(raw) for rel,raw in preimages.items()}
    for gid, extension, prefix, weight in SPECS:
        base = server['assets/gacha.json'][gid]
        assert base == server['assets/'+extension][gid], 'mirrored pool drift'
        fixed = adjust(base, weight)
        for data in server.values():
            if gid in data:
                assert data[gid] == base
                data[gid] = copy.deepcopy(fixed)
        logical = f'master/gacha_odds/{prefix}_character_5.orderedmap'
        before = chain.get(('common',p.hrel(logical)))
        outer = p.rawmap(before); assert list(outer) == [prefix+'_character_5']
        inner = p.rawmap(next(iter(outer.values())))
        assert len(inner) == len(base['pool']['1'])
        for (key, raw), old, new in zip(list(inner.items()),base['pool']['1'],fixed['pool']['1']):
            cells = p.csvrows(raw)[0]
            expected = [str(old['id']),str(old['rank']),str(old['odds']),str(old['isRateUp']).lower(),
                        str(old['isLimited']).lower(),str(old['isExchangeable']).lower(),str(old['trialReadingForced']).lower()]
            assert cells == expected, ('client/server drift',gid,key)
            cells[2],cells[5] = str(new['odds']), str(new['isExchangeable']).lower()
            if new['odds'] != old['odds'] or new['isExchangeable'] != old['isExchangeable']:
                inner[key] = p.packcsv([cells])
        after = p.packmap({prefix+'_character_5':p.packmap(inner)})
        resources[logical] = after
        preimages['client/'+logical] = before
        evidence[gid] = dict(before=base,after=fixed,normal_probability_percent=weight/10000,
            shared_android_ios=True,source=chain.reads['common|'+p.hrel(logical)])
        note = f'rich_text/{prefix}_note.html.deflate'
        oldnote = chain.get(('common',p.hrel(note)))
        text = zlib.decompress(oldnote,-15).decode('utf-8')
        if gid == '990001':
            replacements = {
                '水杰拉尔、秋灯九尾及其余21位可抽MOD各为0.100%，合计2.300%。所有可抽MOD的总概率为6.550%，其他★5角色合计8.450%':
                '水杰拉尔、秋灯九尾、歼灭者及其余21位可抽MOD各为0.100%，合计2.400%。所有可抽MOD的总概率为6.650%，其他★5角色合计8.350%',
                '歼灭者的抽取概率为0%，不会被随机抽出，仍可使用兑换点数兑换。':
                '歼灭者的抽取概率为0.100%，可使用250点兑换点数兑换。'}
        else:
            replacements = {
                '43位可抽MOD各为1.000%，合计43.000%；其他★5角色合计52.000%':
                '44位可抽MOD各为1.000%，合计44.000%；其他★5角色合计51.000%',
                '43位可抽MOD排在角色列表前部并标红，随后列出25位抽取概率为0%的MOD':
                '44位可抽MOD排在角色列表前部并标红，随后列出24位抽取概率为0%的MOD',
                '抽取概率为0%的角色不会被随机抽出。':
                '歼灭者的抽取概率为1.000%，可使用250点兑换点数兑换。抽取概率为0%的角色不会被随机抽出。'}
        for old,new in replacements.items():
            assert text.count(old) == 1, ('notice preimage changed',note,old)
            text = text.replace(old,new)
        resources[note] = zlib.compress(text.encode('utf-8'),level=9,wbits=-15)
        preimages['client/'+note] = oldnote
    for rel,data in server.items():
        writes[rel] = encoded(data)
    members = {p.member(('common',p.hrel(n))):b for n,b in resources.items()}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,b in sorted(members.items()):
            info = zipfile.ZipInfo(n,(2026,9,13,0,0,0)); info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info,b)
    archive = stream.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert z.testzip() is None and {n:z.read(n) for n in z.namelist()} == members
    integrity = dict(name=PART,size=len(archive),sha256=p.sha(archive),members=len(members),files=sorted(members))
    manifest = copy.deepcopy(original); patch = manifest['patches'][-1]
    patch['chain'] = prior+[PART]
    patch['archive_integrity'].append(integrity)
    patch['archive_size'] = sum(x['size'] for x in patch['archive_integrity'])
    patch['files'] = sorted(set(patch['files'])|set(members))
    patch['changes'].append('第2分包：歼灭者179981恢复深渊0.100%、竞速1.000%抽取，两池250点兑换；保留其他MOD概率及五星总率，同步池说明。')
    patch['audit']['epuration_gacha_directory'] = AUDIT
    assert manifest['patches'][:-1] == original['patches'][:-1]
    preimages['assets/asset-patch/manifest.json'] = chain.manifest_bytes
    writes['assets/asset-patch/manifest.json'] = encoded(manifest)
    writes['assets/asset-patch/active/'+PART] = archive
    # Native direct downloads prefer these sparse files; keep them equal to the ZIP.
    # They remain excluded from any later outer cloud overlay.
    for member,raw in members.items():
        rel = 'assets/asset-patch/'+member
        if (p.REPO/rel).exists(): preimages[rel] = (p.REPO/rel).read_bytes()
        writes[rel] = raw
    report = dict(version='1.4.108',part=2,archive=integrity,pools=evidence,
        resources={n:dict(member=p.member(('common',p.hrel(n))),sha256=p.sha(b)) for n,b in resources.items()},
        before_hashes={n:p.sha(b) for n,b in preimages.items()},
        output_hashes={n:p.sha(b) for n,b in writes.items()},prior_archives=copy.deepcopy(original['patches'][-1]['archive_integrity']),
        save_impact='Existing character ID and inventory/point schemas retained; no migration.',
        acquisition_navigation='Existing two gacha banners and native exchange lists use these odds rows; no item/reward search changes.',
        work=str(work),applied=args.apply)
    work.mkdir(parents=True)
    for group,data in [('before',preimages),('after',writes)]:
        for rel,raw in data.items():
            dest=work/group/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
    if args.apply:
        assert not (p.REPO/AUDIT).exists()
        for rel,raw in writes.items():
            dest=(p.REPO/rel).resolve()
            assert dest.is_relative_to(p.REPO.resolve()) and not dest.is_relative_to((p.REPO/'.cdn').resolve())
            assert dest.read_bytes() == preimages[rel] if rel in preimages else not dest.exists()
        for rel,raw in writes.items():
            dest=p.REPO/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        p.savej(p.REPO/AUDIT/'report.json',report)
    p.savej(work/'report.json',report)
    print(json.dumps(dict(applied=args.apply,archive=integrity,work=str(work)),ensure_ascii=False))


if __name__ == '__main__': main()
