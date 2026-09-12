"""Execute emitted arm64 cleanup code with mocked Foundation APIs, not an iPhone."""
import copy,json,struct,sys,unittest
from prepare import WORK,sha
sys.path.insert(0,str(WORK/'test-libs'))
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm64_const import UC_ARM64_REG_PC,UC_ARM64_REG_SP,UC_ARM64_REG_LR,UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2,UC_ARM64_REG_X3,UC_ARM64_REG_X19,UC_ARM64_REG_X20,UC_ARM64_REG_X21,UC_ARM64_REG_X22,UC_ARM64_REG_X23,UC_ARM64_REG_X24,UC_ARM64_REG_X25,UC_ARM64_REG_X26,UC_ARM64_REG_X27,UC_ARM64_REG_X28,UC_ARM64_REG_X29
from unicorn import arm64_const
import native_boot as boot

class Model:
    def __init__(self,native,report,payload):
        self.mu=Uc(UC_ARCH_ARM64,UC_MODE_ARM);self.objects={};self.next=0x300000000;self.mapped=set()
        self.report=report;self.native=native;self.prefs={};self.clears=0;self.persist=True;self.cache_available=True
        self.path='/private/var/containers/Bundle/Application/TEST/worldflipper.app/worldflipper'
        self.attrs=dict(zip(boot.ATTRS,('created-1','modified-1',101,132000000)))
        self.stubs,self.selectors=boot.bindings(native)
        self.names={addr:name for name,addr in self.stubs.items() if name in {r['symbol'] for r in report['calls']}}
        self.load(report['address'],payload)
        for addr in self.names:self.load(addr,b'\xc0\x03\x5f\xd6')
        for name,addr in self.selectors.items():
            if name not in {r['name'] for r in report['selectors']}:continue
            pointer=struct.unpack_from('<Q',native,boot.link.file_offset(native,addr))[0]
            self.load(addr,struct.pack('<Q',pointer));self.load(pointer,name.encode()+b'\0')
        self.stack=0x700000000;self.load(self.stack-0x10000,bytes(0x11000));self.stop=0x600000000;self.load(self.stop,b'\xc0\x03\x5f\xd6')
        self.mu.hook_add(UC_HOOK_CODE,self.on_code)
    def load(self,address,data):
        for page in range(address&~4095,(address+len(data)+4095)&~4095,4096):
            if page not in self.mapped:self.mu.mem_map(page,4096);self.mapped.add(page)
        self.mu.mem_write(address,data)
    def text(self,address):
        b=bytearray()
        while address:
            c=bytes(self.mu.mem_read(address,1));address+=1
            if c==b'\0':break
            b+=c
        return b.decode()
    def obj(self,value):
        if value is None:return 0
        n=self.next;self.next+=16;self.objects[n]=value;return n
    def get(self,reg):return self.objects.get(self.mu.reg_read(reg))
    def on_code(self,uc,address,size,_):
        if address==self.stop:uc.emu_stop();return
        if address not in self.names:return
        name=self.names[address];result=0
        if name=='_objc_autoreleasePoolPush':result=self.obj('pool')
        elif name=='_objc_autoreleasePoolPop':pass
        elif name=='_objc_getClass':result=self.obj(('class',self.text(uc.reg_read(UC_ARM64_REG_X0))))
        elif name=='_NSSelectorFromString':
            result=self.next;self.next+=256;self.load(result,self.get(UC_ARM64_REG_X0).encode()+b'\0')
        elif name=='_objc_msgSend':
            receiver=self.get(UC_ARM64_REG_X0);selector=self.text(uc.reg_read(UC_ARM64_REG_X1))
            a2=self.get(UC_ARM64_REG_X2);a3=self.get(UC_ARM64_REG_X3)
            if receiver is None:result=0
            elif selector=='stringWithUTF8String:':result=self.obj(self.text(uc.reg_read(UC_ARM64_REG_X2)))
            elif selector=='standardUserDefaults':result=self.obj(('defaults',))
            elif selector=='dictionary':result=self.obj({})
            elif selector=='mainBundle':result=self.obj(('bundle',))
            elif selector=='executablePath':result=self.obj(self.path)
            elif selector=='defaultManager':result=self.obj(('manager',))
            elif selector=='attributesOfItemAtPath:error:':
                assert a2==self.path;result=self.obj(self.attrs)
            elif selector=='objectForKey:':result=self.obj((self.prefs if receiver==('defaults',) else receiver).get(a2))
            elif selector=='setObject:forKey:':
                if receiver==('defaults',):
                    assert a3==boot.MARKER
                    if self.persist:self.prefs[a3]=copy.deepcopy(a2)
                else:receiver[a3]=a2
            elif selector=='isEqual:':result=int(receiver==a2)
            elif selector=='sharedURLCache':result=self.obj(('cache',)) if self.cache_available else 0
            elif selector=='removeAllCachedResponses':assert receiver==('cache',);self.clears+=1
            elif selector=='synchronize':result=int(self.persist)
            else:raise AssertionError((receiver,selector,a2,a3))
        else:raise AssertionError(name)
        uc.reg_write(UC_ARM64_REG_X0,result);uc.reg_write(UC_ARM64_REG_PC,uc.reg_read(UC_ARM64_REG_LR))
    def run(self):
        saved={r:0xa000+i for i,r in enumerate((UC_ARM64_REG_X19,UC_ARM64_REG_X20,UC_ARM64_REG_X21,UC_ARM64_REG_X22,UC_ARM64_REG_X23,UC_ARM64_REG_X24,UC_ARM64_REG_X25,UC_ARM64_REG_X26,UC_ARM64_REG_X27,UC_ARM64_REG_X28,UC_ARM64_REG_X29))}
        for reg,v in saved.items():self.mu.reg_write(reg,v)
        self.mu.reg_write(UC_ARM64_REG_SP,self.stack);self.mu.reg_write(UC_ARM64_REG_LR,self.stop)
        self.mu.emu_start(self.report['address'],self.stop,count=10000)
        assert self.mu.reg_read(UC_ARM64_REG_PC)==self.stop
        assert self.mu.reg_read(UC_ARM64_REG_SP)==self.stack
        assert all(self.mu.reg_read(r)==v for r,v in saved.items())

class NativeBootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report=json.loads((WORK/'output/build-report.json').read_text());cls.report=report['boot']
        cls.native=(WORK/'baseline-native').read_bytes();candidate=(WORK/'output/worldflipper').read_bytes()
        off=boot.link.file_offset(candidate,cls.report['address'],cls.report['payload_size'])
        cls.payload=candidate[off:off+cls.report['payload_size']];assert sha(cls.payload)==cls.report['sha256']
    def model(self):return Model(self.native,self.report,self.payload)
    def test_first_install_then_normal_restart(self):
        m=self.model();m.prefs['unrelated.account']='keep';m.run();self.assertEqual(m.clears,1)
        m.run();self.assertEqual(m.clears,1);self.assertEqual(m.prefs['unrelated.account'],'keep')
    def test_same_payload_replaced_inode(self):
        m=self.model();m.run();m.attrs['NSFileSystemFileNumber']=202;m.run();self.assertEqual(m.clears,2)
    def test_same_path_changed_modification(self):
        m=self.model();m.run();m.attrs['NSFileModificationDate']='modified-2';m.run();self.assertEqual(m.clears,2)
    def test_changed_bundle_path(self):
        m=self.model();m.run();m.path=m.path.replace('/TEST/','/NEXT/');m.run();self.assertEqual(m.clears,2)
    def test_changed_build_marker(self):
        m=self.model();m.run();m.prefs[boot.MARKER]['build']='older';m.run();self.assertEqual(m.clears,2)
    def test_missing_attributes_does_not_mark_or_clear(self):
        m=self.model();m.attrs.pop('NSFileCreationDate');m.run();self.assertEqual(m.clears,0);self.assertNotIn(boot.MARKER,m.prefs)
    def test_unavailable_cache_retries(self):
        m=self.model();m.cache_available=False;m.run();self.assertNotIn(boot.MARKER,m.prefs)
        m.cache_available=True;m.run();self.assertEqual(m.clears,1)
    def test_failed_marker_write_retries(self):
        m=self.model();m.persist=False;m.run();self.assertNotIn(boot.MARKER,m.prefs)
        m.persist=True;m.run();self.assertEqual(m.clears,2);self.assertIn(boot.MARKER,m.prefs)

class WrapperAbiTests(unittest.TestCase):
    def check_wrapper(self,name):
        report=json.loads((WORK/'output/build-report.json').read_text());w=report[name]
        native=(WORK/'baseline-native').read_bytes();candidate=(WORK/'output/worldflipper').read_bytes()
        old=w['original'];off=boot.link.file_offset(native,old,4);first=native[off:off+4]
        regs={i:getattr(arm64_const,f'UC_ARM64_REG_X{i}') for i in range(31)}
        live_writes=[]
        def execute(wrapped):
            mu=Uc(UC_ARCH_ARM64,UC_MODE_ARM);mapped=set()
            def load(at,data):
                for page in range(at&~4095,(at+len(data)+4095)&~4095,4096):
                    if page not in mapped:mu.mem_map(page,4096);mapped.add(page)
                mu.mem_write(at,data)
            stack=0x700010000;load(stack-0x10000,bytes(0x11000));load(old,first+b'\x1f\x20\x03\xd5')
            for i,r in regs.items():mu.reg_write(r,0xc000+i)
            mu.reg_write(UC_ARM64_REG_SP,stack)
            if not wrapped:
                def record_original_write(uc,access,address,size,value,_):
                    live_writes.append((address,size))
                mu.hook_add(UC_HOOK_MEM_WRITE,record_original_write)
            if wrapped:
                code=candidate[w['file_offset']:w['file_offset']+56];assert code==bytes.fromhex(w['bytes'])
                load(w['address'],code);load(w['extension'],b'\xc0\x03\x5f\xd6')
                def clobber(uc,pc,size,_):
                    if pc!=w['extension']:return
                    ret=uc.reg_read(UC_ARM64_REG_LR)
                    for i in list(range(19))+[29]:uc.reg_write(regs[i],0xbad000+i)
                    uc.reg_write(UC_ARM64_REG_PC,ret)
                mu.hook_add(UC_HOOK_CODE,clobber)
            mu.emu_start(w['address'] if wrapped else old,old+4,count=1000)
            assert mu.reg_read(UC_ARM64_REG_PC)==old+4
            sp=mu.reg_read(UC_ARM64_REG_SP)
            # The first STP reserves more stack than it initializes. Compare its
            # actual saved registers and incoming stack arguments, not undefined
            # bytes left in the unused part of the new local frame.
            saved=tuple((at,bytes(mu.mem_read(at,size))) for at,size in live_writes)
            incoming=bytes(mu.mem_read(stack,64))
            return {i:mu.reg_read(regs[i]) for i in list(range(8))+list(range(19,31))},sp,saved,incoming
        self.assertEqual(execute(False),execute(True))
    def test_main_arguments_and_prologue(self):self.check_wrapper('main_wrapper')
    def test_asset_handler_arguments_and_prologue(self):self.check_wrapper('asset_wrapper')

if __name__=='__main__':unittest.main(verbosity=2)
