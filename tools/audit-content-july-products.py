#!/usr/bin/env python3
"""Audit products omitted by an older date snapshot against actual current accessors."""
import argparse, hashlib, importlib.util, io, json, sys
from pathlib import Path
sys.dont_write_bytecode = True

def main():
    ap = argparse.ArgumentParser()
    for name in ('repo', 'source', 'exporter', 'review', 'closure', 'accessors', 'output'):
        ap.add_argument('--' + name, required=True)
    a = ap.parse_args(); repo = Path(a.repo); output = Path(a.output); output.mkdir(parents=True, exist_ok=True)
    load = lambda p: json.loads(Path(p).read_bytes())
    catalog = load(repo / 'assets/content_catalog.json'); prior = load(a.closure); accessors = load(a.accessors)
    pending = {r['key'] for r in load(a.review)['rows'] if r['group'] == 'july_pending_review'}
    rows = {r['key']: r for r in catalog['rows']}
    known = {p['key']: p for p in prior['products']}
    # The earlier bounded atlas check missed the loaded general sheet. Recheck only
    # rows whose sole prior failure was that exact texture routing gap.
    atlas_gap = 'texture:ItemThumbnail scene/general/sprite_sheet/mana_a absent from bounded common Item atlases and standalone PNG; other cache mapping unverified'
    recheck = {key for key, product in known.items() if product['status'] != 'verified'
               and product.get('missingRefs') == [atlas_gap] and not product.get('issues')}
    candidates = [r for r in catalog['rows'] if r['key'] in pending and r['type'].endswith('_shop')
                  and (r['key'] not in known or r['key'] in recheck)]
    def module(name, file):
        spec = importlib.util.spec_from_file_location(name, file); result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result); return result
    exporter = module('catalog_exporter', a.exporter)
    auditor = module('product_auditor', Path(a.exporter).with_name('audit-content-action-closure.py'))
    logicals = {r['source'] for r in candidates}
    for r in candidates:
        parent = rows.get(r.get('parentKey'))
        if parent: logicals.update(parent['definitionSources'])
    logicals.update(['master/item/item.orderedmap', 'master/item/equipment.orderedmap', 'master/character/character.orderedmap'])
    for sheet in ('item/sprite_sheet', 'item_sec/sprite_sheet', 'scene/general/sprite_sheet'):
        logicals.update([sheet + '.png', sheet + '.atlas.amf3.deflate'])
    inputs, source = exporter.resolve(Path(a.source), sorted(logicals))
    flat_tables = {r['source'] for r in candidates} | {'master/item/item.orderedmap', 'master/item/equipment.orderedmap', 'master/character/character.orderedmap'}
    tables = {logical: exporter.parse_rows(raw, logical) for logical, (raw, _) in inputs.items() if logical in flat_tables}
    from PIL import Image
    import wf_assets
    from wf_battle_atlas_repack import decode_atlas
    atlas = {}
    for sheet in ('item/sprite_sheet', 'item_sec/sprite_sheet', 'scene/general/sprite_sheet'):
        logical, png = sheet + '.atlas.amf3.deflate', sheet + '.png'
        image = Image.open(io.BytesIO(wf_assets.png_decode_stored(inputs[png][0]))); image.verify()
        image = Image.open(io.BytesIO(wf_assets.png_decode_stored(inputs[png][0])))
        for entry in decode_atlas(inputs[logical][0]):
            if min(entry['x'], entry['y']) < 0 or entry['x'] + entry['w'] > image.width or entry['y'] + entry['h'] > image.height or min(entry['w'], entry['h']) <= 0: raise ValueError('invalid atlas rectangle')
            atlas[entry['n']] = {'atlas': logical, 'sheet': png, 'region': {k: entry[k] for k in ('x', 'y', 'w', 'h')}}
    ids = set(load(repo / 'assets/item_ids.json')) | set(load(repo / 'assets/item_ids_rank_p5b.json'))
    equips = set(load(repo / 'assets/equipment_max_level.json'))
    characters = {**load(repo / 'assets/character.json'), **load(repo / 'assets/character_rank_p5b.json')}
    whitelist = load(repo / 'assets/cdn_general_shop_whitelist.json')
    products = []; needed_pngs = set()
    for row in candidates:
        key = row['key']; typ = row['type']; ident = str(row['id']); server = accessors['items'][key]['item']; raw = tables.get(row['source'], {}).get(ident)
        issues = []; missing = []; matching = {}; decoded = None; required = [row['source']]
        if not server: missing.append('server:actual getShopItemSync absent')
        if not raw: missing.append('client:master row absent')
        else:
            decoded = auditor.decode_product(typ, raw[0])
            if exporter.json_sha(raw[0]) != row['definitionDigest']: issues.append('current client row differs from catalog row identity')
            if server:
                for field in ('costs', 'rewards', 'userCost'): matching[field] = decoded[field] == server.get(field, [] if field != 'userCost' else None)
                matching['cumulativeStock'] = decoded['cumulativeLimit'] == server.get('stock')
                matching['perRequestMaximumProtected'] = isinstance(server.get('stock'), int) and server['stock'] > 0 and decoded['stockOnce'] is not None and server['stock'] <= decoded['stockOnce']
                for field, ok in matching.items():
                    if not ok: issues.append('client/server ' + field + ' differs')
                for field in ('dailyStock', 'monthlyStock'):
                    if (decoded[field] or 0) > 0: missing.append('quota:new period ledger needs exact old-history classification: ' + field)
                if server.get('maxFrequency', 0) > 0: missing.append('quota:explicit maxFrequency semantics review')
                if decoded['costScheduleId'] not in ('', '(None)'): missing.append('schedule:dynamic cost schedule not audited')
                if decoded['equipmentOnlyPossessionOne']: missing.append('ownership:client equipment-only-possession-one not proven')
                if typ == 'general_shop' and row['id'] not in whitelist: missing.append('server:general sales whitelist excludes row')
                if typ == 'event_item_shop':
                    mapping = accessors['eventMap'].get(ident)
                    client_type = {0: 0, 1: 2, 2: 6, 3: 4, 4: 9, 5: 10, 6: 11, 7: 12}.get(int(raw[0][0]))
                    if not mapping or mapping['eventType'] != client_type or str(mapping['eventId']) != raw[0][1]: issues.append('client/server parent mapping differs')
                decoded['referencedItemRows'] = []
                refs = [(0, c['id']) for c in server.get('costs', [])] + [(r['type'], r['id']) for r in server.get('rewards', []) if 'id' in r]
                for kind, value in refs:
                    logical = {0: 'master/item/item.orderedmap', 4: 'master/item/equipment.orderedmap', 3: 'master/character/character.orderedmap'}.get(kind)
                    if logical:
                        required.append(logical)
                        if str(value) not in tables[logical]: missing.append('client:cost/reward definition absent ' + str(kind) + ':' + str(value))
                        if kind == 0 and value not in ids or kind == 4 and str(value) not in equips or kind == 3 and str(value) not in characters: missing.append('server:cost/reward definition absent ' + str(kind) + ':' + str(value))
                    if kind == 0 and str(value) in tables['master/item/item.orderedmap']:
                        item = tables['master/item/item.orderedmap'][str(value)][0]
                        decoded['referencedItemRows'].append({'id': value, 'rowSha256': exporter.json_sha([item]), 'thumbnailPath': item[3]})
                for texture in [decoded['thumbnailPath']] + [r['thumbnailPath'] for r in decoded['referencedItemRows']]:
                    if texture in atlas: required += [atlas[texture]['atlas'], atlas[texture]['sheet']]
                    else: needed_pngs.add(texture + '.png'); required.append(texture + '.png')
                if decoded['thumbnailPath'] in atlas: decoded['textureRoute'] = {'kind': 'loaded_common_item_subtexture', **atlas[decoded['thumbnailPath']]}
        products.append({'key': key, 'status': 'pending', 'ruleVerified': bool(server and decoded and all(matching.values()) and not missing and not issues),
            'server': server, 'client': decoded, 'clientRowSha256': exporter.json_sha(raw), 'parentKey': row.get('parentKey'), 'matches': matching,
            'issues': issues, 'missingRefs': missing, 'resourceLogicals': list(dict.fromkeys(required)), 'mayEnable': False,
            'condition': 'current actual accessor, real Values field semantics and common-group thumbnails; no runtime/player entitlement assertion'})
    if needed_pngs:
        extra, extra_source = exporter.resolve(Path(a.source), sorted(needed_pngs))
        if extra_source['manifestSha256'] != source['manifestSha256']: raise ValueError('manifest changed during audit')
        inputs.update(extra)
    for product in products:
        for logical in product['resourceLogicals']:
            if logical not in inputs: product['missingRefs'].append('texture:unresolved common atlas or standalone ' + logical)
            elif logical in needed_pngs:
                try: Image.open(io.BytesIO(wf_assets.png_decode_stored(inputs[logical][0]))).verify()
                except Exception as error: product['missingRefs'].append('texture:strict PNG decode ' + str(error))
        product['status'] = 'verified' if product['ruleVerified'] and not product['missingRefs'] else 'unsupported' if any(m.startswith('quota:') for m in product['missingRefs']) else 'unknown'
    result = {'schemaVersion': 1, 'source': source, 'products': products, 'resourceIdentities': {l: v[1] for l, v in inputs.items()},
        'counts': {status: sum(p['status'] == status for p in products) for status in ('verified', 'unknown', 'unsupported')},
        'schemaMethodReceipt': prior['clientMethodReceipt'], 'scope': 'fixed July omissions only; no resources/master/database writes'}
    (output / 'additional-products.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'candidates': len(products), **result['counts'], 'missing': sorted({m for p in products for m in p['missingRefs']}), 'issues': sorted({m for p in products for m in p['issues']})}))

if __name__ == '__main__': main()
