"""Exercise inline control flow without requiring an installed iOS client."""
import copy,unittest,types
from prepare import asm,rewrite_calls

def run(body,args,helper=None):
    code=asm.decode(body[5]);locals_=dict(enumerate(args));stack=[];pc=0;steps=0
    while pc<len(code):
        steps+=1
        if steps>500:raise AssertionError('loop did not terminate')
        i=code[pc];pc+=1;op=i.op
        if op in (0x30,0xef,0xf0,0xf1):
            if op==0x30:stack.pop()
        elif op==0x24:stack.append(i.args[0] if i.args[0]<128 else i.args[0]-256)
        elif op==0x21:stack.append(None)
        elif 0xd0<=op<=0xd3:stack.append(locals_.get(op-0xd0))
        elif 0xd4<=op<=0xd7:locals_[op-0xd4]=stack.pop()
        elif op==0x62:stack.append(locals_.get(i.args[0]))
        elif op==0x63:locals_[i.args[0]]=stack.pop()
        elif op==0xa0:b=stack.pop();stack[-1]+=b
        elif op==0xa2:b=stack.pop();stack[-1]*=b
        elif op==0x29:stack.pop()
        elif op==0x10:pc=i.target
        elif op in (0x15,0x16,0x17,0x18):
            b=stack.pop();a=stack.pop();take={0x15:a<b,0x16:a<=b,0x17:a>b,0x18:a>=b}[op]
            if take:pc=i.target
        elif op==0x46:
            count=i.args[1];call_args=stack[-count:] if count else [];del stack[len(stack)-count:]
            receiver=stack.pop();stack.append(run(helper,[receiver,*call_args]))
        elif op==0x48:return stack.pop()
        else:raise AssertionError(hex(op))
    raise AssertionError('missing return')

def body(source,locals_=3):
    return [1,20,locals_,1,2,asm.encode(asm.assemble(source))[0],[],[]]

class InlineTests(unittest.TestCase):
    def setUp(self):
        self.abc=types.SimpleNamespace(mn_name=lambda _: 'helper',multinames=[(0,),(7,0,0)])
        self.helper=body([('getlocal_0',),('pushscope',),('getlocal_1',),('pushbyte',0),('iflt','NEG'),
                          ('getlocal_1',),('pushbyte',2),('multiply',),('pushbyte',3),('add',),('returnvalue',),
                          ('label','NEG'),('pushbyte',0),('returnvalue',)])
    def test_result_and_surrounding_operand_stack(self):
        original=body([('pushbyte',10),('getlocal_0',),('getlocal_1',),('callproperty',1,1),('add',),('returnvalue',)])
        modified=copy.deepcopy(original);rewrite_calls(modified,{'helper':(self.helper,[0],0)},self.abc)
        for x in (-20,-1,0,1,200):
            self.assertEqual(run(modified,[{},x]),10+(0 if x<0 else 2*x+3))
            self.assertEqual(run(modified,[{},x]),run(original,[{},x],self.helper))
    def test_existing_branch_to_call_is_preserved(self):
        original=body([('getlocal_1',),('pushbyte',0),('iflt','ALT'),('getlocal_0',),('getlocal_1',),('jump','CALL'),
                       ('label','ALT'),('getlocal_0',),('pushbyte',8),('label','CALL'),('callproperty',1,1),('returnvalue',)])
        modified=copy.deepcopy(original);rewrite_calls(modified,{'helper':(self.helper,[0],0)},self.abc)
        for x in (-10,0,4):self.assertEqual(run(modified,[{},x]),run(original,[{},x],self.helper))
    def test_repeated_calls_keep_parameters_separate(self):
        original=body([('getlocal_0',),('getlocal_1',),('callproperty',1,1),('getlocal_0',),('pushbyte',9),('callproperty',1,1),('add',),('returnvalue',)])
        modified=copy.deepcopy(original);rewrite_calls(modified,{'helper':(self.helper,[0],0)},self.abc)
        self.assertEqual(run(modified,[{},6]),36)
    def test_lexical_scope_dependency_rejected(self):
        invalid=body([('getlocal_0',),('pushscope',),('getscopeobject',0),('returnvalue',)])
        caller=body([('getlocal_0',),('getlocal_1',),('callproperty',1,1),('returnvalue',)])
        with self.assertRaises(AssertionError):rewrite_calls(caller,{'helper':(invalid,[0],0)},self.abc)

if __name__=='__main__':unittest.main()
