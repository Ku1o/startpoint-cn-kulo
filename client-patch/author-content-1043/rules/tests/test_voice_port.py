"""Execute voice blocks read back from the serialized cumulative SWF."""
import copy, os, sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import build_swf as b
from vm import run

EXISTS='pinball.asset.logic:ILogicAssetContainer::existsVoiceFileReader'
ADD='pinball.asset.logic:IAssetPathCollectionBuilder::addSoundEffect'
G='unicorn_lancer_rose';T='super_robot_tailcoat';Z='samurai_robot_plum'
IDS={G:129992,T:139993,Z:159998}
def path(c,tail):return 'character/'+c+'/voice/battle/'+tail
def some(p):return {'index':0,'params':[p]}
def voices(c):
    return [path(c,'skill_ready')]+([path(c,'skill_ready_alt_'+str(i)) for i in range(1,6)] if c==G else
        [path(c,'matched_skill_ready')]+[path(c,'skill_ready_alt_'+str(i)) for i in range(2,3 if c==T else 4)])

class VoicePortTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=b.SwfAbc(Path(os.environ['STARPOINT_INTEGRATED_SWF'])).abc
        cls.code=[]
        for (name,_,at,_,_,count),ret in zip(b.VOICE_PLAN,(4,None,21)):
            ins=copy.deepcopy(b.asm.decode(cls.a.bodies[b.bodies.resolve(cls.a,name)][5])[at:at+count])
            for x in ins:
                if x.target is not None:x.target-=at
            ins+=b.asm.assemble([('returnvoid',)] if ret is None else [('getlocal',ret),('returnvalue',)])
            cls.code.append(ins)
    def hud(self,c,available=None):
        available=set(voices(c) if available is None else available)
        return {'character':{'mainCharacterStringId':c,'logic':{'logicAssets':{EXISTS:available.__contains__}}},'geraldReadyNext':0}
    def ready(self,h,old):
        return run(self.code[0],self.a,[h,None,None,None,old],lex={'haxe.ds::Option':{'Some':some}})
    def ui(self,c,available=None):
        available=set(voices(c) if available is None else available)
        args=[None]*22;args[2]={'characterId':IDS[c],'logicAssets':{EXISTS:available.__contains__}}
        args[21]=['original']
        return run(self.code[2],self.a,args)
    def preload(self,c,available=None):
        available=set(voices(c) if available is None else available);collected=[]
        args=[None]*6;args[1]={ADD:collected.append};args[5]={'characterId':IDS[c],'logicAssets':{EXISTS:available.__contains__}}
        run(self.code[1],self.a,args);return collected
    def test_gerald_six_ready_cycle(self):
        h=self.hud(G)
        self.assertEqual([some(p) for p in voices(G)]*2,[self.ready(h,some('native')) for _ in range(12)])
    def test_gerald_missing_alternates_fall_back_to_base(self):
        h=self.hud(G,[voices(G)[0]])
        self.assertEqual([some(voices(G)[0])]*7,[self.ready(h,some('native')) for _ in range(7)])
    def test_gerald_missing_base_preserves_native(self):
        h=self.hud(G,voices(G)[1:]);old=some('native')
        self.assertIs(old,self.ready(h,old));self.assertEqual(0,h['geraldReadyNext'])
    def test_tailcoat_every_third_ready_uses_extra(self):
        h=self.hud(T);old=some('native')
        self.assertEqual([old,old,some(voices(T)[2])]*2,[self.ready(h,old) for _ in range(6)])
    def test_zantetsu_four_slot_cycle_retains_native_first_two(self):
        h=self.hud(Z);old=some('native')
        self.assertEqual([old,old,some(voices(Z)[2]),some(voices(Z)[3])]*2,[self.ready(h,old) for _ in range(8)])
    def test_missing_extras_and_no_native_option_are_safe(self):
        for c in (T,Z):
            h=self.hud(c,[]);old=some('native')
            self.assertEqual([old]*8,[self.ready(h,old) for _ in range(8)])
            h=self.hud(c);none={'index':1,'params':[]}
            self.assertIs(none,self.ready(h,none));self.assertEqual(0,h['geraldReadyNext'])
    def test_unrelated_character_keeps_native_selection(self):
        h=self.hud(G);h['character']['mainCharacterStringId']='lion_swordman_reborn'
        old=some('native');self.assertIs(old,self.ready(h,old));self.assertEqual(0,h['geraldReadyNext'])
    def test_voice_page_lists_only_available_pool_members(self):
        for c in IDS:
            expected=voices(c);self.assertEqual(expected,self.ui(c))
            for missing in expected:
                remaining=[p for p in expected if p!=missing]
                self.assertEqual(remaining,self.ui(c,remaining))
            self.assertEqual([],self.ui(c,[]))
    def test_battle_preloads_every_added_ready_alternate(self):
        for c in IDS:
            expected=voices(c)[1 if c==G else 2:]
            self.assertEqual(expected,self.preload(c))
            for missing in expected:
                self.assertEqual([p for p in expected if p!=missing],self.preload(c,[p for p in voices(c) if p!=missing]))
            self.assertEqual([],self.preload(c,[]))

if __name__=='__main__':unittest.main()
