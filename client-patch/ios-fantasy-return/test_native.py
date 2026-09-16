"""Execute actual ARM64 wrappers/helper. AIR objects and engine calls are models."""
from common import *
import unittest
sys.path.insert(0,'F:/codex/work/ios-cache-rounded-r2-20260912/test-libs')
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE
from unicorn import arm64_const as R

class Machine:
    def __init__(self,data,report,quest=300098001,history=(),cold=False):
        self.uc=Uc(UC_ARCH_ARM64,UC_MODE_ARM);self.mapped=set();self.callbacks={};self.objects={}
        self.next=0x300000000;self.next_callback=0x500000000;self.history=list(history)
        self.quest=quest;self.events=[];self.destination=None;self.fallback=False;self.finddefs=0
        h=report['helper'];self.load(h['address'],data[h['file_offset']:h['file_offset']+h['size']])
        for va,size in [(ROUTE,108),(0x103d518a0,144),(0x103d51d80,120),(0x103d51e00,120)]:
            self.load(va,data[offset(data,va):offset(data,va)+size])
        self.stop=0x600000000;self.load(self.stop,b'\xc0\x03\x5f\xd6')
        self.stack=0x700010000;self.load(self.stack-0x10000,bytes(0x11000))
        self.scene=self.alloc(0x500);sv=self.alloc();self.put(self.scene+0x10,sv)
        self.bind_virtual(sv,0x258,self.change_detail)
        self.env=self.alloc();mi=self.alloc();pool=self.alloc();self.core=self.alloc()
        self.put(self.env+0x10,mi);self.put(mi+0x30,pool);self.put(pool+8,self.core)
        self.put(self.core+0x60,0x12340000)
        scope=self.alloc();ae=self.alloc();self.findtable=self.alloc(0x30000)
        self.put(self.env+0x18,scope);self.put(scope+0x10,ae);self.put(ae+0x30,self.findtable)
        nextcls=self.class_object({0xb8:self.next_transition})
        backcls=self.class_object({0xb0:self.from_home})
        scenecls=self.class_object({0x428:self.rush_top})
        self.eventtop=self.object(('EventTop',));self.put(scenecls+0x90,self.eventtop)
        self.definitions={}
        for disp,cls in [(0x2c130,nextcls),(0x2c0d8,backcls),(0x8828,scenecls)]:
            definition=self.alloc();self.put(definition+0x20,cls)
            self.definitions[self.findtable+disp]=definition
            if not cold:self.put(self.findtable+disp,definition)
        self.put(self.scene+0x240,self.object(('QuestId',quest)))
        config=self.alloc();self.put(config+0x48,self.object(('QuestId',quest)));self.put(self.scene+0x350,config)
        for address,callback in {
            0x104b37c68:self.quest_id,0x104b319dc:self.quest_id,
            0x104babf58:self.quest_select,0x104bac08c:self.loading,0x104bb4750:self.blackout,
            ORIGINAL_TARGET:self.original_change_simply,0x10380a540:self.normal_back,
            0x104f73f7c:self.normal_result,0x104f6b804:self.normal_result,
            0x10050a8e8:self.finddef,0x100a2735c:self.newarray,0x100a2676c:self.npe,
        }.items():self.callback(callback,address)
        self.uc.hook_add(UC_HOOK_CODE,self.on_code)
    def load(self,address,data):
        for page in range(address&~4095,(address+len(data)+4095)&~4095,4096):
            if page not in self.mapped:self.uc.mem_map(page,4096);self.mapped.add(page)
        self.uc.mem_write(address,bytes(data))
    def alloc(self,size=0x800):
        at=self.next;self.next+=(size+0xfff)&~0xfff;self.load(at,bytes(size));return at
    def put(self,at,value):self.load(at,struct.pack('<Q',value))
    def get(self,at):return struct.unpack('<Q',self.uc.mem_read(at,8))[0]
    def x(self,i):return self.uc.reg_read(getattr(R,'UC_ARM64_REG_X'+str(i)))
    def object(self,value):
        p=self.alloc(16);self.objects[p]=value;return p
    def value(self,p):return self.objects[p]
    def callback(self,func,address=None):
        if address is None:address=self.next_callback;self.next_callback+=0x100
        self.load(address,b'\xc0\x03\x5f\xd6');self.callbacks[address]=func;return address
    def bind_virtual(self,vtable,slot,func):
        env=self.alloc();info=self.alloc();self.put(vtable+slot,env);self.put(env+0x10,info)
        self.put(info+0x50,self.callback(func))
    def class_object(self,methods):
        p=self.alloc();v=self.alloc();self.put(p+0x10,v)
        for slot,func in methods.items():self.bind_virtual(v,slot,func)
        return p
    def on_code(self,uc,address,size,_):
        if address==self.stop:uc.emu_stop();return
        callback=self.callbacks.get(address)
        if callback is None:return
        assert uc.reg_read(R.UC_ARM64_REG_SP)%16==0
        lr=uc.reg_read(R.UC_ARM64_REG_LR);value=callback()
        if self.fallback:uc.emu_stop();return
        # Callees may clobber all AAPCS64 volatile registers.
        for i in range(19):uc.reg_write(getattr(R,'UC_ARM64_REG_X'+str(i)),0xcc000000+i)
        uc.reg_write(R.UC_ARM64_REG_X0,0 if value is None else value)
        uc.reg_write(R.UC_ARM64_REG_PC,lr)
    def quest_id(self):return self.value(self.x(1))[1]
    def quest_select(self):return self.object(('RushSelect',self.x(1),self.x(2)))
    def loading(self):return self.object(('RushLoading',self.value(self.x(1))))
    def blackout(self):return self.object(('BlackOut',self.value(self.x(1))))
    def next_transition(self):return self.object(('Transition',self.value(self.x(1))))
    def rush_top(self):return self.object(('RushTop',self.x(1)))
    def from_home(self):return self.object(('FromHome',self.value(self.x(1))))
    def finddef(self):
        address=self.x(0);value=self.definitions[address];self.put(address,value);self.finddefs+=1;return value
    def newarray(self):
        assert self.x(0)==self.get(self.core+0x60)
        assert self.get(self.x(0)+8)==self.env
        return self.object([self.value(self.get(self.x(2)+8*i)&~7) for i in range(self.x(1))])
    def change_detail(self):
        assert self.x(0)==self.scene
        self.destination=self.value(self.x(1));kind,items=self.value(self.x(2));assert kind=='FromHome'
        self.history=[('Title',),('Home',)]+items;self.events.append('change_detail');return 4
    def original_change_simply(self):
        self.destination=('Transition',self.value(self.x(1)));self.events.append('legacy_not_change');return 4
    def normal_result(self):self.fallback=True;self.events.append('original_result')
    def normal_back(self):self.events.append('original_back');return 4
    def npe(self):raise AssertionError('Unexpected null reference in ARM64 helper')
    def run(self,entry):
        saved={i:0x190000+i for i in range(19,30)}
        for i,value in saved.items():self.uc.reg_write(getattr(R,'UC_ARM64_REG_X'+str(i)),value)
        self.uc.reg_write(R.UC_ARM64_REG_SP,self.stack);self.uc.reg_write(R.UC_ARM64_REG_LR,self.stop)
        self.uc.reg_write(R.UC_ARM64_REG_X0,self.scene);self.uc.reg_write(R.UC_ARM64_REG_X1,self.env)
        self.uc.emu_start(entry,self.stop,count=3000)
        assert self.uc.reg_read(R.UC_ARM64_REG_SP)==self.stack
        assert all(self.x(i)==value for i,value in saved.items())
        assert self.get(self.core+0x60)==0x12340000

class ReturnRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((OUT/'build-report.json').read_text());cls.old=native()
        with zipfile.ZipFile(cls.report['ipa']) as z:cls.new=z.read(cls.report['source_ipa']['native_member'])
    def assert_fixed(self,m):
        self.assertEqual(m.history,[('Title',),('Home',),('EventTop',),('RushTop',700098)])
        self.assertEqual(m.destination,('Transition',('BlackOut',('RushLoading',('RushSelect',700098,1)))))
        self.assertEqual(m.events,['change_detail'])
        self.assertEqual(m.history.pop(),('RushTop',700098))
        self.assertEqual(m.history.pop(),('EventTop',))
        self.assertEqual(m.history.pop(),('Home',))
    def test_fixed_finish_and_retry_three_bosses(self):
        for entry in (0x103d51d80,0x103d51e00):
            for quest in (300098001,300098002,300098003):
                for cold in (False,True):
                    with self.subTest(entry=hex(entry),quest=quest,cold=cold):
                        m=Machine(self.new,self.report,quest,cold=cold);m.run(entry);self.assert_fixed(m)
                        self.assertEqual(m.finddefs,3 if cold else 0)
    def test_previous_binary_preserves_empty_history(self):
        m=Machine(self.old,self.report);m.run(0x103d51e00)
        self.assertEqual(m.history,[]);self.assertEqual(m.events,['legacy_not_change'])
    def test_unrelated_quests_use_original_result(self):
        for entry in (0x103d51d80,0x103d51e00):
            for quest in (300098000,300098004,700098004,700099030):
                with self.subTest(entry=hex(entry),quest=quest):
                    m=Machine(self.new,self.report,quest,history=[('Sentinel',)]);m.run(entry)
                    self.assertEqual(m.events,['original_result']);self.assertEqual(m.history,[('Sentinel',)])
    def test_room_back_restores_history_without_stale_room(self):
        for quest in (300098001,300098002,300098003):
            m=Machine(self.new,self.report,quest,history=[('OldRoom',)]);m.run(0x103d518a0);self.assert_fixed(m)
    def test_other_room_keeps_original_back_handler(self):
        m=Machine(self.new,self.report,300098004,history=[('OldRoom',)]);m.run(0x103d518a0)
        self.assertEqual(m.events,['original_back']);self.assertEqual(m.history,[('OldRoom',)])

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ReturnRegression)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        dump(OUT/'native-tests.json',dict(status='passed',tests=result.testsRun,scenarios=25,
             executes_packaged_arm64=True,air_runtime_calls_mocked=True,device_tested=False,
             covers=['3 bosses: finish/retry, cold/warm definitions','old-binary negative control',
                     '8 unrelated quest controls','3 room exits','unrelated room fallback',
                     'AAPCS64 registers and stack','AIR MethodFrame restoration']))
    raise SystemExit(0 if result.wasSuccessful() else 1)
