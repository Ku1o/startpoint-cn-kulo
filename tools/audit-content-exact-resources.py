#!/usr/bin/env python3
"""Read bounded logical winners from the actual chain; never write resources/CDN."""
import argparse, hashlib, importlib.util, io, json, sys, zipfile
from pathlib import Path
sys.dont_write_bytecode = True

def main():
    ap = argparse.ArgumentParser()
    for name in ('source', 'exporter', 'catalog', 'closure', 'output'):
        ap.add_argument('--' + name, required=True)
    a = ap.parse_args()
    load = lambda p: json.loads(Path(p).read_bytes())
    catalog, closure = load(a.catalog), load(a.closure)
    rows = {r['key']: r for r in catalog['rows']}
    start, end = 1752940800000, 1753027200000
    in_day = lambda r: not r.get('personalWindow') and (r['originalStartMs'] is None or r['originalStartMs'] <= start) and (r['originalEndMs'] is None or r['originalEndMs'] >= end - 1000)
    products = [p for p in closure['products'] if p['status'] == 'verified' and in_day(rows[p['key']])]
    parents = {p['parentKey'] for p in products if p.get('parentKey') and in_day(rows[p['parentKey']])}
    atlas_logicals = {sheet + suffix for sheet in ('item/sprite_sheet', 'item_sec/sprite_sheet') for suffix in ('.png', '.atlas.amf3.deflate')}
    wanted = sorted({l for p in products for l in p['resourceLogicals']} | {l for key in parents for l in rows[key]['definitionSources']} | atlas_logicals)
    spec = importlib.util.spec_from_file_location('catalog_exporter', a.exporter)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    inputs, source = mod.resolve(Path(a.source), wanted)
    old_inputs = {}
    def previous_raw(logical):
        if logical not in old_inputs:
            receipt = closure['resourceIdentities'].get(logical) or catalog['resources'].get(logical)
            with zipfile.ZipFile(Path(a.source) / receipt['archive']) as z:
                raw = z.read(receipt.get('member', mod.member(logical)))
            if hashlib.sha256(raw).hexdigest() != receipt['sha256']: raise ValueError('previous resource replaced: ' + logical)
            old_inputs[logical] = raw
        return old_inputs[logical]
    entries = {}
    for logical in wanted:
        previous = closure['resourceIdentities'].get(logical) or catalog['resources'].get(logical)
        current = inputs.get(logical)
        entries[logical] = {'previous': previous, 'current': current[1] if current else None,
            'unchanged': bool(current and previous and current[1]['sha256'] == previous['sha256'])}
    # Table changes are resolved by exact rows, never by overwriting the prior whole-table receipt.
    from PIL import Image
    import wf_assets
    from wf_battle_atlas_repack import decode_atlas
    def atlas(current):
        textures = {}
        for sheet in ('item/sprite_sheet', 'item_sec/sprite_sheet'):
            logical, png = sheet + '.atlas.amf3.deflate', sheet + '.png'
            image = Image.open(io.BytesIO(wf_assets.png_decode_stored(inputs[png][0] if current else previous_raw(png)))).convert('RGBA')
            for entry in decode_atlas(inputs[logical][0] if current else previous_raw(logical)):
                box = (entry['x'], entry['y'], entry['x'] + entry['w'], entry['y'] + entry['h'])
                if min(box[:2]) < 0 or box[2] > image.width or box[3] > image.height: raise ValueError('atlas rect outside image')
                # Region dimensions and rotation/frame offsets affect rendering independently of PNG bytes.
                metadata = {k: v for k, v in entry.items() if k not in ('x', 'y')}
                textures[entry['n']] = {'metadata': metadata, 'pixels': hashlib.sha256(image.crop(box).tobytes()).hexdigest()}
        return textures
    previous_textures, current_textures = atlas(False), atlas(True)
    exact_rows = {}; product_closures = {}; old_tables = {}
    parsed = {}
    for p in products:
        row = rows[p['key']]; logical = row['source']
        if logical not in inputs: continue
        if logical not in parsed: parsed[logical] = mod.parse_rows(inputs[logical][0], logical)
        value = parsed[logical].get(str(row['id']))
        exact_rows[p['key']] = {'logical': logical, 'sha256': mod.json_sha(value),
            'previousSha256': p['clientRowSha256'], 'unchanged': mod.json_sha(value) == p['clientRowSha256']}
        failures = []
        if not exact_rows[p['key']]['unchanged']: failures.append('client product master row changed')
        references = [(0, cost['id']) for cost in p['server'].get('costs', [])] + [(reward['type'], reward['id']) for reward in p['server'].get('rewards', []) if 'id' in reward]
        for kind, ident in references:
            logical = {0: 'master/item/item.orderedmap', 4: 'master/item/equipment.orderedmap', 3: 'master/character/character.orderedmap'}.get(kind)
            if logical is None: continue
            if logical not in parsed: parsed[logical] = mod.parse_rows(inputs[logical][0], logical)
            if logical not in old_tables: old_tables[logical] = mod.parse_rows(previous_raw(logical), logical)
            if old_tables[logical].get(str(ident)) != parsed[logical].get(str(ident)) or str(ident) not in parsed[logical]:
                failures.append('cost/reward master row changed or absent: ' + str(kind) + ':' + str(ident))
        textures = [p['client']['thumbnailPath']] + [x['thumbnailPath'] for x in p['client'].get('referencedItemRows', [])]
        for texture in textures:
            if texture in previous_textures:
                if previous_textures[texture] != current_textures.get(texture): failures.append('atlas texture changed: ' + texture)
            else:
                logical = texture + '.png'
                if logical not in entries or not entries[logical]['unchanged']: failures.append('standalone texture changed or missing: ' + texture)
        for logical in p['resourceLogicals']:
            if entries[logical]['unchanged'] or logical in atlas_logicals or logical.endswith('.orderedmap'): continue
            failures.append('resource changed: ' + logical)
        product_closures[p['key']] = {'verified': not failures, 'failures': failures,
            'exactProductRowUnchanged': exact_rows[p['key']]['unchanged'], 'costRewardMasterRowsCompared': len(references), 'texturesCompared': len(textures)}
    result = {'schemaVersion': 1, 'source': source, 'resources': entries, 'productRows': exact_rows, 'productClosures': product_closures,
        'productsConsidered': len(products), 'parentsConsidered': len(parents), 'resourceLogicals': len(wanted),
        'changedResources': [l for l, v in entries.items() if not v['unchanged']],
        'scope': 'current common/Android logical winners only; no CDN write or player/database read'}
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    Path(a.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({**{k: result[k] for k in ('productsConsidered', 'parentsConsidered', 'resourceLogicals', 'changedResources')}, 'productsClosed': sum(v['verified'] for v in product_closures.values()), 'failures': {k: v['failures'] for k, v in product_closures.items() if not v['verified']}}))

if __name__ == '__main__': main()
