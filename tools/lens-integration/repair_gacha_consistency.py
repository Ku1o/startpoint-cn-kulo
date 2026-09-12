"""Repair server pool parity and merge dark-dragon promotion into unpublished .106."""
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
import export_effective_gacha as effective

ARCHIVE = 'pinball-1.4.105-1.4.106-1-mech-item-sources.zip'
OLD_SHA = '8b0d3913bb47f0b13eabbae5aeec1e882fd7fe6f036d9da6f0005344df8cbb94'
AUDIT = 'assets/asset-patch/audit/gacha-consistency-1.4.106'
DRAGON = '261089'


def promote(rows, before):
    after = copy.deepcopy(before)
    requests, consumers = {}, {}
    for gid, group in rows.items():
        r = group[0]
        if r[13] != '0':
            continue
        four, five = r[15], r[16]
        consumers.setdefault(five, set()).add(gid)
        matches = [(k, v) for k, v in before.get(four, {}).items() if v[0] == DRAGON]
        if not matches:
            continue
        assert len(matches) == 1 and matches[0][1][1] == '4'
        key, old = matches[0]
        peers = [v for v in before[five].values() if v[3:5] == old[3:5] and int(v[2]) > 0]
        weights = {v[2] for v in peers}
        assert len(weights) == 1, ('ambiguous same-class five-star weight', gid, weights)
        new = old[:]
        new[1], new[2] = '5', next(iter(weights))
        requests[gid] = dict(four=four, five=five, key=key, before=old, after=new,
                             peer_ids=[v[0] for v in peers])
    for gid, req in requests.items():
        assert consumers[req['five']] <= requests.keys(), ('shared five-star table leaks into other banners', gid)
        after[req['four']].pop(req['key'], None)
        current = [v for v in after[req['five']].values() if v[0] == DRAGON]
        if current:
            assert current == [req['after']], ('conflicting promotion in shared table', gid)
        else:
            table = after[req['five']]
            assert all(k.isdigit() for k in table), 'review nonnumeric odds keys'
            key = str(max(map(int, table), default=-1) + 1)
            table[key] = req['after']
    return after, requests


def runtime():
    code = """const a=require('./out/lib/assets');const c=require('./out/lib/content-master');
console.log(JSON.stringify({gachas:Object.fromEntries(Object.keys(c.serverGachas).map(k=>[k,a.getGachaSync(k)])),characters:c.serverCharacters}));"""
    return json.loads(subprocess.run(['node', '-e', code], cwd=p.REPO, capture_output=True,
        text=True, encoding='utf-8', check=True, timeout=30).stdout)


def signature(entry):
    return (entry['id'], entry['rank'], entry['odds'], bool(entry.get('isRateUp')),
            bool(entry.get('isLimited')), bool(entry.get('isExchangeable')), bool(entry.get('trialReadingForced')))


def normalized(entries, character):
    total = sum(int(r[2]) for r in entries)
    result = []
    for row in entries:
        item = dict(id=int(row[0]), rank=int(row[1]), odds=int(row[2]), isRateUp=row[3] == 'true',
                    isLimited=row[4] == 'true', isExchangeable=row[5] == 'true',
                    rarity=math.floor(int(row[2]) / total * 100000 + 0.5) / 100 if total else 0)
        if character:
            item['trialReadingForced'] = row[6] == 'true'
        result.append(item)
    return result


def reconcile(base, current, rows, odds):
    after = copy.deepcopy(base)
    changes = {}
    for gid, group in rows.items():
        gacha = current[gid]
        r = group[0]
        assert gacha['type'] == int(r[13])
        character = r[13] == '0'
        pools = copy.deepcopy(gacha['pool'])
        for col, bucket in zip([14,15,16] if character else [22,23,24], ['3','2','1']):
            oid = r[col]
            if oid in ('', '(None)'):
                continue
            expected = normalized(list(odds[oid].values()), character)
            old = pools.get(bucket, [])
            if sorted(map(signature, old)) != sorted(map(signature, expected)):
                pools[bucket] = expected
        if pools != gacha['pool']:
            assert gid in after and after[gid] == gacha, ('do not overwrite a winning extension', gid)
            after[gid]['pool'] = pools
            changes[gid] = [b for b in pools if pools[b] != gacha['pool'].get(b)]
    return after, changes


