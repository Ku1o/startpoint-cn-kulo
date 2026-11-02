"""Small explicit acceptance contract. Missing evidence is a failure, not a fallback."""
import hashlib,json
from pathlib import Path
import xml.etree.ElementTree as ET

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def validate_fixtures(data):
    if data.get('schemaVersion')!=2:raise ValueError('Only explicit fixture schemaVersion 2 is supported')
    if not isinstance(data.get('cases'),list):raise ValueError('Missing cases array')
    case_ids=[];step_ids=[]
    for case in data['cases']:
        case_ids.append(case['id'])
        if 'responses' in case:raise ValueError('Duplicate responses representation is not supported')
        for step in case['steps']:
            step_ids.append(step['id'])
            if not isinstance(step['response'],dict):raise ValueError('A complete response object is required')
    if len(case_ids)!=len(set(case_ids)) or len(step_ids)!=len(set(step_ids)):raise ValueError('Duplicate case/step IDs')

def require_battle_fixtures(data):
    validate_fixtures(data)
    required={'source-field-mana-boost','source-raid-frozen-exp','source-five-boss-pending-result'}
    rows=data['cases']
    if len(rows)!=3 or any(c.get('group')!='battle' for c in rows) or {c['id'] for c in rows}!=required:
        raise ValueError('Requested battle group requires all three complete battle business cases')
    expectations('common',data,{})

PURCHASE_CASES={
    'source-shop-buy':('shop.buy','/api/index.php/shop/buy'),
    'source-recover-stamina':('shop.recover_stamina','/api/index.php/shop/recover_stamina'),
    'source-inject-exp':('expod.inject_exp','/api/index.php/expod/inject_exp'),
    'source-box-exec':('boxGacha.exec','/api/index.php/box_gacha/exec'),
    'source-mana-learn':('mana.learn','/api/index.php/character/learn_mana_node'),
    'source-mana-awake':('mana.awake','/api/index.php/character/awake_mana_node'),
}

def require_purchases_fixtures(data):
    validate_fixtures(data)
    rows=data['cases']
    if len(rows)!=len(PURCHASE_CASES) or any(c.get('group')!='purchases' for c in rows) or {c['id'] for c in rows}!=set(PURCHASE_CASES):
        raise ValueError('Requested purchases group requires all six complete purchase cases')
    for case in rows:
        operation,route=PURCHASE_CASES[case['id']]
        if case.get('operation')!=operation:raise ValueError('Purchase operation does not match its case')
        if [s['id'] for s in case['steps']]!=[case['id']+'/success',case['id']+'/retry']:
            raise ValueError('Purchase fixture omits or reorders its success/retry branch')
        for state in [case.get('before'),case.get('expectedAfter')]+[s.get('expectedAfter') for s in case['steps']]:
            if not isinstance(state,dict) or not all(isinstance(state.get(k),dict) for k in ('userInfo','items','characters')):
                raise ValueError('Purchase fixture requires explicit wallet, inventory and character state')
            if not {'free_mana','paid_mana','free_vmoney','vmoney','pooled_exp','stamina'}<=set(state['userInfo']):
                raise ValueError('Purchase economic field expectations are incomplete')
        for step in case['steps']:
            if step.get('route')!=route or step.get('httpStatus')!=200:raise ValueError('Purchase route/status mismatch')
            if step['response'].get('data_headers',{}).get('result_code')!=1 or not isinstance(step['response'].get('data'),dict):
                raise ValueError('Purchase fixture must contain the complete successful native response')
            wire=step.get('wire',{})
            if not isinstance(wire.get('sha256'),str) or len(wire['sha256'])!=64 or not isinstance(wire.get('bytes'),int) or wire['bytes']<=0:
                raise ValueError('Purchase response must retain its real wire identity')
            if operation.startswith('mana.') and not step.get('expectedManaNodes'):
                raise ValueError('Mana fixture requires its separate native node expectation')

