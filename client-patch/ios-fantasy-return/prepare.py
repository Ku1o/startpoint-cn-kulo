"""Compile a private variant of changeSceneSimply; keep runtime ABC untouched."""
from common import *

def main():
    native()  # Historical reproduction always uses the pinned source artifact.
    assert not WORK.exists(), 'Use a new task directory.'
    reg=registry(); raw=(REPO/reg['full_abc']).read_bytes()
    assert sha(raw)==reg['full_abc_sha256']
    abc=model.abcfmt.ABC(raw); v=view(abc)
    bi,=v.by_label['pinball.context.scene::LogicScene/changeSceneSimply|1']
    assert abc.bodies[bi][0]==METHOD
    def q(name):
        ids=[i for i in range(1,len(abc.multinames)) if abc.mn_name(i)==name]
        assert len(ids)==1,(name,ids)
        return ids[0]
    code=model.asm.assemble([
        ('getlocal_0',), ('pushscope',), ('getlocal_0',),
        ('getlex',q('pinball.common.data.scene::ChangeSceneNextKind')), ('getlocal_1',),
        ('callproperty',q('Transition'),1),
        ('getlex',q('pinball.common.data.scene::ChangeSceneBackKind')),
        ('getlex',q('pinball.common.data.scene::SceneKind')), ('getproperty',q('EventTop')),
        ('getlex',q('pinball.common.data.scene::SceneKind')),
        ('pushshort',700), ('pushshort',1000), ('multiply_i',), ('pushbyte',98), ('add_i',),
        ('callproperty',q('RushEventTop'),1), ('newarray',2),
        ('callproperty',q('FromHome'),1), ('callpropvoid',q('changeSceneWithDetail'),2), ('returnvoid',),
    ])
    code=model.asm.encode(code)[0]
    old=abc.bodies[bi]
    abc.bodies[bi]=[METHOD,7,2,old[3],old[3]+1,code,[],[]]
    check=model.check_body(abc.bodies[bi],abc)
    # A stubbed script initializer hides instance methods from AIR's reachability
    # pass. Supply the lexical class definition for compilation only.
    ci,= [i for i,x in enumerate(abc.instances) if abc.mn_name(x[0])=='pinball.context.scene::LogicScene']
    si,=v.by_label['script:pinball.context.scene::LogicScene/<init>']
    init=abc.bodies[si];parent=abc.instances[ci][1]
    initcode=model.asm.encode(model.asm.assemble([
        ('getlocal_0',),('pushscope',),('getlocal_0',),('getlex',parent),('pushscope',),
        ('getlex',parent),('newclass',ci),('popscope',),('initproperty',abc.instances[ci][0]),('returnvoid',),
    ]))[0]
    abc.bodies[si]=[init[0],2,1,init[3],init[3]+2,initcode,[],[]]
    model.check_body(abc.bodies[si],abc)
    # No added pools, classes, methods, signatures or activation traits.
    fresh=abc.serialize(); original=model.abcfmt.ABC(raw)
    for field in ('methods','metadata','instances','classes','scripts','ints','uints','doubles','strings','namespaces','ns_sets','multinames'):
        assert model.freeze(getattr(abc,field))==model.freeze(getattr(original,field)),field
    WORK.mkdir(parents=True)
    (WORK/'navigation-compiler-input.abc').write_bytes(fresh)
    dump(WORK/'prepare.json',dict(input_ipa_sha256=INPUT_SHA, compiler_input_sha256=sha(fresh),
         donor_method=METHOD,body_index=bi,check=check,normalized=view(abc).normalized(bi),
         compiler_only_script_initializer=init[0],runtime_abc_unchanged=True,
         history=['Title','Home','EventTop','RushEventTop(700098)']))
    print('Prepared donor method',METHOD,'in',WORK)

if __name__=='__main__':main()