def validate(current, rows, odds, characters):
    count = exchanges = 0
    for gid, group in rows.items():
        g = current[gid]; r = group[0]
        assert g['type'] == int(r[13])
        seen = set()
        for col, bucket in zip([14,15,16] if g['type'] == 0 else [22,23,24], ['3','2','1']):
            oid = r[col]
            if oid in ('', '(None)'):
                assert not g['pool'].get(bucket)
                continue
            client = normalized(list(odds[oid].values()), g['type'] == 0)
            server = g['pool'].get(bucket, [])
            assert sorted(map(signature, client)) == sorted(map(signature, server)), ('client/server pool drift', gid, bucket)
            for x in server:
                assert x['id'] not in seen, ('duplicate item', gid, x['id'])
                seen.add(x['id']); count += 1; exchanges += bool(x.get('isExchangeable'))
                assert x['rank'] == 6 - int(bucket), ('bucket mismatch', gid, x['id'])
                if g['type'] == 0:
                    assert characters[str(x['id'])]['rarity'] == x['rank'], ('character rank drift', gid, x['id'])
    return dict(pools=len(rows), entries=count, exchangeable_pairs=exchanges)


def prepare(work):
    chain, rows, odds, raw, reads = effective.load()
    assert chain.tail == '1.4.106'
    archive = p.REPO / 'assets/asset-patch/active' / ARCHIVE
    old_zip = archive.read_bytes()
    assert p.sha(old_zip) == OLD_SHA, 'unrecognized or already replaced .106 preimage'
    actual = runtime()
    assert actual['characters'][DRAGON]['rarity'] == 5
    after_odds, promotions = promote(rows, odds)
    assert len(promotions) == 82, ('promotion scope changed', len(promotions))
    base_path = p.REPO / 'assets/gacha.json'
    base_bytes = base_path.read_bytes()
    base = json.loads(base_bytes)
    after_base, changes = reconcile(base, actual['gachas'], rows, after_odds)
    final_runtime = {**actual['gachas'], **{k: after_base[k] for k in changes}}
    checks = validate(final_runtime, rows, after_odds, actual['characters'])
    assert all({k:v for k,v in base[g].items() if k!='pool'} == {k:v for k,v in after_base[g].items() if k!='pool'} for g in base)
    resources = {}
    for oid, table in after_odds.items():
        if table == odds[oid]:
            continue
        name = f'master/gacha_odds/{oid}.orderedmap'
        payload = p.packmap({oid: p.packmap({k:p.packcsv([v]) for k,v in table.items()})})
        decoded = {k:p.csvrows(v)[0] for k,v in p.rawmap(p.rawmap(payload)[oid]).items()}
        assert decoded == table
        resources[name] = payload
    with zipfile.ZipFile(io.BytesIO(old_zip)) as z:
        old_members = {n:z.read(n) for n in z.namelist()}
    assert len(old_members) == 2
    members = {**old_members, **{p.member(('common', p.hrel(n))):b for n,b in resources.items()}}
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for n,b in sorted(members.items()):
            info = zipfile.ZipInfo(n, (2026,9,12,0,0,0)); info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info,b)
    payload = out.getvalue()
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        assert z.testzip() is None
        assert {n:z.read(n) for n in z.namelist()} == members
    integrity = dict(name=ARCHIVE, size=len(payload), sha256=p.sha(payload), members=len(members), files=sorted(members))
    manifest = copy.deepcopy(chain.manifest)
    edge = manifest['patches'][-1]
    assert edge['version'] == '1.4.106' and edge['depends_on'] == '1.4.105' and edge['archive'] == ARCHIVE
    edge.update(name='入手方法与扭蛋兑换、卡池一致性补全', description='保留入手来源补全，合入暗龙五星卡池分组；服务端卡池同步修正兑换资格、成员、权重和标签。',
                archive_size=len(payload), archive_integrity=[integrity], files=sorted(members))
    edge['audit']['gacha_directory'] = AUDIT
    report = dict(archive=integrity, previous_archive_sha256=OLD_SHA, checks=checks,
                  changed_server_pools=changes, promotions=promotions,
                  resources={n:dict(member=p.member(('common',p.hrel(n))),sha256=p.sha(b)) for n,b in resources.items()},
                  preserved_item_members={n:p.sha(b) for n,b in old_members.items()}, source_reads=reads,
                  server_before_sha256=p.sha(base_bytes), server_after_sha256=None, source_applied=False)
    server_bytes = (json.dumps(after_base, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    report['server_after_sha256'] = p.sha(server_bytes)
    work.mkdir(parents=True,exist_ok=True)
    for label, data in [('before', raw), ('after', resources)]:
        for name,b in data.items():
            target=work/label/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(b)
    (work/'gacha.before.json').write_bytes(base_bytes)
    (work/'gacha.after.json').write_bytes(server_bytes)
    (work/ARCHIVE).write_bytes(payload)
    p.savej(work/'runtime.before.json',actual)
    p.savej(work/'manifest.after.json',manifest)
    p.savej(work/'report.json',report)
    p.savej(work/'export.after.json',effective.export(rows,after_odds))
    return chain, resources, payload, server_bytes, manifest, report


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--apply-source', action='store_true')
    args=ap.parse_args(); work=args.work.resolve()
    assert work.is_relative_to(Path('F:/codex/work').resolve())
    chain,resources,payload,server_bytes,manifest,report=prepare(work)
    if args.apply_source:
        delivery={p.REPO/'assets/gacha.json':server_bytes,
                  p.REPO/'assets/asset-patch/active'/ARCHIVE:payload,
                  p.REPO/'assets/asset-patch/manifest.json':(work/'manifest.after.json').read_bytes()}
        for name,b in resources.items():
            delivery[p.REPO/'assets/asset-patch'/p.member(('common',p.hrel(name)))]=b
        assert (p.REPO/'assets/asset-patch/manifest.json').read_bytes()==chain.manifest_bytes
        assert p.sha((p.REPO/'assets/gacha.json').read_bytes())==report['server_before_sha256']
        assert p.sha((p.REPO/'assets/asset-patch/active'/ARCHIVE).read_bytes())==OLD_SHA
        for name in resources:
            loose=p.REPO/'assets/asset-patch'/p.member(('common',p.hrel(name)))
            if loose.exists():
                assert loose.read_bytes()==(work/'before'/name).read_bytes(), ('loose resource differs from effective preimage',name)
        backups=[]
        for target in delivery:
            resolved=target.resolve()
            assert resolved.is_relative_to(p.REPO.resolve()) and not resolved.is_relative_to((p.REPO/'.cdn').resolve())
            backup=work/'backup'/target.relative_to(p.REPO)
            assert not backup.exists(), 'preserve previous preimage'
            if target.exists():
                backup.parent.mkdir(parents=True,exist_ok=True); backup.write_bytes(target.read_bytes())
            backups.append(dict(path=str(target),existed=target.exists()))
        p.savej(work/'backup-files.json',backups)
        for target,b in delivery.items():
            target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(b)
        final,rows,odds,raw,_=effective.load()
        assert final.manifest['patches'][:-1]==chain.manifest['patches'][:-1]
        assert all(raw[n]==b for n,b in resources.items())
        live=runtime(); assert validate(live['gachas'],rows,odds,live['characters'])==report['checks']
        report['source_applied']=True
        p.savej(p.REPO/AUDIT/'report.json',report)
        p.savej(work/'report.json',report)
    print(json.dumps(dict(checks=report['checks'],changed_pools=len(report['changed_server_pools']),
        promotion_pairs=len(report['promotions']),client_resources=len(report['resources']),archive_size=report['archive']['size'],
        sha256=report['archive']['sha256'],source_applied=report['source_applied'])))


if __name__=='__main__': main()