def validate_purchase_source(data,repo):
    source=data.get('source',{});root=Path(repo).resolve()
    if source.get('mode')!='src/ts-node/transpile-only' or source.get('outUsed') is not False or Path(source.get('root','')).resolve()!=root:
        raise ValueError('Purchases must be generated from the requested current source')
    files=source.get('relatedFiles')
    if not isinstance(files,list) or not files:raise ValueError('Purchase source identity is missing')
    paths=[]
    for row in files:
        target=(root/row['path']).resolve()
        if not target.is_relative_to(root) or not target.is_file() or sha(target)!=row.get('sha256'):
            raise ValueError('Purchase source identity differs: '+row['path'])
        paths.append(row['path'])
    if len(paths)!=len(set(paths)):raise ValueError('Duplicate purchase source identity')
    required={'src/routes/api/shop.ts','src/routes/api/expod.ts','src/routes/api/boxGacha.ts','src/routes/api/character/mana.ts','src/lib/cn-response-hook.ts'}
    if not required<=set(paths):raise ValueError('Purchase source identity omits required routes or codec')

def expectations(suite,data,built):
    cases=list(built.get('required_case_ids',[]));steps=list(built.get('required_step_ids',[]));deferred=[];excluded=[];loads=[];case_steps={};restore_states={};purchase_checks={};uncovered_fields={}
    if suite=='common':
        purchases=[case for case in data['cases'] if case.get('group')=='purchases']
        if purchases:
            require_purchases_fixtures({**data,'cases':purchases})
            required=['state/items','state/characters']+['state/userInfo/'+key for key in ('free_mana','paid_mana','free_vmoney','vmoney','pooled_exp','stamina')]
            purchase_checks={s['id']:required for c in purchases for s in c['steps']}
            uncovered_fields={c['id']:['user_character_mana_node_list'] for c in purchases if c['operation'].startswith('mana.')}
        battle=[case for case in data['cases'] if case.get('group')=='battle']
        if battle and {case['id'] for case in battle}!={'source-field-mana-boost','source-raid-frozen-exp','source-five-boss-pending-result'}:
            raise ValueError('Battle fixtures must contain mana/boost, Raid and pending-result cases')
        expected_battle_steps={
            'source-field-mana-boost':['single-0','single-0-retry','single-1','single-1-retry','multi-mana','multi-mana-retry'],
            'source-raid-frozen-exp':['raid-frozen-finish','raid-frozen-retry'],
            'source-five-boss-pending-result':['five-boss-old-finish','five-boss-old-retry'],
        }
        for case in battle:
            if [s['id'] for s in case['steps']]!=expected_battle_steps[case['id']]:raise ValueError('Battle fixture omits or reorders a mandatory branch')
            for step in case['steps']:
                if not isinstance(step.get('expectedCanBoost'),bool) or not isinstance(step.get('expectedCanBossBoost'),bool):raise ValueError('Battle boost availability must be explicit')
                if not {'free_mana','boost_point','boss_boost_point','pooled_exp'}<=set(step.get('expectedUserInfoSubset',{})):raise ValueError('Battle economic response assertions are incomplete')
        eligible=[case for case in data['cases'] if case['group']!='ex']
        if data['cases'] and not eligible:raise ValueError('No requested real cases belong to common; select ex for full load')
        cases += [case['id'] for case in eligible]
        steps += [step['id'] for case in eligible for step in case['steps'] if step.get('route')!='/api/index.php/load']
        case_steps={case['id']:[step['id'] for step in case['steps'] if step.get('route')!='/api/index.php/load'] for case in eligible}
        excluded=[step['id'] for case in eligible for step in case['steps'] if step.get('route')=='/api/index.php/load'];loads=list(excluded)
    elif suite=='flows':
        cases += [case['id'] for case in data['cases']]
        steps=[step['id'] for case in data['cases'] for step in case['steps']]
        deferred=[step['id'] for case in data['cases'] for step in case['steps'] if step['route']=='/api/index.php/load']
        case_steps={case['id']:[step['id'] for step in case['steps']] for case in data['cases']}
        loads=list(deferred)
    elif suite=='ex':
        loads=[step['id'] for case in data['cases'] if case['group']=='ex' for step in case['steps'] if step['route']=='/api/index.php/load']
        cases += loads
        restore_states={step['id']:step['expectedRestoreState'] for case in data['cases'] if case['group']=='ex' for step in case['steps'] if step['route']=='/api/index.php/load'}
        if not cases:raise ValueError('EX suite requires actual load responses')
    elif suite in ('crazy-flow','mail-ex'):
        eligible=[case for case in data['cases'] if case['group']=='crazy'] if suite=='crazy-flow' else [case for case in data['cases'] if case['group']=='mail' and case.get('clientScenario')=='mail-ex']
        if not eligible:raise ValueError(suite+' requires its own real response cases')
        cases += [case['id'] for case in eligible]
        steps += [step['id'] for case in eligible for step in case['steps']]
        case_steps={case['id']:[step['id'] for step in case['steps']] for case in eligible}
        loads=[step['id'] for case in eligible for step in case['steps'] if step['route']=='/api/index.php/load']
    elif suite=='mvp':
        eligible=[case for case in data['cases'] if case['group']=='mvp']
        if data['cases'] and (len(eligible)!=2 or {case['id'] for case in eligible}!={'source-mvp-healer-first','source-mvp-damage-first'}):raise ValueError('MVP source fixtures must contain both required settlement orders')
        for case in eligible:
            actors=['healer','damage'] if case['id'].endswith('healer-first') else ['damage','healer']
            required=[case['id']+'-'+actor for actor in actors]+[case['id']+'-'+actor+'-retry' for actor in actors]
            if [step['id'] for step in case['steps']]!=required:raise ValueError('MVP fixtures omit or reorder a member/settlement/retry branch')
        cases += [case['id'] for case in eligible]
        steps += [step['id'] for case in eligible for step in case['steps']]
        case_steps={case['id']:[step['id'] for step in case['steps']] for case in eligible}
    elif suite not in ('queue','gacha-entry'):raise ValueError('Unknown suite: '+suite)
    if not cases:raise ValueError('Suite declares no required cases')
    return {'case_ids':sorted(set(cases)),'step_ids':sorted(set(steps)),'case_step_ids':case_steps,'restore_states':restore_states,'deferred_step_ids':sorted(deferred),'excluded_step_ids':sorted(excluded),'load_step_ids':sorted(loads),'min_assertions':built.get('min_assertions',0),'required_step_checks':purchase_checks,'uncovered_fields':uncovered_fields}

