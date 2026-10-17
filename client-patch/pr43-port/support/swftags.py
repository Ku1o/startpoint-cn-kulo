"""SWF tag parsing helpers; provenance and license in SOURCES.md."""
import struct
import zlib

def load_swf(path):
    raw = open(path,'rb').read()
    sig = raw[:3]
    ver = raw[3]
    filelen = struct.unpack_from('<I', raw, 4)[0]
    if sig == b'FWS':
        body = raw[8:]
    elif sig == b'CWS':
        body = zlib.decompress(raw[8:])
    else:
        raise SystemExit('unsupported sig %r' % sig)
    return sig, ver, filelen, body

def skip_rect(body):
    nbits = body[0] >> 3
    total = 5 + 4*nbits
    return (total + 7)//8

def iter_tags(body):
    off = skip_rect(body)
    off += 4  # framerate(2) + framecount(2)
    while off < len(body):
        if off+2 > len(body): break
        th = struct.unpack_from('<H', body, off)[0]
        code = th >> 6
        length = th & 0x3f
        hdr = 2
        if length == 0x3f:
            length = struct.unpack_from('<I', body, off+2)[0]
            hdr = 6
        yield code, off, hdr, length
        off += hdr + length
        if code == 0:
            break
