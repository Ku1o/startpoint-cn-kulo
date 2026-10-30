"""Replace the existing ticket cell and standalone image without metadata edits."""
import hashlib
import io
import sys
from PIL import Image


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _image(raw, assets):
    assert raw[:8] == b'\x89png\r\n\x1a\n'
    ordinary = assets.png_decode_stored(raw)
    assert ordinary == b'\x89PNG\r\n\x1a\n' + raw[8:]
    with Image.open(io.BytesIO(ordinary)) as probe:
        assert probe.format == 'PNG' and getattr(probe, 'n_frames', 1) == 1
        probe.verify()
    with Image.open(io.BytesIO(ordinary)) as image:
        image.load()
        return image.convert('RGBA')


def build(context, spec):
    """Return exactly two encoded resources; the context owns all IO policy."""
    tools = context.repo / 'tools/fantasy-gauntlet-mod-tools'
    sys.path.insert(0, str(tools))
    import wf_assets
    import wf_battle_atlas_repack as codec
    baseline = {}
    for row in spec['baselineResources']:
        raw = context.get(row['root'], row['logical'])
        assert isinstance(raw, bytes) and len(raw) == row['bytes'] and _sha(raw) == row['sha256']
        baseline[row['logical']] = raw
    source = context.input(spec['input']['relative']).read_bytes()
    assert len(source) == spec['input']['bytes'] and _sha(source) == spec['input']['sha256']
    stored = wf_assets.png_encode(source)
    assert wf_assets.png_decode_stored(stored) == source
    limits = spec['constraints']
    icon_path, sheet_path, atlas_path = limits['standalone'], limits['sheet'], limits['atlas']
    atlas = codec.decode_atlas(baseline[atlas_path])
    assert len(atlas) == limits['atlasFrameCount']
    frames = [row for row in atlas if row['n'] == limits['ticketFrame']['n']]
    assert frames == [limits['ticketFrame']]
    generic = [row for row in atlas if row['n'] == limits['genericFrame']['n']]
    assert generic == [limits['genericFrame']]
    ticket = frames[0]
    box = (ticket['x'], ticket['y'], ticket['x'] + ticket['w'], ticket['y'] + ticket['h'])
    images = []
    try:
        icon, old, old_icon = (_image(stored, wf_assets), _image(baseline[sheet_path], wf_assets),
                               _image(baseline[icon_path], wf_assets))
        images.extend((icon, old, old_icon))
        assert list(icon.size) == spec['input']['size'] == [20, 20]
        assert list(old.size) == limits['sheetSize']
        old_cell = old.crop(box)
        images.append(old_cell)
        assert old_cell.tobytes() == old_icon.tobytes()
        after = old.copy()
        images.append(after)
        # No compositing mask: transparent pixels must replace old opaque pixels.
        after.paste(icon, (ticket['x'], ticket['y']))
        restored = after.copy()
        images.append(restored)
        restored.paste(old_cell, (ticket['x'], ticket['y']))
        assert restored.tobytes() == old.tobytes()
        new_cell = after.crop(box)
        images.append(new_cell)
        assert new_cell.tobytes() == icon.tobytes()
        generic = generic[0]
        generic_box = (generic['x'], generic['y'], generic['x'] + generic['w'], generic['y'] + generic['h'])
        first, second = old.crop(generic_box), after.crop(generic_box)
        images.extend((first, second))
        assert first.tobytes() == second.tobytes()
        encoded_sheet = codec.encode_png(after)
        readback = _image(encoded_sheet, wf_assets)
        images.append(readback)
        assert readback.size == after.size and readback.tobytes() == after.tobytes()
        result = {('common', icon_path): stored, ('common', sheet_path): encoded_sheet}
        assert set(result) == {(row['root'], row['logical']) for row in spec['outputResources']}
        for row in spec['outputResources']:
            raw = result[(row['root'], row['logical'])]
            assert len(raw) == row['bytes'] and _sha(raw) == row['sha256']
        return result
    finally:
        for image in reversed(images):
            image.close()