def check_assertions(row):
    checks=row.get('checks',[])
    if not isinstance(checks,list) or any(not isinstance(check,dict) or check.get('pass') is not True for check in checks):
        raise ValueError('A case/step assertion is false or malformed: '+row['id'])

def validate_result(result,contract,exit_code):
    if exit_code!=0:raise ValueError('ADL exited unsuccessfully: '+str(exit_code))
    if result.get('status')!='passed' or result.get('failed')!=0:raise ValueError('Runtime did not report an explicit passed result')
    if result.get('fatal') is not None:raise ValueError('Runtime reports a fatal error')
    if result.get('stage_is_null',result.get('stageIsNull')) is not True:raise ValueError('This suite requires AIR cmd mode with no stage')
    rows=result.get('cases',[]);ids=[row['id'] for row in rows]
    if len(ids)!=len(set(ids)) or set(ids)!=set(contract['case_ids']):raise ValueError('Required cases are missing, duplicated or unexpected')
    excluded=[row['id'] for row in result.get('excludedSteps',[])]
    if len(excluded)!=len(set(excluded)) or set(excluded)!=set(contract.get('excluded_step_ids',[])):raise ValueError('Explicitly excluded load steps do not match the contract')
    step_ids=[];uncovered=list(excluded)
    for row in rows:
        if row.get('status')!='passed':raise ValueError('Case did not pass: '+row['id'])
        check_assertions(row)
        if row['id'] in contract.get('uncovered_fields',{}) and row.get('uncoveredFields')!=contract['uncovered_fields'][row['id']]:
            raise ValueError('Purchase result must declare the unexecuted mana-node scene fields')
        if row['id'] in contract.get('case_step_ids',{}):
            actual=[step['id'] for step in row.get('steps',[])]
            if actual!=contract['case_step_ids'][row['id']]:raise ValueError('Case steps are missing, misplaced or out of order: '+row['id'])
        if row['id'] in contract.get('restore_states',{}):
            if row.get('restoreState',{}).get('tag')!=contract['restore_states'][row['id']] or row.get('completeCalled')!=1:
                raise ValueError('EX did not complete the required restore branch: '+row['id'])
            state=row['restoreState']
            if state['tag']=='None' and (state.get('index')!=6 or state.get('params','missing') is not None):raise ValueError('EX None enum has an unexpected shape')
        for step in row.get('steps',[]):
            step_ids.append(step['id'])
            check_assertions(step)
            if not set(contract.get('required_step_checks',{}).get(step['id'],[]))<=set(c.get('name') for c in step.get('checks',[])):
                raise ValueError('Purchase result omits required native economic assertions')
            if step['id'] in contract['deferred_step_ids']:
                if step.get('status')!='deferred_to_full_load_carrier':raise ValueError('Full load must be explicitly deferred in flows')
                uncovered.append(step['id'])
            elif step.get('status')!='passed':raise ValueError('Required step did not pass: '+step['id'])
    if len(step_ids)!=len(set(step_ids)) or set(step_ids)!=set(contract['step_ids']):raise ValueError('Required steps are missing, duplicated or unexpected')
    if result.get('assertions',0)<contract['min_assertions']:raise ValueError('Required assertion count was not reached')
    return {'cases':len(rows),'steps':len(step_ids),'deferred_to_other_suite':uncovered,'executed_load_steps':sorted(set(contract.get('load_step_ids',[]))-set(uncovered)),**({'uncovered_fields':contract['uncovered_fields']} if contract.get('uncovered_fields') else {})}

