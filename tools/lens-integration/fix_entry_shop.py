"""Append the missing Five Boss navigation/shop rows to the effective chain.

The weapon row is copied from the already active server CDN master. Existing
master leaves stay byte-identical. The banner is a new text-based UI asset;
no donor/pristine artwork is edited. Local delivery is an explicit flag.
"""
import argparse
import copy
import io
import json
import os
from pathlib import Path
import shutil
import zipfile
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
import prepare_content as p

STAGE = 'master/quest/boss_battle_stage_node.orderedmap'
CATEGORY = 'master/shop/boss_coin_shop_category.orderedmap'
SHOP = 'master/shop/boss_coin_shop.orderedmap'
BANNER = 'quest/boss_battle/banner/mod_five_boss_exchange.png'


def validate_navigation(blobs, server_shop):
    stages = p.rawmap(p.rawmap(blobs[STAGE])['1'])
    assert '99' in stages, 'missing Five Boss stage entry'
    stage = p.csvrows(stages['99'])[0]
    assert len(stage) == 14 and stage[2] == '1' and stage[4] == '(None)'
    assert stage[6] == '99' and stage[1] == '五重决战'
    categories = p.rawmap(blobs[CATEGORY])
    assert '99' in categories, 'missing Five Boss shop category'
    category = p.csvrows(categories['99'])[0]
    assert len(category) == 13 and category[3:8] == ['2', '1', '99', '1', '1099001']
    assert category[9] + '.png' == BANNER
    products = p.rawmap(blobs[SHOP])
    for key, expected in server_shop['99'].items():
        assert key in products, f'missing client product {key}'
        row = p.csvrows(products[key])[0]
        assert len(row) == 50 and row[0] == '99'
        costs = [{'id': int(row[n]), 'amount': int(row[n+1])}
                 for n in (17, 19, 21, 23) if row[n] != '(None)']
        assert costs == expected['costs']
        assert int(row[32]) == expected['rewards'][0]['type']
        assert int(row[33]) == expected['rewards'][0]['id']
        assert int(row[34]) == expected['rewards'][0]['count']
        assert int(row[28]) == expected['stock']
    return {'stage': 1099, 'quest': 1099001, 'category': 99,
            'products': sorted(server_shop['99'])}


