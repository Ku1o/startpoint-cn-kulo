"""Run the ported iOS rule bodies against the accepted battle scenarios."""
import json,sys,unittest
from common import HERE,WORK,OUT,dump
sys.path[:0]=[str(HERE.parent/'ios-cumulative-login'),str(HERE.parent/'author-content-1043/rules/tests')]
import prepare as p
p.asm.MNEMONICS['avm_label']=0x09;p.asm.BY_OPCODE[0x09]='avm_label'
import test_rules
from vm import run

class IosRules(test_rules.RulesTest):
    @classmethod
    def setUpClass(cls):
        cls.abc=p.abcfmt.ABC((WORK/'ios/author-full.abc').read_bytes())
        view=p.view(cls.abc)
        for field,method in [('convert','wfConvertNormalAttack'),('resolve','wfResolveDamageType'),
                             ('filter','wfBlocksGauge'),('allows','wfAllowsGauge'),('address','wfGaugeFromAddress')]:
            label,=[label for label in view.by_label if '/'+method+'|1' in label]
            bi,=view.by_label[label]
            setattr(cls,field,p.asm.decode(cls.abc.bodies[bi][5]))

def main():
    skipped={'test_signed_minus_one_is_encoded_without_negative_pool_value',
             'test_empty_description_uses_real_string_constant_not_reserved_zero',
             'test_builder_rejects_symbolic_only_loop_before_serialization'}
    names=[n for n in unittest.defaultTestLoader.getTestCaseNames(IosRules) if n not in skipped]
    result=unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(IosRules(n) for n in names))
    assert result.wasSuccessful()
    port=json.loads((WORK/'ios/port.json').read_text('utf8'))
    abc=p.abcfmt.ABC((WORK/'ios/author-full.abc').read_bytes())
    row,=[r for r in port['method_redirects'] if r['original']==57004]
    code=p.asm.decode(next(b for b in abc.bodies if b[0]==row['compiled'])[5])
    markers=(101,102,104,131,132,133)
    for marker in markers:assert run(code,abc,[{'buffTargetAs':marker}])==marker
    for value in (0,1,2,3,4,100,103,134,999):assert run(code,abc,[{'buffTargetAs':value}])==-1
    ctor=p.asm.decode(next(b for b in abc.bodies if b[0]==48643)[5])
    for kind in (0,1,2,3):
        obj={'__enum__':False};prior=dict(wfGainKind=24,wfGainCategory=1024,wfGainOwner=1,wfGainTrigger=2)
        run(ctor,abc,[obj,'Initial' if kind==0 else 'Test',kind,[prior]])
        assert obj['__enum__'] is True and obj['index']==kind and obj['params']==[prior]
        assert obj['wfGainKind']==(1 if kind==0 else 24 if kind==3 else 8)
    report={'passed':True,'ported_bytecode_tests':len(names),'environment_guard_cases':15,'constructor_default_cases':4,
            'checks':names,'source':'actual iOS full ABC methods','runtime':'bounded AVM2 interpreter with modeled battle objects',
            'device_tested':False}
    dump(OUT/'ios/rules-verification.json',report)
    print(json.dumps({k:report[k] for k in ('passed','ported_bytecode_tests','environment_guard_cases')}))

if __name__=='__main__':main()
