"""Execute re-exported P-code branches with mocked UI/services (not a device test)."""
from prepare import ROOT,LEGACY
from import_methods import targets
import sys,re,json
sys.path.insert(0,str(LEGACY))
from transplant_abc_method_bodies import extract_method_pcode

def name(s):
    if s.startswith('Multiname('):return re.search(r'Multiname\("([^"\n]+)"',s)[1]
    return re.findall(r'"([^"\n]*)"',s)[-1]

def execute(text,root,param=None):
    lines=[l.strip() for l in text.splitlines()]
    lines=lines[lines.index('code')+1:lines.index('end ; code')]
    labels={s[:-1]:i for i,s in enumerate(lines) if s.endswith(':')}
    stack=[];loc={0:root,1:param};pc=0;steps=0
    while pc<len(lines):
        line=lines[pc];pc+=1;steps+=1
        assert steps<10000,'instruction bound'
        if not line or line.endswith(':'):continue
        op,_,arg=line.partition(' ')
        if op in ('debug','debugline','debugfile','coerce','coerce_a'):continue
        if op=='pushscope':stack.pop()
        elif op.startswith('getlocal'):stack.append(loc[int(arg or op[8:])])
        elif op.startswith('setlocal'):loc[int(arg or op[8:])]=stack.pop()
        elif op in ('pushbyte','pushint','pushshort'):stack.append(int(arg))
        elif op=='pushstring':stack.append(json.loads(arg))
        elif op in ('pushfalse','pushtrue','pushnull'):stack.append({'pushfalse':False,'pushtrue':True,'pushnull':None}[op])
        elif op in ('findproperty','findpropstrict'):stack.append(root)
        elif op=='getlex':stack.append(root[name(arg)])
        elif op=='getproperty':
            key=stack.pop() if arg.startswith('MultinameL(') else name(arg)
            stack.append(stack.pop()[key])
        elif op in ('initproperty','setproperty'):
            value=stack.pop();stack.pop()[name(arg)]=value
        elif op=='newobject':
            n=int(arg);v={}
            for _ in range(n):value=stack.pop();key=stack.pop();v[key]=value
            stack.append(v)
        elif op in ('callproperty','callpropvoid','constructprop'):
            n=int(arg.rsplit(',',1)[1]);args=stack[-n:] if n else []
            if n:del stack[-n:]
            ob=stack.pop();value=ob[name(arg)](*args)
            if op!='callpropvoid':stack.append(value)
        elif op in ('convert_i','convert_d','convert_b'):stack.append({'convert_i':int,'convert_d':float,'convert_b':bool}[op](stack.pop()))
        elif op=='astypelate':stack.pop()
        elif op=='dup':stack.append(stack[-1])
        elif op=='pop':stack.pop()
        elif op in ('equals','lessthan','bitand','in'):
            b=stack.pop();a=stack.pop()
            stack.append(a==b if op=='equals' else a<b if op=='lessthan' else a&b if op=='bitand' else a in b)
        elif op=='lookupswitch':
            ls=re.findall(r'ofs[0-9a-f]+',arg);key=int(stack.pop())
            pc=labels[ls[key+1] if 0<=key<len(ls)-1 else ls[0]]
        elif op=='jump':pc=labels[arg]
        elif op in ('iftrue','iffalse'):
            v=bool(stack.pop())
            if v==(op=='iftrue'):pc=labels[arg]
        elif op in ('ifeq','ifne','ifngt'):
            b=stack.pop();a=stack.pop()
            if a==b if op=='ifeq' else a!=b if op=='ifne' else not a>b:pc=labels[arg]
        elif op=='returnvoid':return
        else:raise AssertionError(f'unsupported instruction: {line}')
    raise AssertionError('no return')

class Container(dict):
    def __init__(self):
        super().__init__();self.children={}
        self.update(getContainer=self.child,getText=self.child,goto=lambda frame:self.update(frame=frame),set_text=lambda value:self.update(text=value))
    def child(self,key,*_):
        if key not in self.children:self.children[key]=Container()
        return self.children[key]

def main():
    blocks={method:extract_method_pcode(ROOT/'final-pcode/scripts'/(cls.replace('.','/')+'.pcode'),cls,method) for cls,method,_,_ in targets}
    results=[]
    for state in range(4):
        ui=Container()
        root=dict(mainLayer=ui,peek=dict(profileKind=dict(index=1),getProfile=lambda:dict(getFollowState=lambda:state,isFollower=lambda:state in [1,3])),view=dict(asset=dict(getUiString=lambda k:k)))
        execute(blocks['refreshFollowRelationButtons'],root)
        follow=ui.child('top_right_button_layer').child('follow_button')['visible']
        remove=ui.child('top_right_button_layer').child('remove_button')['visible']
        assert follow==(state in [0,3]) and remove==(state in [1,2])
        for button in ([0x20,0x30] if state in [0,3] else [0x30]):
            actions=[];data=dict(viewer_id=703758818,follow_state=state)
            root=dict(response=dict(target_user_info=data),followStateUpdateFunction=lambda *_:None,startFollowDelete=lambda:actions.append('delete'),gear=dict(addChild=lambda flow,*_:actions.append(flow)),FollowFollowerAddProcessingFlow=lambda *args:'add')
            execute(blocks['applyButton'],root,button)
            assert actions==(['add'] if state in [0,3] else ['delete']),actions
            results.append(dict(state=state,follow_visible=follow,remove_visible=remove,button=hex(button),action=actions[0]))
    for viewer,row,expected in [(777646232,777646232,'my'),('777646232',777646232,'my'),(777646232,703758818,'other'),(777646232,0,None)]:
        routes=[]
        root=dict(PartyGroupSource=None,mode=dict(index=0,params=[-1]),globalLogic=dict(getPlayer=lambda:dict(get_viewerId=lambda:viewer)),LoadingTaskKind=dict(ProfileGetMyProfile=('my',None),ProfileGetProfile=lambda uid:('other',uid)),ChangeSceneBackKind=dict(AddCurrent='add-current'),changeSceneWithLoading=lambda task,back:routes.append((task,back)))
        execute(blocks['copyPlayedParty'],root,dict(id=row))
        assert routes==[] if expected is None else routes==[((expected,None if expected=='my' else float(row)),'add-current')],routes
        results.append(dict(viewer=viewer,row=row,route=expected))
    report=dict(status='passed',kind='mocked execution of P-code re-exported from actual iOS compiler input; not device execution',cases=results)
    (ROOT/'output/branch-checks.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
    print(f'passed {len(results)} scenarios')

if __name__=='__main__':main()
