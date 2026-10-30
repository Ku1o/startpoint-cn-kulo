"""Reproduce theme103's adopted master row, seven visual resources and references.

The historical345 background is an explicit approved concept input. Current350
art is a separate recipe; this module never selects it or rewrites a manifest.
"""
import hashlib
import io
import sys
import zlib


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build(context, spec):
    sys.path.insert(0, str(context.repo / 'tools/fantasy-gauntlet-mod-tools'))
    from rebuild_character_edge import rawmap, packmap
    import wf_assets
    import wf_dsl
    from PIL import Image, ImageFilter
    import csv

    before = {}
    for entry in spec['baselineResources']:
        raw = context.get(entry['root'], entry['logical'])
        assert isinstance(raw, bytes) and len(raw) == entry['bytes'] and _sha(raw) == entry['sha256']
        before[entry['logical']] = raw
    source = context.external(spec['conceptInput']['alias']).read_bytes()
    assert _sha(source) == spec['conceptInput']['sha256']
    with Image.open(io.BytesIO(source)) as original:
        original.load()
        assert original.size == tuple(spec['conceptInput']['size'])
        assert original.width * 900 == original.height * 700
        background = original.convert('RGB').resize((700, 900), Image.Resampling.LANCZOS)
    opened = [background]
    try:
        alpha_source = wf_assets.png_decode_stored(before[spec['maskReference']])
        with Image.open(io.BytesIO(alpha_source)) as reference:
            reference.load()
            assert reference.size == (700, 900) and reference.mode == 'RGBA'
            alpha = reference.getchannel('A')
        opened.append(alpha)
        assert _sha(alpha.tobytes()) == spec['maskAlphaSha256']
        mask = background.convert('RGBA')
        mask.putalpha(alpha)
        reduced = background.resize((350, 450), Image.Resampling.LANCZOS)
        blur = reduced.filter(ImageFilter.GaussianBlur(spec['blurRadius']))
        opened.extend((mask, reduced, blur))

        def encode(image):
            stream = io.BytesIO()
            image.save(stream, 'PNG', optimize=True)
            stored = wf_assets.png_encode(stream.getvalue())
            assert wf_assets.png_decode_stored(stored) == stream.getvalue()
            return stored

        prefix = 'town/background/halloween2026/'
        result = {('common', prefix + 'background.png'): encode(background),
                  ('common', prefix + 'background_mask.png'): encode(mask),
                  ('common', prefix + 'background_blur.png'): encode(blur)}
        atlas_input = spec['input']
        atlas_raw = context.input(atlas_input['relative']).read_bytes()
        assert len(atlas_raw) == atlas_input['bytes'] and _sha(atlas_raw) == atlas_input['sha256']
        result[('common', 'town/particle/halloween2026/sprite_sheet.png')] = wf_assets.png_encode(atlas_raw)
        for logical, tree in spec['particleObjects'].items():
            encoder = zlib.compressobj(9, zlib.DEFLATED, -15)
            plain = wf_dsl.encode_amf3(tree)
            stored = encoder.compress(plain) + encoder.flush()
            assert wf_dsl.parse_dsl(zlib.decompress(stored, -15))['tree'] == tree
            result[('common', logical)] = stored
        master = spec['master']
        old_rows = rawmap(before[master])
        assert len(old_rows) == 18 and '103' not in old_rows
        stream = io.StringIO(newline='')
        csv.writer(stream, lineterminator='\n').writerow(spec['row'])
        new_rows = {**old_rows, '103': zlib.compress(stream.getvalue().encode('utf-8'))}
        packed = packmap(new_rows)
        assert rawmap(packed) == new_rows
        assert all(rawmap(packed)[key] == raw for key, raw in old_rows.items())
        result[('common', master)] = packed
        assert len(result) == len(spec['outputResources']) == 8
        for entry in spec['outputResources']:
            raw = result[(entry['root'], entry['logical'])]
            assert len(raw) == entry['bytes'] and _sha(raw) == entry['sha256'], entry['logical']
        return result
    finally:
        for image in reversed(opened):
            image.close()
