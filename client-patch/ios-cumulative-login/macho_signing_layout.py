"""Keep loader metadata outside the replaceable Mach-O signature tail."""
import struct


def load_commands(data):
    assert struct.unpack_from('<I',data)[0]==0xfeedfacf,'64-bit little-endian Mach-O required'
    pos=32
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        cmd,size=struct.unpack_from('<II',data,pos)
        assert size>=8 and pos+size<=len(data),'invalid load command'
        yield pos,cmd,bytes(data[pos:pos+size])
        pos+=size
    assert pos==32+struct.unpack_from('<I',data,20)[0]


def signature_range(data):
    rows=[(pos,*struct.unpack_from('<II',raw,8)) for pos,cmd,raw in load_commands(data) if cmd==0x1d]
    assert len(rows)==1,'one LC_CODE_SIGNATURE required'
    return rows[0]


def string_table(data):
    rows=[(pos,*struct.unpack_from('<II',raw,16)) for pos,cmd,raw in load_commands(data) if cmd==2]
    assert len(rows)==1 and rows[0][1]>0 and rows[0][2]>0,'one nonempty symbol string table required'
    return rows[0]


def ldid_code_limit(data):
    # TrollStore's ldid (aaf8f23) Allocate() uses stroff + strsize in preference
    # to LC_CODE_SIGNATURE.dataoff, then aligns the resulting code limit to 16.
    _,offset,size=string_table(data)
    return (offset+size+15)&~15


def linkedit_ranges(data):
    """All offset/count metadata advertised by supported load commands."""
    result=[]
    blobs={0x1e,0x26,0x29,0x2b,0x2e,0x80000033,0x80000034}
    for _,cmd,raw in load_commands(data):
        if cmd in (0x22,0x80000022):
            fields=[(8+i*8,1,n) for i,n in enumerate(('rebase','bind','weak_bind','lazy_bind','export'))]
        elif cmd==2:fields=[(8,16,'symbols'),(16,1,'strings')]
        elif cmd==0xb:fields=[(32,8,'toc'),(40,56,'modules'),(48,4,'external_refs'),(56,4,'indirect_symbols'),(64,8,'external_relocations'),(72,8,'local_relocations')]
        elif cmd in blobs:fields=[(8,1,hex(cmd))]
        else:continue
        for at,width,name in fields:
            offset,count=struct.unpack_from('<II',raw,at)
            if count:
                assert offset,'nonempty metadata has no file offset'
                result.append(dict(name=name,offset=offset,size=count*width))
    return result


def assert_signable_layout(data):
    _,sigoff,sigsize=signature_range(data)
    assert sigoff%16==0 and sigsize>0,'invalid signature range'
    assert sigoff+sigsize==len(data),'data after replaceable code signature'
    links=[(pos,raw) for pos,cmd,raw in load_commands(data) if cmd==0x19 and raw[8:24].rstrip(b'\0')==b'__LINKEDIT']
    assert len(links)==1
    _,link=links[0];vm,vs,off,fs=struct.unpack_from('<QQQQ',link,24)
    assert off+fs==len(data) and fs<=vs and off<=sigoff
    ranges=linkedit_ranges(data)
    for row in ranges:
        assert off<=row['offset'] and row['offset']+row['size']<=sigoff,('loader metadata overlaps signature tail',row)
    limit=ldid_code_limit(data)
    assert limit==sigoff,('ldid truncates after symbol strings',hex(limit),hex(sigoff))
    for row in ranges:
        assert row['offset']+row['size']<=limit,('ldid would discard loader metadata',row)
    return dict(signature_offset=sigoff,signature_size=sigsize,signature_is_last=True,
        loader_metadata_before_signature=True,ldid_code_limit=limit,ldid_metadata_preserved=True,metadata_ranges=ranges)


def insert_before_string_table(data,payload):
    """Keep the symbol string table last so ldid cannot discard this payload."""
    assert_signable_layout(data)
    command,sigoff,size=signature_range(data)
    symtab,at,strsize=string_table(data)
    for row in linkedit_ranges(data):
        if row['name']!='strings':
            assert row['offset']+row['size']<=at,('metadata after string-table insertion point',row)
    padded=bytes(payload)+bytes((-len(payload))%16)
    data[at:at]=padded
    struct.pack_into('<I',data,symtab+16,at+len(padded))
    struct.pack_into('<I',data,command+8,sigoff+len(padded))
    for pos,cmd,raw in load_commands(data):
        if cmd==0x19 and raw[8:24].rstrip(b'\0')==b'__LINKEDIT':
            off=struct.unpack_from('<Q',raw,40)[0];fs=len(data)-off
            struct.pack_into('<Q',data,pos+48,fs)
            struct.pack_into('<Q',data,pos+32,(fs+0x3fff)&~0x3fff)
    assert signature_range(data)[1]+size==len(data)
    return at
