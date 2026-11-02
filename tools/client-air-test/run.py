"""One local AIR acceptance entry. All build/ADL children use client-background."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,shutil,subprocess,sys,time,traceback
sys.dont_write_bytecode=True
TOOL=Path(__file__).resolve().parent
sys.path[:0]=[str(TOOL/'lib'),str(TOOL/'suites')]
from run_contract import read,write,sha,validate_fixtures,expectations,validate_result,validate_binding,validate_application,require_battle_fixtures,require_purchases_fixtures,validate_purchase_source
SUITES=['queue','common','flows','ex','gacha-entry','crazy-flow','mail-ex','mvp']
GROUPS=['tutorial','mail','equipment','crazy','ex','mvp','battle','purchases']
ALL_GROUPS=['tutorial','mail','equipment','crazy','ex']

def parse():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--swf',type=Path,required=True)
    p.add_argument('--swf-sha256',help='Optional prior expected identity; a mismatch is fatal')
    p.add_argument('--suite',required=True,help='Comma-separated '+','.join(SUITES)+'; all is explicit')
    p.add_argument('--groups',help='Comma-separated tutorial,mail,equipment,crazy,ex; mvp, battle or purchases separately; all is explicit')
    p.add_argument('--out',type=Path,required=True,help='A new run directory outside the business repository')
    p.add_argument('--fixtures',type=Path,help='Explicit schema2 response replay; does not validate current server code')
    p.add_argument('--config',type=Path,default=TOOL/'config.local.json')
    p.add_argument('--timeout',type=int,default=600)
    p.add_argument('--_run',action='store_true',help=argparse.SUPPRESS)
    a=p.parse_args();a.repo=a.repo.resolve();a.swf=a.swf.resolve();a.out=a.out.resolve()
    a.suites=[s for s in SUITES if s!='mvp'] if a.suite=='all' else a.suite.split(',')
    if not a.suites or len(set(a.suites))!=len(a.suites) or set(a.suites)-set(SUITES):p.error('Choose explicit supported suites without duplicates')
    a.group_list=list(ALL_GROUPS) if a.groups=='all' else (a.groups.split(',') if a.groups else [])
    if set(a.group_list)-set(GROUPS):p.error('Unsupported group')
    if 'battle' in a.group_list and (a.group_list!=['battle'] or a.suites!=['common']):p.error('Battle runs separately with --suite common --groups battle')
    if 'purchases' in a.group_list:
        if a.group_list!=['purchases'] or a.suites!=['common']:p.error('Purchases runs separately with --suite common --groups purchases')
        if a.fixtures:p.error('Purchases requires current-source generation; explicit fixture replay is not supported')
    if 'mvp' in a.suites:
        if a.suites!=['mvp']:p.error('MVP runs separately because client payload generation precedes its source finish fixtures')
        if not a.group_list:a.group_list=['mvp']
        if a.group_list!=['mvp']:p.error('MVP requires only --groups mvp')
    needs_server=bool(set(a.suites)&{'common','flows','ex','crazy-flow','mail-ex','mvp'})
    if needs_server and not a.fixtures and not a.group_list:
        if a.suites==['ex']:a.group_list=['ex']
        else:p.error('Choose --groups explicitly; routine work does not run all business cases')
    if a.out.exists():p.error('Output already exists; choose a new directory, never reuse an old result')
    if a.out.is_relative_to(a.repo) or a.out.is_relative_to(TOOL):p.error('Run output must be outside the business repository and tool directory')
    if not (a.repo/'package.json').is_file() or not a.swf.is_file():p.error('Explicit repo/SWF input is missing')
    if a.fixtures and not a.fixtures.is_file():p.error('Explicit fixture input is missing')
    if a.fixtures and a.group_list==['battle']:
        try:
            replay=read(a.fixtures);validate_fixtures(replay)
            require_battle_fixtures({**replay,'cases':[c for c in replay['cases'] if c.get('group')=='battle']})
        except (ValueError,KeyError,TypeError) as error:p.error(str(error))
    a.config_data=read(a.config)
    for label,path in [('SDK ADL',Path(a.config_data['sdk'])/'bin/adl.exe'),('SDK compiler',Path(a.config_data['sdk'])/'lib/mxmlc-cli.jar'),('Java',Path(a.config_data['java'])),('background entry',Path(a.config_data['background']))]:
        if not path.is_file():p.error(label+' missing: '+str(path))
    if a.swf_sha256 and sha(a.swf)!=a.swf_sha256.lower():p.error('Selected SWF does not match the supplied identity')
    return a

def load_suite(name):
    spec=importlib.util.spec_from_file_location('air_suite_'+name.replace('-','_'),TOOL/'suites'/(name.replace('-','_')+'.py'))
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module);return module

def run_stage(command,cwd,log,timeout):
    started=time.perf_counter();p=subprocess.run([str(x) for x in command],cwd=cwd,capture_output=True,timeout=timeout)
    Path(log).write_bytes(p.stdout+p.stderr)
    return {'command':[str(x) for x in command],'exit_code':p.returncode,'elapsed_ms':round((time.perf_counter()-started)*1000,3)}

def worker(a):
    a.out.mkdir(parents=True,exist_ok=False)
    stage='inputs';summary={'status':'failed','run':str(a.out),'requested_suites':a.suites,'suites':[]}
    try:
        inputs=a.out/'inputs';inputs.mkdir();frozen=inputs/'client.swf';shutil.copyfile(a.swf,frozen)
        identity=sha(frozen)
        if sha(a.swf)!=identity:raise ValueError('Input SWF changed while freezing it')
        ctx={'repo':str(a.repo),'swf':str(frozen),'swf_sha256':identity,'sdk':str(Path(a.config_data['sdk']).resolve()),'java':str(Path(a.config_data['java']).resolve()),'tool_root':str(TOOL),'run_root':str(a.out)}
        head=subprocess.check_output(['git','-C',str(a.repo),'rev-parse','HEAD'],text=True).strip()
        status=subprocess.check_output(['git','-C',str(a.repo),'status','--porcelain','-uall'],text=True).splitlines()
        manifest={'input_swf':{'source':str(a.swf),'frozen':str(frozen),'sha256':identity},'repo':str(a.repo),'head':head,'dirty_paths':status,'config':a.config_data,'groups':a.group_list,'response_mode':'explicit-replay' if a.fixtures else 'generated-from-requested-source','tool_sources':{str(p.relative_to(TOOL)):sha(p) for p in TOOL.rglob('*') if p.is_file() and p.suffix in ('.py','.as','.json','.cjs')}}
        needs_server=bool(set(a.suites)&{'common','flows','ex','crazy-flow','mail-ex','mvp'})
        stage='fixtures'
        if a.fixtures:
            fixtures=read(a.fixtures);validate_fixtures(fixtures)
            if a.group_list:fixtures={**fixtures,'cases':[c for c in fixtures['cases'] if c['group'] in a.group_list]}
            fixture_path=inputs/'fixtures.json';write(fixture_path,fixtures)
            manifest['replay_source']={'path':str(a.fixtures.resolve()),'sha256':sha(a.fixtures),'current_server_executed':False}
        elif needs_server:
            if a.suites==['mvp']:
                import abc_tools
                abc_tools.configure(ctx)
                fixture_path=load_suite('mvp').generate(ctx,a.out/'server',a.config_data['node'])
            elif a.group_list==['battle']:
                import abc_tools
                abc_tools.configure(ctx)
                fixture_path=load_suite('common').generate_battle(ctx,a.out/'server',a.config_data['node'])
            elif a.group_list==['purchases']:
                command=[a.config_data['node'],TOOL/'fixtures/purchases.cjs','--repo',a.repo,'--out',a.out/'server']
                generation=run_stage(command,a.repo,a.out/'generator.log',240);write(a.out/'generator-execution.json',generation)
                if generation['exit_code']!=0:raise RuntimeError('Real purchase fixture generation failed; see generator.log')
                fixture_path=a.out/'server/fixtures.json'
            else:
                command=[a.config_data['node'],TOOL/'fixtures/generate.cjs','--repo',a.repo,'--out',a.out/'server','--groups',','.join(a.group_list)]
                generation=run_stage(command,a.repo,a.out/'generator.log',240);write(a.out/'generator-execution.json',generation)
                if generation['exit_code']!=0:raise RuntimeError('Real server fixture generation failed; see generator.log')
                fixture_path=a.out/'server/fixtures.json'
            fixtures=read(fixture_path)
            if fixtures.get('completed') is not True:raise ValueError('Generator did not complete all requested cases')
        else:
            fixtures={'schemaVersion':2,'cases':[]};fixture_path=inputs/'fixtures.json';write(fixture_path,fixtures)
        validate_fixtures(fixtures)
        if a.group_list==['battle']:require_battle_fixtures(fixtures)
        if a.group_list==['purchases']:
            require_purchases_fixtures(fixtures);validate_purchase_source(fixtures,a.repo)
            manifest['server_source']=fixtures['source']
        ctx['fixtures']=str(fixture_path)
        manifest['fixtures']={'path':str(fixture_path),'sha256':sha(fixture_path),'cases':[c['id'] for c in fixtures['cases']]}
        write(a.out/'manifest.json',manifest)
        import abc_tools
        abc_tools.configure(ctx)
        for name in a.suites:
            stage=name+'/build';print(json.dumps({'stage':stage}),flush=True)
            destination=a.out/'suites'/name;destination.mkdir(parents=True,exist_ok=False)
            module=load_suite(name);built=module.build(ctx,destination)
            for key in ('application','swf','proof'):
                built[key]=Path(built[key]).resolve()
                if not built[key].is_relative_to(destination.resolve()):raise ValueError('Suite artifact escaped its own run directory: '+key)
            binding={**validate_application(built),**validate_binding(built,ctx)};contract=expectations(name,fixtures,built)
            write(destination/'contract.json',contract)
            result_path=destination/'result.json'
            if result_path.exists():raise ValueError('A result existed before ADL execution; refusing stale evidence')
            stage=name+'/execute'
            command=[Path(ctx['sdk'])/'bin/adl.exe','-nodebug','-cmd',built['application'],'--',fixture_path,result_path]
            execution=run_stage(command,destination,destination/'adl.log',90)
            write(destination/'execution.json',execution)
            if not result_path.is_file():raise ValueError('ADL produced no fresh result.json')
            stage=name+'/verify';result=read(result_path)
            coverage=validate_result(result,contract,execution['exit_code'])
            if sha(fixture_path)!=manifest['fixtures']['sha256'] or sha(frozen)!=identity:raise ValueError('Frozen inputs changed during this run')
            if sha(built['swf'])!=binding['swf_sha256']:raise ValueError('Carrier changed during execution')
            if sha(built['application'])!=binding['application_sha256']:raise ValueError('AIR descriptor changed during execution')
            receipt={'suite':name,'status':'passed','input_swf_sha256':identity,'fixture_sha256':manifest['fixtures']['sha256'],**binding,**coverage,'execution':execution,'result_sha256':sha(result_path),'limits':result.get('limits',[])}
            write(destination/'receipt.json',receipt);summary['suites'].append(receipt)
        if subprocess.check_output(['git','-C',str(a.repo),'status','--porcelain','-uall'],text=True).splitlines()!=status:raise ValueError('Business worktree status changed during the run')
        if needs_server and not a.fixtures:
            for source in fixtures['source']['relatedFiles']:
                if sha(a.repo/source['path'])!=source['sha256']:raise ValueError('Relevant server source changed after fixture generation: '+source['path'])
        deferred={step for suite in summary['suites'] for step in suite['deferred_to_other_suite']}
        covered={step for suite in summary['suites'] for step in suite['executed_load_steps']}
        summary['coverage_scope']='Only requested suites and explicitly reported cases; see per-suite limits'
        summary['uncovered_load_steps']=sorted(deferred-covered)
        summary.update(status='passed',manifest_sha256=sha(a.out/'manifest.json'),input_swf_sha256=identity,fixture_sha256=manifest['fixtures']['sha256'])
        write(a.out/'result.json',summary);print(json.dumps({'status':'passed','suites':a.suites,'result':str(a.out/'result.json')}),flush=True)
        return 0
    except BaseException as error:
        summary.update(failed_stage=stage,error=str(error));write(a.out/'result.json',summary)
        (a.out/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
        print(json.dumps({'status':'failed','stage':stage,'error':str(error),'result':str(a.out/'result.json')}),flush=True)
        return 1

def main():
    a=parse()
    if a._run:return worker(a)
    # The only AIR path is a complete worker invocation under the existing wrapper.
    command=[sys.executable,'-B',a.config_data['background'],'--timeout',str(a.timeout),'--cwd',str(TOOL),'--',sys.executable,'-B','-u',str(Path(__file__).resolve()),*sys.argv[1:],'--_run']
    return subprocess.run(command).returncode
if __name__=='__main__':raise SystemExit(main())