def banner(font_path):
    # Simple UI typography and geometry, generated from code rather than artwork.
    im = Image.new('RGB', (1000, 184), '#14202f')
    d = ImageDraw.Draw(im)
    d.polygon([(0, 0), (160, 0), (80, 184), (0, 184)], fill='#23546a')
    d.polygon([(790, 0), (1000, 0), (1000, 184), (710, 184)], fill='#254758')
    d.rectangle((0, 174, 1000, 183), fill='#d5b976')
    d.text((116, 18), '五重决战', font=ImageFont.truetype(str(font_path), 70), fill='#ffffff')
    d.text((122, 113), '终式武装 · 入场凭证兑换',
           font=ImageFont.truetype(str(font_path), 30), fill='#d5b976')
    out = io.BytesIO(); im.save(out, format='PNG')
    raw = out.getvalue(); encoded = p.wf_assets.png_encode(raw)
    assert p.wf_assets.png_decode_stored(encoded) == raw
    return encoded, raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--font', type=Path, required=True)
    ap.add_argument('--publish-local', action='store_true')
    args = ap.parse_args(); w = args.work.resolve(); w.mkdir(parents=True, exist_ok=True)
    chain = p.Chain(); assert chain.tail == '1.4.102', 're-review changed chain first'
    old = {name: chain.get(('common', p.hrel(name))) for name in (STAGE, CATEGORY, SHOP)}
    stage_root = p.rawmap(old[STAGE]); stage_rows = p.rawmap(stage_root['1'])
    assert '99' not in stage_rows
    stage = p.csvrows(stage_rows['1'])[0]
    assert len(stage) == 14
    stage[0:3] = ['高难挑战', '五重决战', '1']
    stage[4:11] = ['(None)', '', '99', '10000144', '10000145', '10000146', '10000147']
    stage[11] = 'quest/thumbnail/multi_battle/mod_five_boss'
    stage[13] = '0'  # no official external event webpage for this local mode
    stage_rows['99'] = p.packcsv([stage]); stage_root['1'] = p.packmap(stage_rows)
    categories = p.rawmap(old[CATEGORY]); assert '99' not in categories
    category = p.csvrows(categories['1'])[0]
    assert len(category) == 13
    category[0:9] = ['mod_five_boss', '2999', '(None)', '2', '1', '99', '1', '1099001', '(None)']
    category[9] = BANNER.removesuffix('.png')
    categories['99'] = p.packcsv([category])
    products = p.rawmap(old[SHOP]); assert '990099001' not in products
    cdn = p.readj(p.REPO/'assets/cdndata/boss_coin_shop.json')
    products['990099001'] = p.packcsv(cdn['990099001'])
    blobs = {STAGE: p.packmap(stage_root), CATEGORY: p.packmap(categories), SHOP: p.packmap(products)}
    server_shop = p.readj(p.REPO/'assets/boss_coin_shop.json')
    checks = validate_navigation(blobs, server_shop)
    # The actual pre-fix client must fail, so a missing master row cannot pass
    # merely because server-side battle/settlement tests succeed.
    try: validate_navigation(old, server_shop)
    except AssertionError: pass
    else: raise AssertionError('preimage unexpectedly passes navigation checks')
    for logical in old:
        before = p.rawmap(old[logical]); after = p.rawmap(blobs[logical])
        for key, value in before.items():
            if logical == STAGE and key == '1':
                for child, raw in p.rawmap(value).items(): assert p.rawmap(after[key])[child] == raw
            else: assert after[key] == value
    for logical in [stage[11]+'.png', stage[12]+'.png', category[10]+'.png',
                    cdn['990099001'][0][12]+'.png']:
        raw = chain.get(('common', p.hrel(logical)))
        assert raw is not None, f'missing navigation image {logical}'
        Image.open(io.BytesIO(p.wf_assets.png_decode_stored(raw))).load()
    png, preview = banner(args.font)
    blobs[BANNER] = png; (w/'banner-preview.png').write_bytes(preview)
    base, target = chain.tail, '1.4.103'
    archive_name = f'pinball-{base}-{target}-1-five-boss-entry-shop.zip'
    payloads = {p.member(('common', p.hrel(logical))): raw for logical, raw in blobs.items()}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for member, raw in sorted(payloads.items()):
            info = zipfile.ZipInfo(member, (2026,9,8,0,0,0)); info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, raw)
    raw_zip = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as z:
        assert z.testzip() is None
        for member, raw in payloads.items(): assert z.read(member) == raw
        assert p.wf_assets.png_decode_stored(z.read(p.member(('common',p.hrel(BANNER))))) == preview
    integrity = {'name':archive_name,'size':len(raw_zip),'sha256':p.sha(raw_zip),
                 'members':len(payloads),'files':sorted(payloads)}
    record = {'id':'five-boss-entry-shop-1.4.103','type':'patch','name':'五重决战入口与兑换跳转修复',
              'description':'补齐讨伐入口、兑换分类及终式武器商品。','version':target,'depends_on':base,
              'enabled':True,'archive':archive_name,'archive_size':len(raw_zip),'chain':[archive_name],
              'archive_integrity':[integrity],'files':sorted(payloads),'created_at':'2026-09-08',
              'local_test_only':True,'required_local_platform':'android'}
    manifest = copy.deepcopy(chain.manifest); manifest['patches'].append(record);manifest['cdn_version']=target
    new_manifest = (json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
    report = {'status':'passed_static_navigation_and_shop_checks','version':target,'checks':checks,
              'original_rows_preserved':True,'preimage_rejected':True,'images_resolve':True,
              'baseline_manifest_sha256':p.sha(chain.manifest_bytes),'archive':integrity,
              'source_reads':chain.reads,'device_tested':False,'runtime_delivered':False}
    (w/'manifest.before.json').write_bytes(chain.manifest_bytes)
    for logical, raw in blobs.items():
        target_path=w/'prepared'/p.member(('common',p.hrel(logical)));target_path.parent.mkdir(parents=True,exist_ok=True);target_path.write_bytes(raw)
    (w/archive_name).write_bytes(raw_zip);(w/'manifest.after.json').write_bytes(new_manifest)
    p.savej(w/'report.json',report)
    if args.publish_local:
        runtime=Path('F:/startpoint-cn-main').resolve(); rel_manifest='assets/asset-patch/manifest.json'
        assert (p.REPO/rel_manifest).read_bytes()==chain.manifest_bytes
        assert (runtime/rel_manifest).read_bytes()==chain.manifest_bytes, 'runtime has different patch chain'
        delivery={f'assets/asset-patch/{member}':raw for member,raw in payloads.items()}
        delivery[f'assets/asset-patch/active/{archive_name}']=raw_zip
        delivery[rel_manifest]=new_manifest
        backup=runtime/'.codex-backups'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-five-boss-entry-shop')
        receipt=[]
        # Preflight every resolved destination before the first write.
        for rel,raw in delivery.items():
            for root in (p.REPO,runtime):
                dest=(root/rel).resolve();assert dest.is_relative_to(root.resolve())
                assert '.cdn' not in dest.parts
                if '/active/' in rel: assert not dest.exists()
            dest=runtime/rel
            receipt.append({'path':rel,'before_sha256':p.sha(dest.read_bytes()) if dest.exists() else None,'sha256':p.sha(raw)})
        for root,save_root in ((p.REPO,w/'source-before'),(runtime,backup)):
            for rel,raw in delivery.items():
                dest=root/rel
                if dest.exists():
                    saved=save_root/rel;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,saved)
                dest.parent.mkdir(parents=True,exist_ok=True)
                temp=dest.with_name(dest.name+'.entry-shop-tmp');assert not temp.exists()
                temp.write_bytes(raw);os.replace(temp,dest)
                assert dest.read_bytes()==raw
        report.update(runtime_delivered=True,backup=str(backup),delivery=receipt)
        p.savej(w/'report.json',report)
        p.savej(p.REPO/'assets/asset-patch/audit/five-boss-entry-shop-1.4.103/report.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('source_reads','delivery')},ensure_ascii=False))


if __name__=='__main__': main()
