"""One install-time NSURLCache reset. No traversal or deletion of game files.

Calls existing Objective-C/Foundation import stubs, before the original main.
Bundle inode/timestamps distinguish replacement even when app version is equal.
"""
import struct,sys
from prepare import sha
sys.path.insert(0,'F:/codex/tools/ios-re-libs')
import keystone
import build_native as link

ATTRS=('NSFileCreationDate','NSFileModificationDate','NSFileSystemFileNumber','NSFileSize')
MARKER='cn.startpoint.startup-network-cache.install-v1'

def bindings(native):
    binary=link.lief.parse(list(native));symbols=list(binary.symbols)
    _,_,dyn=next(x for x in link.commands(native) if x[1]==0xb)
    indoff,indcount=struct.unpack_from('<II',dyn,56)
    stubs={}
    for sec in binary.sections:
        if sec.name!='__stubs':continue
        for i in range(sec.size//sec.reserved2):
            index=sec.reserved1+i;assert index<indcount
            symbol=struct.unpack_from('<I',native,indoff+4*index)[0]
            if symbol&0xc0000000:continue
            stubs[symbols[symbol].name]=sec.virtual_address+i*sec.reserved2
    selectors={}
    sec=next(s for s in binary.sections if s.name=='__objc_selrefs')
    for off in range(sec.offset,sec.offset+sec.size,8):
        pointer=struct.unpack_from('<Q',native,off)[0];at=link.file_offset(native,pointer)
        name=native[at:native.index(0,at)].decode()
        selectors[name]=sec.virtual_address+off-sec.offset
    return stubs,selectors

def build(native,address,build_id):
    stubs,selectors=bindings(native)
    required=['_objc_getClass','_objc_msgSend','_objc_autoreleasePoolPush','_objc_autoreleasePoolPop','_NSSelectorFromString']
    assert all(n in stubs for n in required)
    strings={};parts=[];calls=[];sel_reads=[]
    def emit(*lines):parts.extend(lines)
    def pointer(register,value):emit(f'adrp {register}, 0x{value&~4095:x}',f'add {register}, {register}, #{value&4095}')
    def literal(register,text):
        if text not in strings:strings[text]=0x2000+sum(len(s.encode())+1 for s in strings)
        pointer(register,address+strings[text])
    def call(name):
        calls.append(dict(instruction=len(parts),symbol=name,target=stubs[name]));emit(f'bl 0x{stubs[name]:x}')
    def sel(name):
        at=selectors[name];pointer('x1',at);emit('ldr x1, [x1]');sel_reads.append(dict(name=name,address=at))
    def send(name):sel(name);call('_objc_msgSend')
    def klass(name):literal('x0',name);call('_objc_getClass')
    def string(text):emit('mov x0, x24');literal('x2',text);send('stringWithUTF8String:')
    def put(key,value):
        string(key);emit('cbz x0, finish','mov x3, x0',f'mov x2, {value}','mov x0, x21');send('setObject:forKey:')
    emit('stp x29, x30, [sp, #-96]!','mov x29, sp','stp x19, x20, [sp, #16]',
         'stp x21, x22, [sp, #32]','stp x23, x24, [sp, #48]','stp x25, x26, [sp, #64]','stp x27, x28, [sp, #80]')
    call('_objc_autoreleasePoolPush');emit('mov x19, x0')
    klass('NSString');emit('cbz x0, finish','mov x24, x0')
    klass('NSUserDefaults');send('standardUserDefaults');emit('cbz x0, finish','mov x20, x0')
    klass('NSMutableDictionary');send('dictionary');emit('cbz x0, finish','mov x21, x0')
    string(MARKER);emit('cbz x0, finish','mov x23, x0')
    string(build_id);emit('cbz x0, finish','mov x26, x0');put('build','x26')
    klass('NSBundle');send('mainBundle');send('executablePath');emit('cbz x0, finish','mov x25, x0');put('path','x25')
    klass('NSFileManager');send('defaultManager');emit('mov x2, x25','mov x3, #0');send('attributesOfItemAtPath:error:')
    emit('cbz x0, finish','mov x22, x0')
    for name in ATTRS:
        string(name);emit('cbz x0, finish','mov x26, x0','mov x2, x0','mov x0, x22');send('objectForKey:')
        emit('cbz x0, finish','mov x2, x0','mov x3, x26','mov x0, x21');send('setObject:forKey:')
    emit('mov x0, x20','mov x2, x23');send('objectForKey:')
    emit('mov x2, x21');send('isEqual:');emit('cbnz w0, finish')
    klass('NSURLCache');send('sharedURLCache');emit('cbz x0, finish','mov x25, x0')
    string('removeAllCachedResponses');emit('cbz x0, finish');call('_NSSelectorFromString')
    emit('cbz x0, finish','mov x1, x0','mov x0, x25');call('_objc_msgSend')
    emit('mov x0, x20','mov x2, x21','mov x3, x23');send('setObject:forKey:')
    emit('mov x0, x20');send('synchronize')
    emit('finish:','mov x0, x19');call('_objc_autoreleasePoolPop')
    emit('ldp x19, x20, [sp, #16]','ldp x21, x22, [sp, #32]','ldp x23, x24, [sp, #48]',
         'ldp x25, x26, [sp, #64]','ldp x27, x28, [sp, #80]','ldp x29, x30, [sp], #96','ret')
    source='\n'.join(parts)
    assembler=keystone.Ks(keystone.KS_ARCH_ARM64,keystone.KS_MODE_LITTLE_ENDIAN)
    code=bytes(assembler.asm(source,address)[0]);assert len(code)<0x2000
    payload=code+bytes(0x2000-len(code))+b''.join(s.encode()+b'\0' for s in strings)
    return payload,dict(address=address,code_size=len(code),payload_size=len(payload),sha256=sha(payload),
        calls=calls,selectors=sel_reads,strings={text:address+off for text,off in strings.items()},
        source=source,marker=MARKER,installation_attributes=list(ATTRS),
        cleanup_api='[NSURLCache.sharedURLCache removeAllCachedResponses]',
        game_file_deletion=False,account_cookie_keychain_deletion=False)