def validate_application(built):
    application=Path(built['application']);root=ET.parse(application).getroot()
    nodes=root.findall('{*}initialWindow/{*}content')
    if len(nodes)!=1 or not nodes[0].text:raise ValueError('AIR descriptor must declare one initial content SWF')
    actual=(application.parent/nodes[0].text.strip()).resolve()
    if actual!=Path(built['swf']).resolve():raise ValueError('AIR descriptor points to a different SWF')
    return {'application_sha256':sha(application)}

def validate_binding(built,ctx):
    proof=read(built['proof']);identity=proof.get('input',proof.get('identity',{}))
    if proof.get('missing_required_methods'):raise ValueError('Required production methods are explicitly missing')
    if identity.get('swf_sha256')!=ctx['swf_sha256']:raise ValueError('Graft proof belongs to another input SWF')
    declared=proof.get('execution_swf_sha256',proof.get('target_swf_sha256'))
    if sha(built['swf'])!=declared:raise ValueError('Executed SWF is not the verified saved carrier')
    methods=proof.get('real_methods',proof.get('methods',[]))
    if not methods:raise ValueError('No verified production methods in carrier')
    for row in methods:
        for key in ('normalized_code_exceptions_equal','method_info_flags_defaults_exact','stack_locals_scope_exact','activation_traits_exact_after_pool_mapping'):
            if row.get(key) is not True:raise ValueError('Incomplete method readback proof: '+key)
    return {'swf_sha256':declared,'verified_methods':len(methods),'proof_sha256':sha(built['proof'])}
