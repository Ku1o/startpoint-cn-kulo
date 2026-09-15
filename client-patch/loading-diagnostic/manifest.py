"""Append compiled Android components without reserializing any existing XML node."""
import struct

ANDROID='http://schemas.android.com/apk/res/android'
NONE=0xffffffff

def chunks(data):
    kind,header,total=struct.unpack_from('<HHI',data)
    assert kind==3 and header==8 and total==len(data)
    p=header;out=[]
    while p<len(data):
        kind,head,size=struct.unpack_from('<HHI',data,p)
        assert size>=head>=8 and p+size<=len(data)
        out.append(data[p:p+size]);p+=size
    assert p==len(data)
    return out

def kind(chunk):return struct.unpack_from('<H',chunk)[0]

def length(data,p,utf8):
    if utf8:
        n=data[p];p+=1
        if n&0x80:n=((n&0x7f)<<8)|data[p];p+=1
    else:
        n=struct.unpack_from('<H',data,p)[0];p+=2
        if n&0x8000:n=((n&0x7fff)<<16)|struct.unpack_from('<H',data,p)[0];p+=2
    return n,p

class Pool:
    def __init__(self,raw):
        self.raw=raw;self.header=struct.unpack_from('<H',raw,2)[0]
        self.count,self.style_count,self.flags,self.start,self.style_start=struct.unpack_from('<5I',raw,8)
        self.offsets=list(struct.unpack_from('<'+str(self.count)+'I',raw,self.header))
        self.styles=raw[self.header+4*self.count:self.header+4*(self.count+self.style_count)]
        self.blob=bytearray(raw[self.start:self.style_start or len(raw)])
        self.style_data=raw[self.style_start:] if self.style_start else b''
        self.strings=[]
        for off in self.offsets:
            n,p=length(self.blob,off,bool(self.flags&0x100))
            if self.flags&0x100:
                n,p=length(self.blob,p,True);text=self.blob[p:p+n].decode('utf8')
            else:text=self.blob[p:p+2*n].decode('utf-16le')
            self.strings.append(text)
    def add(self,value):
        if value in self.strings:return self.strings.index(value)
        self.offsets.append(len(self.blob));self.strings.append(value)
        if self.flags&0x100:
            data=value.encode('utf8');units=len(value.encode('utf-16le'))//2
            def size(n):return bytes([n]) if n<128 else bytes([(n>>8)|0x80,n&255])
            self.blob+=size(units)+size(len(data))+data+b'\0'
        else:
            data=value.encode('utf-16le');units=len(data)//2
            assert units<32768;self.blob+=struct.pack('<H',units)+data+b'\0\0'
        return len(self.strings)-1
    def serialize(self):
        blob=bytes(self.blob);blob+=b'\0'*((-len(blob))%4)
        start=self.header+4*len(self.offsets)+len(self.styles)
        style_start=start+len(blob) if self.style_count else 0
        raw=bytearray(self.raw[:self.header]);size=start+len(blob)+len(self.style_data)
        struct.pack_into('<I',raw,4,size)
        struct.pack_into('<5I',raw,8,len(self.offsets),self.style_count,self.flags&~1,start,style_start)
        return bytes(raw)+struct.pack('<'+str(len(self.offsets))+'I',*self.offsets)+self.styles+blob+self.style_data

def attr_ids(rows):
    raw=next(c for c in rows if kind(c)==0x180)
    return list(struct.unpack_from('<'+str((len(raw)-8)//4)+'I',raw,8))

def remap_node(raw,mapping):
    data=bytearray(raw);k=kind(data)
    def change(at):
        old=struct.unpack_from('<I',data,at)[0]
        if old!=NONE:struct.pack_into('<I',data,at,mapping[old])
    change(12) # optional comment string
    if k in (0x102,0x103):change(16);change(20)
    else:raise AssertionError('unexpected component XML chunk '+hex(k))
    if k==0x102:
        attr_start,attr_size,count=struct.unpack_from('<3H',data,24)
        assert attr_size==20
        for i in range(count):
            at=16+attr_start+i*attr_size
            change(at);change(at+4);change(at+8)
            if data[at+15]==3:change(at+16)
    return bytes(data)

def merge(original,template,old_uuid,new_uuid):
    assert original.count(old_uuid.encode('utf-16le'))==1
    renewed=original.replace(old_uuid.encode('utf-16le'),new_uuid.encode('utf-16le'))
    base=chunks(renewed);extra=chunks(template)
    pool=Pool(next(c for c in base if kind(c)==1));old_strings=list(pool.strings)
    donor=Pool(next(c for c in extra if kind(c)==1));mapping={i:pool.add(x) for i,x in enumerate(donor.strings)}
    ids=attr_ids(base);original_ids=list(ids);ids.extend([0]*(len(pool.strings)-len(ids)))
    for i,value in enumerate(attr_ids(extra)):
        if value:
            at=mapping[i];assert ids[at] in (0,value);ids[at]=value
    assert ids[:len(original_ids)]==original_ids
    nodes=[];stack=[];in_application=False
    for raw in extra:
        k=kind(raw)
        if k==0x102:
            name=donor.strings[struct.unpack_from('<I',raw,20)[0]]
            if in_application:nodes.append(remap_node(raw,mapping))
            stack.append(name)
            if name=='application':in_application=True
        elif k==0x103:
            name=stack.pop()
            if name=='application':in_application=False
            elif in_application:nodes.append(remap_node(raw,mapping))
    assert nodes and not stack
    result=[];inserted_at=None
    for raw in base:
        k=kind(raw)
        if k==1:result.append(pool.serialize())
        elif k==0x180:result.append(struct.pack('<HHI',0x180,8,8+4*len(ids))+struct.pack('<'+str(len(ids))+'I',*ids))
        else:
            if k==0x103 and pool.strings[struct.unpack_from('<I',raw,20)[0]]=='application':
                assert inserted_at is None;inserted_at=len(result);result.extend(nodes)
            result.append(raw)
    assert inserted_at is not None
    raw=b''.join(result);out=struct.pack('<HHI',3,8,len(raw)+8)+raw
    rebuilt=chunks(out);readback=Pool(next(c for c in rebuilt if kind(c)==1))
    assert readback.strings[:len(old_strings)]==old_strings
    restored=rebuilt[:inserted_at]+rebuilt[inserted_at+len(nodes):]
    assert len(restored)==len(base)
    for a,b in zip(base,restored):
        if kind(a) not in (1,0x180):assert a==b
    return out,{'original_xml_nodes_unchanged':True,'added_xml_chunks':len(nodes),
                'original_strings':len(old_strings),'final_strings':len(readback.strings),'original_resource_ids_preserved':True}
