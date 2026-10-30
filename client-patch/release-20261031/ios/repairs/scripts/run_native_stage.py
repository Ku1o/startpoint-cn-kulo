"""Bounded native stages for the actual prepared repair delta. Not a full rebuild."""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
from pathlib import Path
import argparse,ast,inspect,json,os,sys
from types import FunctionType,SimpleNamespace
from unittest.mock import patch
import repair_common as c

def owned(path):
    path=Path(path).resolve();c.require(path.is_relative_to(c.TASK.resolve()),'Artifact outside new repair task')
    return path

def grouped_link(link_stage,options):
    """Sort only new functions by compiler unwind, never alter old boundaries."""
    import verify_stages as independent
    compiled=c.read(options.compiled)
    hashes={str((Path(compiled['directory'])/r['name']).resolve()):r['sha256'] for r in compiled['objects']}
    allocation=[];prefix_proof={}
    def preserve_prefix(native,patched,allowed,end):
        chunks=0
        for at in range(0,end,1024*1024):
            stop=min(end,at+1024*1024);before=memoryview(native)[at:stop]
            actual=bytearray(memoryview(patched)[at:stop])
            for begin,finish in allowed:
                c.require(0<=begin<=finish,'Allowed prefix range is reversed')
                left,right=max(at,begin),min(stop,finish,end)
                if left<right:actual[left-at:right-at]=before[left-at:right-at]
            c.require(actual==before,f'Unexpected preexisting native change in full-prefix chunk {at:x}')
            chunks+=1
        prefix_proof.update(bytes_compared=end,chunk_bytes=1024*1024,chunks=chunks,
            semantics='unchanged allowed ranges; exact original masked full-prefix byte equality')
        return prefix_proof
    def order(item):
        mid,value=item;record,path,*_=value
        key=str(Path(path).resolve());c.require(key in hashes,'Allocation object not in frozen compile report')
        obj=independent.Object(Path(key),hashes[key]);fn=obj.function(record.symbol)
        row=dict(method=mid,symbol=record.symbol,object=key,object_sha256=hashes[key],
                 compiler_encoding=fn['encoding'],inline_table=fn['code_size']<len(fn['data']),size=record.size)
        allocation.append(row)
        return row['inline_table'],row['compiler_encoding'],mid
    tree=ast.parse(inspect.getsource(link_stage.original.run));changed=0;prefix_changed=0
    for node in ast.walk(tree):
        if isinstance(node,ast.For) and ast.unparse(node.target)=='(mid, (record, *_))':
            c.require(ast.unparse(node.iter)=='sorted(funcs.items())','Link allocation source shape changed')
            node.iter.keywords.append(ast.keyword(arg='key',value=ast.Name(id='_acceptance_new_function_order',ctx=ast.Load())))
            changed+=1
    c.require(changed==1,'Expected exactly one new-function allocation loop')
    fn=tree.body[0]
    for i,node in list(enumerate(fn.body)):
        if not (isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='prefix' for t in node.targets)):continue
        c.require(ast.unparse(node.value)=='bytearray(patched[:old_prefix_end])','Linker prefix allocation shape changed')
        block=fn.body[i:i+3]
        c.require(isinstance(block[1],ast.For) and isinstance(block[2],ast.If) and
                  'unexpected preexisting native change' in ast.unparse(block[2]),'Linker prefix predicate shape changed')
        fn.body[i:i+3]=ast.parse('_acceptance_check_prefix(native,patched,allowed,old_prefix_end)').body
        prefix_changed+=1;break
    c.require(prefix_changed==1,'Expected one bounded prefix allocation adapter')
    namespace=link_stage.original.__dict__.copy();namespace['_acceptance_new_function_order']=order
    namespace['_acceptance_check_prefix']=preserve_prefix
    exec(compile(ast.fix_missing_locations(tree),str(Path(link_stage.original.__file__)),'exec'),namespace)
    link_stage.original.__dict__['_acceptance_new_function_order']=order
    link_stage.original.__dict__['_acceptance_check_prefix']=preserve_prefix
    adapted=FunctionType(namespace['run'].__code__,link_stage.original.__dict__)
    from signing_models import verify_signing_models
    with (patch.object(link_stage.original,'run',adapted),
          patch.object(link_stage.original,'verify_signing_models',verify_signing_models),
          patch.object(link_stage.support,'verify_signing_models',verify_signing_models)):
        report=link_stage.run_link(options)
    positions={int(r['method']):r['address'] for r in report['functions']}
    for row in allocation:row['linked_address']=positions[row['method']]
    allocation.sort(key=lambda row:row['linked_address'])
    proof=dict(strategy='new-only allocation grouped by unchanged compiler unwind',allocation_loop_ast_changes=1,
               prefix_allocation_ast_changes=1,prefix_comparison=prefix_proof,
               source_linker=str(Path(link_stage.original.__file__)),
               source_linker_sha256=c.sha(Path(link_stage.original.__file__).read_bytes()),
               adapter_sha256=c.sha(Path(__file__).read_bytes()),functions=allocation,
               old_functions_relocated=False,old_unwind_boundaries_deleted=False)
    c.dump(options.output/'allocation-contract.json',proof)
    report.update(allocation_contract=str(options.output/'allocation-contract.json'),
                  allocation_contract_sha256=c.sha((options.output/'allocation-contract.json').read_bytes()))
    link_stage.save(options.output/'link-report.json',report)
    return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['compile','link','finalize','package'])
    ap.add_argument('--prepared',type=Path);ap.add_argument('--compiled',type=Path)
    ap.add_argument('--linked',type=Path);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--compiler-timeout',type=int,default=165);args=ap.parse_args()
    c.bounded_job();c.require(0<args.compiler_timeout<=165,'Inner compiler timeout must be <=165 seconds')
    output=owned(args.output)
    # Process-local only. compile_port's background Python lacks -B, so inherit
    # this variable through every child; never modify persistent/global config.
    previous_env=os.environ.get('PYTHONDONTWRITEBYTECODE');os.environ['PYTHONDONTWRITEBYTECODE']='1'
    try:
        c.framework()
        import compile_port,link_stage
        if args.stage in ('compile','link'):
            c.require(args.prepared is not None,'Prepared port required');prepared=owned(args.prepared);port=c.read(prepared)
            c.require(port['base_full_abc_sha256']==c.ABC_SHA and port['old_methods']==101833,'Wrong cumulative base')
            c.require(not ({r['method_id'] for r in port['methods']} & {18392,66181}),
                      'Repair target intersects protected native wrapper; dedicated plan required')
            c.fresh(output)
        if args.stage=='compile':
            report=compile_port.run(prepared,output,sdk=c.SDK,dependencies=c.DEPENDENCIES,
                                    background=c.BACKGROUND,timeout=args.compiler_timeout)
        elif args.stage=='link':
            c.require(args.compiled is not None,'Compile report required')
            options=SimpleNamespace(prepared=prepared,compiled=owned(args.compiled),output=output,
                previous_link=c.PREVIOUS_LINK,
                previous_package=c.PREVIOUS_PACKAGE,
                runtime_stubs=c.STUBS,dependencies=c.DEPENDENCIES)
            report=grouped_link(link_stage,options)
        elif args.stage=='finalize':
            c.require(output.is_dir(),'Existing new linked directory required')
            current=c.read(output/'link-report.json')
            c.require(current['status']=='linked_pending_unwind_finalization','No pending native finalization')
            sys.path.insert(0,cfg.local('settings/recipe'))
            finalizer=c.module('acceptance_strict_finalizer',Path(cfg.local('settings/recipe/finalize_final.py')))
            from signing_models import verify_signing_models
            with (patch.object(finalizer.finalize_delta,'verify_switch_tables',finalizer.strict_switch),
                  patch.object(link_stage.support,'verify_signing_models',verify_signing_models)):
                report=link_stage.finalize(SimpleNamespace(output=output))
        else:
            c.require(args.linked is not None,'Finalized link report required');linked=owned(args.linked)
            c.fresh(output);c.fresh(output.with_suffix('.json'))
            package=c.module('acceptance_existing_packager',c.SOURCE/'ios-r11-port/package_stage.py')
            with patch.object(sys,'argv',[str(Path(package.__file__)),'--linked',str(linked),'--output',str(output)]):
                package.main()
            report=c.read(output.with_suffix('.json'),128*1024)
        print(json.dumps(dict(stage=args.stage,status=report['status'],native_sha256=report.get('native_sha256'),
                              ipa_sha256=report.get('ipa_sha256'))))
    finally:
        if previous_env is None:os.environ.pop('PYTHONDONTWRITEBYTECODE',None)
        else:os.environ['PYTHONDONTWRITEBYTECODE']=previous_env

if __name__=='__main__':main()
