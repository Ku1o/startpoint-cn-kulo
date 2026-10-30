"""Build the original-pixel town's main/mask/blur resources without chain IO."""
import hashlib
import io
import sys
from PIL import Image, ImageFilter


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _image(raw, assets):
    assert raw[:8] == b'\x89png\r\n\x1a\n'
    ordinary = assets.png_decode_stored(raw)
    assert ordinary == b'\x89PNG\r\n\x1a\n' + raw[8:]
    with Image.open(io.BytesIO(ordinary)) as probe:
        assert probe.format == 'PNG' and getattr(probe, 'n_frames', 1) == 1
        probe.verify()
    image = Image.open(io.BytesIO(ordinary))
    image.load()
    return ordinary, image


def build(context, spec):
    """Return exactly three PNGs; existing349 alpha is an explicit baseline."""
    sys.path.insert(0, str(context.repo / 'tools/fantasy-gauntlet-mod-tools'))
    import wf_assets
    baseline = {}
    for row in spec['baselineResources']:
        raw = context.get(row['root'], row['logical'])
        assert isinstance(raw, bytes) and len(raw) == row['bytes'] and _sha(raw) == row['sha256']
        baseline[row['logical']] = raw
    source = context.input(spec['input']['relative']).read_bytes()
    assert len(source) == spec['input']['bytes'] and _sha(source) == spec['input']['sha256']
    assert source[:8] == b'\x89PNG\r\n\x1a\n'
    constraints = spec['constraints']
    background_path, mask_path, blur_path = constraints['background'], constraints['mask'], constraints['blur']
    main = wf_assets.png_encode(source)
    opened = []
    try:
        ordinary, background = _image(main, wf_assets)
        opened.append(background)
        assert ordinary == source and list(background.size) == spec['input']['size'] == [700, 900]
        assert background.mode == spec['input']['mode']
        rgb = background.convert('RGB')
        opened.append(rgb)
        _old_png, old_mask = _image(baseline[mask_path], wf_assets)
        opened.append(old_mask)
        assert old_mask.mode == 'RGBA' and old_mask.size == (700, 900)
        alpha = old_mask.getchannel('A')
        opened.append(alpha)
        assert _sha(alpha.tobytes()) == constraints['inheritedMaskAlphaSha256']
        mask = rgb.convert('RGBA')
        opened.append(mask)
        mask.putalpha(alpha)
        recipe = constraints['blurRecipe']
        assert recipe == {'size': [350, 450], 'resample': 'LANCZOS', 'gaussianRadius': 1.25, 'pngOptimize': True}
        reduced = rgb.resize(tuple(recipe['size']), Image.Resampling.LANCZOS)
        opened.append(reduced)
        blur = reduced.filter(ImageFilter.GaussianBlur(recipe['gaussianRadius']))
        opened.append(blur)

        def stored(image):
            buffer = io.BytesIO()
            image.save(buffer, 'PNG', optimize=True)
            return wf_assets.png_encode(buffer.getvalue())

        result = {('common', background_path): main, ('common', mask_path): stored(mask),
                  ('common', blur_path): stored(blur)}
        for (root, logical), raw in result.items():
            normal, readback = _image(raw, wf_assets)
            opened.append(readback)
            if logical == background_path:
                assert normal == source and readback.mode == background.mode
                assert readback.size == background.size and readback.tobytes() == background.tobytes()
            elif logical == mask_path:
                assert readback.mode == 'RGBA' and readback.size == (700, 900)
                read_rgb, read_alpha = readback.convert('RGB'), readback.getchannel('A')
                opened.extend((read_rgb, read_alpha))
                assert read_rgb.tobytes() == rgb.tobytes() and read_alpha.tobytes() == alpha.tobytes()
            else:
                assert readback.mode == 'RGB' and readback.size == (350, 450)
                assert readback.tobytes() == blur.tobytes()
        assert set(result) == {(row['root'], row['logical']) for row in spec['outputResources']}
        for row in spec['outputResources']:
            raw = result[(row['root'], row['logical'])]
            assert len(raw) == row['bytes'] and _sha(raw) == row['sha256']
        return result
    finally:
        for image in reversed(opened):
            image.close()
