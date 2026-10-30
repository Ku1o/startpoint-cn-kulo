"""Create two half-size visual layouts while retaining source pixels/timelines."""
import hashlib
import sys
import zlib


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _decode(raw, reader_type):
    inflater = zlib.decompressobj(-15)
    plain = inflater.decompress(raw) + inflater.flush()
    assert inflater.eof and not inflater.unused_data and not inflater.unconsumed_tail
    reader = reader_type(plain)
    value = reader.read_value()
    assert reader.pos == len(plain)
    return value


def _parts(atlas, frame, total):
    images, unique, segments = [], {}, []
    previous_end = 0
    for row in atlas:
        assert row['n'].startswith(frame['name'])
        end = int(row['n'][len(frame['name']):])
        assert previous_end < end <= total
        identity = tuple(row.get(key, 0) for key in ('x', 'y', 'w', 'h', 'fx', 'fy', 'fw', 'fh'))
        if identity not in unique:
            unique[identity] = len(images)
            images.append({'s': False, 'p': row['n']})
        segments.append({'s': previous_end, 'i': unique[identity],
                         'l': [{'m': 255, 't': end - previous_end}]})
        previous_end = end
    assert previous_end == total
    return {'i': images, 'g': [{'t': total, 's': segments}], 'm': [],
            'a': [1] * len(images), 'o': [],
            't': [{'a': 2048, 'b': 0, 'c': 0, 'd': 2048,
                   'x': int(frame['x'] * 2048), 'y': int(frame['y'] * 2048)}],
            'c': [], 's': frame['scale']}


def build(context, spec):
    """Return only normal/special parts; no PNG, atlas, timeline or DSL output."""
    sys.path.insert(0, str(context.repo / 'tools/fantasy-gauntlet-mod-tools'))
    from wf_mod_tool import AMF3Reader
    from wf_dsl import encode_amf3
    baseline = {}
    for row in spec['baselineResources']:
        raw = context.get(row['root'], row['logical'])
        assert isinstance(raw, bytes) and len(raw) == row['bytes'] and _sha(raw) == row['sha256']
        baseline[row['logical']] = raw
    result = {}
    assert spec['constraints']['innerScale'] == 0.5
    for variant in spec['variants']:
        atlas = _decode(baseline[variant['atlas']], AMF3Reader)
        frame = _decode(baseline[variant['frame']], AMF3Reader)
        timeline = _decode(baseline[variant['timeline']], AMF3Reader)
        assert frame['scale'] == 6 and frame['x'] == frame['y'] == -128 and frame['smoothing'] is False
        assert len(atlas) == variant['atlasRows']
        assert [sequence['name'] for sequence in timeline['sequences']] == variant['selectors']
        total = max(sequence['end'] for sequence in timeline['sequences'])
        assert total == variant['totalTicks']
        parts = _parts(atlas, frame, total)
        assert len(parts['i']) == sum(parts['a']) == variant['imagePoolCapacity']
        assert parts['t'] == [{'a': 2048, 'b': 0, 'c': 0, 'd': 2048, 'x': -262144, 'y': -262144}]
        # Segment coverage mirrors FrameAnimationSource's cumulative end ticks,
        # including special's first-cell pre-roll before its selector starts.
        covered = 0
        for segment, source in zip(parts['g'][0]['s'], atlas):
            assert segment['s'] == covered and segment['l'][0]['m'] == 255
            covered += segment['l'][0]['t']
            assert covered == int(source['n'][len(frame['name']):])
        assert covered == total
        compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
        raw = compressor.compress(encode_amf3(parts)) + compressor.flush()
        assert _decode(raw, AMF3Reader) == parts
        result[('common', variant['output'])] = raw
    assert set(result) == {(row['root'], row['logical']) for row in spec['outputResources']}
    for row in spec['outputResources']:
        raw = result[(row['root'], row['logical'])]
        assert len(raw) == row['bytes'] and _sha(raw) == row['sha256']
    return result
