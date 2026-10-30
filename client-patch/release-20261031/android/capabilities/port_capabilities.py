"""Selective, transactional low-level patch execution against the accepted R11.

Historical build/main entry points are never called. Each group receives a new
Editor with its own current method contract, and a failure discards that whole
group. Explicit historical method/anchor checks inside patch functions remain.
"""
from __future__ import annotations
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
import re
from pathlib import Path
import sys
import traceback
import types

import bootstrap
from bootstrap import (ROOT, REFERENCES, BASE, BASE_SHA, CONTRACTS, DONOR,
                       REPOSITORY, input_path, output_path, require_hash)

SUPPORT = REFERENCES / '_build-v35/run11-source'
sys.path[:0] = [str(SUPPORT / 'vendor'), str(SUPPORT)]
import asm
asm.MNEMONICS.setdefault('avm_label', 0x09)
import bodies
from swfabc import SwfAbc
import framework
from static_check import check_body
from multiabc import compose, envelope, editors
from common import describe

PCODE_BY_HASH = None
DEFER_FINAL_DASH_HELPER = False

def bind_semantic_locks(module, editor):
    """Relocate a hash only with an archived, identical resolved instruction body.

    This is not a lock bypass: every opcode, constant value, branch target and
    method header must match the preimage P-code whose original hash is named
    by the source. Only the current R11 pool indices may differ.
    """
    global PCODE_BY_HASH
    if PCODE_BY_HASH is None:
        PCODE_BY_HASH={}
        rows=json.loads((CONTRACTS/'semantic-preimages.json').read_text('utf-8'))['preimages']
        for row in rows:
            PCODE_BY_HASH.setdefault(row['historical_code_sha256'],[]).append(row)
    evidence=[]
    for name,value in list(vars(module).items()):
        if not (name.endswith('LOCKS') or name=='DEPENDENCIES') or not isinstance(value,dict):
            continue
        for label,lock in value.items():
            tuple_lock=isinstance(lock,tuple) and len(lock)==2 and isinstance(lock[0],str)
            if tuple_lock:
                lock={'sha':lock[0],'header':lock[1]}
            if not isinstance(lock,dict) or not {'sha','header'}<=set(lock):
                continue
            current=editor.body(label)
            current_hash=digest(current[5])
            if current_hash==lock['sha']:
                continue
            if current[1:5] != lock['header']:
                continue
            normalized=[describe(editor.abc,x) for x in asm.decode(current[5])]
            for record in PCODE_BY_HASH.get(lock['sha'],[]):
                expected=record['instructions']
                if normalized==expected:
                    evidence.append({'label':label,'historical_sha':lock['sha'],
                                     'current_sha':current_hash,'source_git_path':record['source_git_path'],
                                     'proof':'identical resolved opcodes/constants/branches/header'})
                    lock['sha']=current_hash
                    if tuple_lock:
                        value[label]=(current_hash,lock['header'])
                    break
    editor.semantic_relocations=getattr(editor,'semantic_relocations',[])+evidence
    return evidence

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def body_bytes(body):
    fmt = framework.FMT
    writer = fmt.W()
    for value in body[:5]:
        writer.u30(value)
    writer.u30(len(body[5]))
    writer.raw(body[5])
    writer.u30(len(body[6]))
    for handler in body[6]:
        for value in handler:
            writer.u30(value)
    writer.u30(len(body[7]))
    for trait in body[7]:
        fmt.write_trait(writer, trait)
    return writer.out()

class R11Editor(framework.Editor):
    def __init__(self, source):
        super().__init__(source, locks={})
        self.contract = {}
        self.added_state = []

    def body(self, label):
        body = super().body(label)
        if label not in self.contract:
            self.contract[label] = {'sha': digest(body[5]), 'header': list(body[1:5]),
                                    'body': bodies.resolve(self.abc, label), 'method': body[0]}
            self.locks.setdefault(label, dict(self.contract[label]))
        return body

    def number(self, value):
        # Retain the archive's numeric expression fallback. Some source modules
        # intentionally synthesize large constants as several instructions;
        # adding an int instead would shift later reviewed helper anchors.
        return super().number(value)

    def add_slot(self, cls, name, type_name, static=False):
        result = super().add_slot(cls, name, type_name, static)
        self.added_state.append({'class': cls, 'name': name, 'type': type_name,
                                 'static': static, 'ios': 'requires_static_storage_AOT_mapping'})
        return result

def package(name, path):
    """Load an archive source directory under a private package, without main."""
    mod = types.ModuleType(name)
    mod.__path__ = [str(path)]
    sys.modules[name] = mod
    return mod

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

def group_module(number, slug, child='patches.py'):
    path = REFERENCES / f'{number}-{slug}' / 'source'
    name = 'batch' + str(number)
    package(name, path)
    parts = child.split('/')[:-1]
    for index in range(len(parts)):
        package(name+'.'+'.'.join(parts[:index+1]), path.joinpath(*parts[:index+1]))
    return load(name + '.' + child.removesuffix('.py').replace('/', '.'), path / child)

def board(e):
    return group_module(194, 'gerald-mana-board2-lv120', 'board2/patch.py').build(e)

def carry(e):
    return group_module(163, 'five-boss-stage-carry', 'stage_carry/patch.py').build(e)

def core(e):
    return group_module(112, 'wfx-effect-query').build(e)

def query(e):
    return group_module(112, 'wfx-effect-query', 'query.py').build(e)

def pf(e):
    return group_module(118, 'pf-lv4-data').build(e)

def fever_items(e):
    old=REPOSITORY/'docs/client-apk-patches-v33/93-fever-items-leading-dsl/source/feveritems_patches.py'
    load('feveritems_patches',old)
    return group_module(119,'fever-items-v2').build(e)

def leaders(e):
    return group_module(120, 'leader-unlock').build(e)

def overflow(e):
    return group_module(122, 'overflow-heal-damage').build(e)

def visuals(e):
    """123/124 source, rebound to the actual R11 auxiliary ABC contract."""
    from perf2_core import splice_with_exits
    module = group_module(123, 'ability-visuals', 'helpers.py')
    module.build(e)
    e.insert('BattleCharacterLogic/resolvePathCollection', 2, [
        ('getlocal_0',), ('getlocal_1',), ('getlocal_2',),
        ('callpropvoid', e.newq('wfxPreloadAbilityVisuals'), 2)])
    label = 'MemberImpl/wfxDirectFactor'
    ins = asm.decode(e.body(label)[5])
    if [x.name for x in ins[-2:]] != ['multiply','returnvalue']:
        raise ValueError('123/124 direct clamp tail differs')
    e.insert(label, len(ins)-1, [('dup',), ('pushbyte',0), ('ifge','OK'),
        ('pop',), ('pushbyte',0), ('label','OK')])
    tag='cn.mod.InahoAbilityVisuals'
    aux=R11Editor(SwfAbc(e.swf.path,tag=tag.encode()))
    hits=[i for i in range(1,len(aux.abc.multinames)) if aux.abc.mn_name(i)=='member']
    if len(hits)!=1:
        raise ValueError('ambiguous aux member symbol: '+repr(hits))
    member=hits[0]
    reader=aux.pool.public_qname('wfxAbilityVisualPaths',aux.q('Object'))
    shift=aux.pool.public_qname('shift',aux.q('http://adobe.com/AS3/2006/builtin::indexOf'))
    for label,slot in [('InahoAbilityVisuals$/shot',1),('InahoAbilityVisuals$/hit',2)]:
        code=[('getlocal_1',),('getproperty',member),('callproperty',reader,0),
              ('setlocal_3',),('getlocal_3',),('pushnull',),('ifeq','OLD')]
        for _ in range(slot):
            code += [('getlocal_3',),('callproperty',shift,0),('pop',)]
        code += [('getlocal_3',),('callproperty',shift,0),('setlocal_3',),
                 ('getlocal_3',),('iffalse','OFFICIAL'),('getlocal_3',),('returnvalue',),('label','OLD')]
        body=aux.body(label)
        if len(asm.decode(body[5])) < 9:
            raise ValueError('Inaho visual native fallthrough too short')
        raw,exc,_,_=splice_with_exits(body,2,code,{'OFFICIAL':8},asm.ENTER)
        aux.replace(label,raw,exc)
    aux.insert('InahoAbilityVisuals$/preload',2,[('returnvoid',)])
    aux.apply()
    e.extra_editors[tag]=aux
    return {'patches':[123,124],'rebound':'current R11 aux ABC; source insertions preserved',
            'aux_target':tag}

def fever(e):
    return group_module(125,'super-fever','superfever/patches.py').build(e)

def superdamage(e):
    return group_module(125,'super-fever','superdamage/patches.py').build(e)

def superpreload(e):
    return group_module(125,'super-fever','superpreload/patches.py').build(e)

def voices(e):
    return group_module(128,'dual-form-uid','voice_dual/patches.py').build(e)

def heal_damage(e):
    return group_module(132,'heal-damage','heal_damage/patches.py').build(e)

def heal_resources(e):
    return group_module(132,'heal-damage','heal_resources/patches.py').build(e)

def heal_fever(e):
    return group_module(133,'heal-fever','heal_fever/patches.py').build(e)

def unlockv2(e):
    # Earlier partial helper used a single newly pooled 1021000 constant. Restore
    # the source common.n arithmetic encoding before applying its next-stage
    # instruction anchors. Both representations evaluate the same int value.
    label='BattleCharacterLogic/wfxExtraLeaders'
    ins=asm.decode(e.body(label)[5])
    hits=[i for i,x in enumerate(ins) if x.name=='pushint' and e.abc.ints[x.args[0]]==1021000]
    if hits:
        if len(hits)!=1:
            raise ValueError('ambiguous leader identity constant')
        pf_module=group_module(118,'pf-lv4-data')
        pf_module.rewrite(e,label,[(hits[0],hits[0]+1,[('pushshort',1021),('pushshort',1000),
                            ('multiply',),('pushbyte',0),('add',),('convert_i',)])])
        body=e.body(label)
        e.locks[label]={'sha':digest(body[5]),'header':list(body[1:5])}
    module=group_module(134,'leader-unlock-v2','leader_unlock/patches.py')
    bind_semantic_locks(module,e)
    return module.build(e)

def leaderguard(e):
    module=group_module(135,'wfx-no-leader-guard','leader_guard/patches.py')
    bind_semantic_locks(module,e)
    return module.build(e)

def global_module(number,slug,sub):
    path=REFERENCES/f'{number}-{slug}'/'source'/sub
    package(sub,path)
    return load(sub+'.patches',path/'patches.py')

def fullmaterials(e):
    from perf2_core import splice_with_exits
    module=global_module(136,'overlimit-full-and-window-guard','materials')
    full=module.install(e)
    # These are reviewed against the current R11 material-compatibility bodies,
    # including its extra max-step check and its display-only fallback array.
    sites={
      'OwnedOverLimitLogic/getOwnAwakingCrystalToOverLimit':[(86,101,'character','pushtrue')],
      'OwnedOverLimitLogic/getAwakingCrystalToOverLimit':[(102,117,'character','pushtrue'),
                                                        (148,163,'character','getlocal_2')],
      'OwnedOverLimitLogic/getOverLimitState':[(34,46,'character','pushfalse')],
      'OwnedCharacterLogic/getPossibleOverLimitCountByItem':[(18,28,None,'getlocal_1')],
      'OverLimitWindow/getOverLimitState':[(14,32,'targetCharacter','getlocal_0')],
      'OverLimitWindow/run':[(88,106,'targetCharacter','getlocal')],
      'OverLimitWindow/getStatusInformation':[(19,37,'targetCharacter','getlocal_2')],
      'ExpodOverLimitByItemDialog/getDescription':[(11,29,'character','pushstring')],
    }
    details=[]
    for label,locations in sites.items():
        original=e.body(label)
        ins=asm.decode(original[5]);working=copy.deepcopy(original);edits=[]
        # Close the same pre-existing unreachable native jump-to-end recognized
        # by archive136. The old jump and all original bytes remain untouched.
        if label=='OwnedCharacterLogic/getPossibleOverLimitCountByItem':
            end=len(ins)
            raw,exc,_=asm.splice(working,end,asm.assemble([('avm_label',),('pushbyte',0),('returnvalue',)]),asm.ENTER)
            working[5],working[6]=raw,exc
            edits.append((end,3,asm.ENTER))
        for at,target,prop,target_op in sorted(locations,reverse=True):
            if ins[target].name!=target_op:
                raise ValueError('R11 full-mode destination differs: '+label)
            normalized=[describe(e.abc,op) for op in ins[at:target]]
            cached_rarity=(label.endswith('/getOwnAwakingCrystalToOverLimit') and
                ins[at].name=='getlocal' and ins[at].args==[2]) or (
                label.endswith('/getAwakingCrystalToOverLimit') and ins[at].name in ('getlocal_1','getlocal') and
                (ins[at].name=='getlocal_1' or ins[at].args==[1]))
            if not (cached_rarity or any('get_rarity' in op for op in normalized)) or not any('overLimitStep' in op for op in normalized):
                raise ValueError('R11 full-mode rarity/step guard differs: '+label)
            code=[('getlocal_0',)]
            if prop:code.append(('getproperty',e.q(prop)))
            code += [('callproperty',full,0),('iftrue','FULL')]
            raw,exc,_,count=splice_with_exits(working,at,code,{'FULL':target},asm.FORBID)
            working[5],working[6]=raw,exc
            edits=[(old_at+count,old_count,incoming) for old_at,old_count,incoming in edits]
            edits.append((at,count,asm.FORBID))
            details.append({'label':label,'before_site':at,'before_full_destination':target,
                            'receiver':prop or 'this','native_guard':normalized})
        recovery=sorted(edits)
        if asm.unsplice_many(working[5],recovery)!=original[5]:
            raise ValueError('R11 native material-compatibility body did not recover: '+label)
        e.replace(label,working[5],working[6])
        e.report[label]['insertions']=recovery
    return {'patch':136,'native_R11_instructions_exactly_recoverable':True,'sites':details,
       'compatibility':'retained existing R11 display-only fallback; added full selector at its rarity/step guard as well',
       'zero_stock':'original owned-item filtering, paradox-core cap and confirmation gates retained'}

def pedestals(e):
    module=global_module(136,'overlimit-full-and-window-guard','pedestals')
    bind_semantic_locks(module,e)
    return module.build(e)

def windowguard(e):
    return global_module(136,'overlimit-full-and-window-guard','window').build(e)

def ownermain(e):
    # Same reviewed common.n identity encoding as the source's original COUNT
    # preimage. The first partial's permissive numeric pool changed only these
    # two expression encodings, so restore them before the exact next-stage CFG.
    label='BattleCharacterLogic/getInstantAbiltyCountWithoutLimit'
    ins=asm.decode(e.body(label)[5])
    changes=[]
    for at,op in enumerate(ins):
        if op.name=='pushint' and e.abc.ints[op.args[0]] in (1021000,1024000):
            value=e.abc.ints[op.args[0]]
            changes.append((at,at+1,[('pushshort',value//1000),('pushshort',1000),
                 ('multiply',),('pushbyte',0),('add',),('convert_i',)]))
    if changes:
        group_module(118,'pf-lv4-data').rewrite(e,label,changes)
        body=e.body(label)
        e.locks[label]={'sha':digest(body[5]),'header':list(body[1:5])}
    module=global_module(137,'leader-unlock-owner-main','owner_main')
    bind_semantic_locks(module,e)
    return module.build(e)

def archived_code(e, path, allow_new=()):
    """Resolve this archive's readable P-code onto R11 pools, preserving CFG."""
    code=[]
    lines=json.loads((CONTRACTS/'helper-instructions.json').read_text('utf-8'))['methods'][path]['instruction_lines']
    for line in lines:
        hit=re.match(r'^#(\d+) ofs[0-9a-f]+: (\w+) (\[.*?\])(?: -> #(\d+))?$',line)
        if not hit:
            continue
        index,op,values,target=hit.groups()
        args=ast.literal_eval(values)
        code.append(('label','I'+str(int(index))))
        if target is not None:
            code.append((op,'I'+target))
            continue
        if op in {'getlex','findproperty','findpropstrict','getproperty','setproperty','initproperty',
                  'coerce','astype','callproperty','callpropvoid','constructprop','callproplex',
                  'callsuper','callsupervoid','getsuper','setsuper','deleteproperty','istype'}:
            symbol=args[0]
            args[0]=e.newq(symbol) if symbol in allow_new else e.q(symbol)
        elif op=='pushstring':
            args[0]=e.pool.string(args[0])
        elif op=='pushint':
            args[0]=e.pool.integer(args[0])
        elif op in {'pushuint','pushdouble'}:
            pool=getattr(e.abc,'uints' if op=='pushuint' else 'doubles')
            if args[0] not in pool:
                raise ValueError('archived numeric constant absent '+repr(args))
            args[0]=pool.index(args[0])
        code.append((op,*args))
    return code

def identity_tags(e):
    cls='pinball.common.data.battle.squadMember::CharacterBaseImpl'
    helper=e.add_method(cls,'wfxCharacterIdentityTags','Array',['Array'],
            archived_code(e,'identity_tags'),4)
    label='CharacterBaseImpl/get_characterTags'
    ins=asm.decode(e.body(label)[5])
    if len(ins)!=7 or [x.name for x in ins[-2:]]!=['coerce','returnvalue']:
        raise ValueError('identity tags getter native anchor differs')
    e.insert(label,6,[('getlocal_0',),('swap',),('callproperty',helper,1)])
    return {'patch':138,'source':'explicit archived P-code; additive getter wrapper'}

def caster_barrier(e):
    helper=e.add_method('pinball.scene.battle.battle.action::ActionEvaluator',
        'wfxBarrierRequest','Object',['Object'],
        archived_code(e,'caster_barrier',{'wfxBarrierOwner'}),4)
    label='ActionEvaluator/evalCommand'
    ins=asm.decode(e.body(label)[5])
    hits=[i for i,x in enumerate(ins) if x.name=='callproperty' and e.abc.mn_name(x.args[0])=='Barrier']
    if len(hits)!=1 or ins[hits[0]-1].name!='newobject' or ins[hits[0]-1].args!=[1]:
        raise ValueError('CreateBarrier request construction differs')
    e.insert(label,hits[0],[('getlocal_0',),('swap',),('callproperty',helper,1)])
    label='BarrierCalculator/calculate'
    ins=asm.decode(e.body(label)[5])
    if [x.name for x in ins[:4]]!=['getlex','getlex','getlocal_1','callproperty'] or not e.abc.mn_name(ins[3].args[0]).endswith('::getRealMaximumHealthPoint'):
        raise ValueError('barrier target HP anchor differs')
    e.insert(label,3,[('getlocal_2',),('getproperty',e.newq('wfxBarrierOwner')),
          ('dup',),('iffalse','NATIVE_TARGET'),('swap',),('pop',),('jump','HP'),
          ('label','NATIVE_TARGET'),('pop',),('label','HP')])
    return {'patch':139,'source':'archived helper plus exact request and HP expression insertions',
            'state':'dynamic wfxBarrierOwner on native Object request; no class fields'}

def direct_count(e):
    package('batch141',SUPPORT)
    package('batch141.direct_count',SUPPORT/'direct_count')
    module=load('batch141.direct_count.patches',SUPPORT/'direct_count/patches.py')
    bind_semantic_locks(module,e)
    return module.build(e)

def heal_any(e):
    package('batch142',SUPPORT)
    package('batch142.heal_any',SUPPORT/'heal_any')
    module=load('batch142.heal_any.patches',SUPPORT/'heal_any/patches.py')
    bind_semantic_locks(module,e)
    bind_semantic_locks(module.ct_patch,e)
    original_install=module.ct_patch.install
    def install_with_generated_preimage(editor,m,value):
        # Compare the newly generated pre-CT helper against the archived final
        # helper with its eight-instruction CT prologue removed. This proves its
        # entire preimage rather than accepting a changed hash on faith.
        record=json.loads((CONTRACTS/'helper-instructions.json').read_text('utf-8'))['methods']['ct_predecessor']
        lines=[hit.group(1) for line in record['instruction_lines']
               if (hit:=re.match(r'^#\d+ ofs[0-9a-f]+: (.*)$',line))]
        if lines[2:10]!=['getlocal_0 []','getlocal_1 []','getlocal_2 []','getlocal_3 []',
             'getlocal [4]',"callproperty ['wfxHealAnyCTRecord', 4]",'iffalse [] -> #10','returnvoid []']:
            raise ValueError('archived CT prologue differs')
        expected=lines[:2]+lines[10:]
        expected=[re.sub(r'-> #(\d+)',lambda h:'-> #'+str(int(h[1])-8 if int(h[1])>=10 else int(h[1])),line) for line in expected]
        body=editor.body(module.ct_patch.DAMAGE)
        actual=[describe(editor.abc,op) for op in asm.decode(body[5])]
        if actual!=expected or body[1:5]!=module.ct_patch.SECOND_DAMAGE_HEADER:
            raise ValueError('newly generated CT preimage differs semantically from archive')
        historical=module.ct_patch.SECOND_DAMAGE_SHA
        module.ct_patch.SECOND_DAMAGE_SHA=digest(body[5])
        editor.semantic_relocations=getattr(editor,'semantic_relocations',[])+[{
            'label':module.ct_patch.DAMAGE,'historical_sha':historical,
            'current_sha':module.ct_patch.SECOND_DAMAGE_SHA,'source_git_path':record['source_git_path'],
            'proof':'identical entire resolved pre-CT helper after exact eight-instruction prologue removal'}]
        return original_install(editor,m,value)
    module.ct_patch.install=install_with_generated_preimage
    return module.build(e)

def atlas_preload(e):
    module=group_module(157,'atlas-preload-dualform-and-ability-dmg','atlas_preload/patch.py')
    bind_semantic_locks(sys.modules['batch157.atlas_preload.inline'],e)
    return module.build(e)

def summon_cutin(e):
    module=group_module(158,'summon-cutin-preload','summon_cutin_preload/patch.py')
    bind_semantic_locks(module,e)
    leading=module.LEADING
    expected,header=module.DEPENDENCIES[leading]
    current=e.body(leading)
    if digest(current[5])!=expected:
        # Recover the genuine missing p11 support-preload predecessor from the
        # fixed donor. Its exact original hash is the source's dependency lock.
        donor=SwfAbc(DONOR_PATH)
        donor_body=donor.abc.bodies[bodies.resolve(donor.abc,leading)]
        if digest(donor_body[5])!=expected or donor_body[1:5]!=header:
            raise ValueError('fixed donor does not match p11 leading preimage')
        graft_donor(e,['ActionDslHandler/wfxPreloadSummonSupport',
                      'ActionDslHandler/wfxPreloadSummonSupports',leading],insertion_only=[leading])
        current=e.body(leading)
        if [describe(e.abc,x) for x in asm.decode(current[5])]!=[describe(donor.abc,x) for x in asm.decode(donor_body[5])]:
            raise ValueError('relocated p11 leading instructions differ')
        module.DEPENDENCIES[leading]=(digest(current[5]),header)
        e.semantic_relocations=getattr(e,'semantic_relocations',[])+[{'label':leading,
             'historical_sha':expected,'current_sha':digest(current[5]),
             'proof':'fixed donor exact locked preimage and identical relocated complete body'}]
    return module.build(e)

def combo_base(e):
    return group_module(159,'combo-base-wfx41','combo_base/patch.py').build(e)

def dual_pf(e):
    path=REFERENCES/'160-dual-pf-wfx42/source'
    package('dual_pf_preload',path/'dual_pf_preload')
    package('dual_pf',path/'dual_pf')
    module=group_module(160,'dual-pf-wfx42','dual_pf/patch.py')
    preload=module.preload
    preload.LOCKS={preload.TARGETS[0]:{'sha':preload.BASE_SHA,'header':[6,10,1,2]}}
    bind_semantic_locks(preload,e)
    preload.BASE_SHA=preload.LOCKS[preload.TARGETS[0]]['sha']
    return module.build(e)

def summon_flip(e):
    return group_module(161,'summon-flip-pf','summon_flip_pf/patch.py').build(e)

def ball_action(e):
    path=REFERENCES/'160-dual-pf-wfx42/source'
    package('dual_pf_preload',path/'dual_pf_preload')
    package('dual_pf',path/'dual_pf')
    module=group_module(162,'ball-pf-action','ball_pf_action/patch.py')
    def current_bundled_keys():
        import io,zipfile
        identity=json.loads((CONTRACTS/'capability-order.json').read_text('utf-8'))
        registry=dict(apk=str(input_path('android.inputs.r11_apk.path')),
                      apk_sha256=identity['baseline_apk_sha256'])
        require_hash(registry['apk'],registry['apk_sha256'])
        logical=module.bundled.PATH
        hashed=hashlib.sha1((logical+module.bundled.SALT).encode()).hexdigest()
        suffix=hashed[:2]+'/'+hashed[2:]
        with zipfile.ZipFile(registry['apk']) as apk:
            with zipfile.ZipFile(io.BytesIO(apk.read('assets/bundle.zip'))) as bundle:
                matches=[n for n in bundle.namelist() if n.endswith('/'+suffix)]
                if len(matches)!=1:
                    raise ValueError('R11 PFA bundle member not unique')
                raw=bundle.read(matches[0])
        keys=module.bundled.keys(raw)
        return keys,{'logical_path':logical,'key_count':len(keys),'keys':keys,
                     'sources':[{'apk':registry['apk'],'apk_sha256':registry['apk_sha256'],
                                 'bundle_entry':matches[0],'table_sha256':digest(raw)}]}
    module.bundled.load=current_bundled_keys
    return module.build(e)

def pf_chain_group(e,sub):
    module=group_module(144,'pf-unison-chain',sub+'/patch.py')
    bind_semantic_locks(module,e)
    if hasattr(module,'movement'):
        bind_semantic_locks(module.movement,e)
    return module.build(e)

def pf_chain_preload(e):
    path=REFERENCES/'144-pf-unison-chain/source/preload/patch.py'
    # The archive omitted target-locks.json. Build a new reviewed current-input
    # contract; the patch still validates every concrete source instruction used.
    tree=ast.parse(path.read_text('utf-8-sig'))
    tree.body=[node for node in tree.body if not (isinstance(node,ast.Assign) and
        any(isinstance(t,ast.Name) and t.id=='LOCKS' for t in node.targets))]
    mod=types.ModuleType('batch144preload')
    mod.__file__=str(path)
    exec(compile(tree,str(path),'exec'),mod.__dict__)
    mod.LOCKS={label:e.body(label) for label in mod.TARGETS}
    return mod.build(e)

def pf4(e):
    return group_module(154,'pf4-source-unison','src/patch.py').build(e)

def combo_cap(e):
    return group_module(156,'direct-combo-cap','direct_combo_cap/patch.py').build(e)

def trial_pf(e):
    path=REFERENCES/'153-hell-pumpkin-pf-trial/source'
    sys.path.insert(0,str(path))
    common=load('pa_common',path/'pa_common.py')
    label='HitCountCheck/matchTrial'
    body=e.body(label)
    if digest(body[5])!=common.CODE_SHA256 or body[1:5]!=common.HEADER:
        raise ValueError('P-a native matchTrial lock differs')
    idx=bodies.resolve(e.abc,label)
    common.BODY_INDEX=idx
    module=load('pa_patch',path/'pa_patch.py')
    original=copy.deepcopy(body)
    _,detail=module.build(e.swf)
    changed=copy.deepcopy(e.abc.bodies[idx])
    e.abc.bodies[idx]=original
    e.replace(label,changed[5],changed[6],changed[1:5])
    return detail

def guard_signed(e):
    module=group_module(193,'perfect-guard-wfx43','guard/patch.py')
    bind_semantic_locks(module,e)
    body=e.body(module.SPEC)
    if digest(body[5])!=module.LOCKS[module.SPEC]['sha'] or body[1:5]!=module.LOCKS[module.SPEC]['header']:
        raise ValueError('signed guard parser preimage differs')
    module.parser(e)
    return {'patch':193,'signed_arg_flags':True,'code':43}

DONOR_SHA='2fa334cca6b104bdcae061c5ed9bc63eb52d59db7e687c90d24742e61759e7b4'
DONOR_PATH=DONOR

def graft_donor(e,labels,slots=(),insertion_only=()):
    """Import selected methods and only their real closures, never donor classes."""
    if digest(DONOR_PATH.read_bytes())!=DONOR_SHA:
        raise ValueError('fixed donor identity changed')
    path=REPOSITORY/'client-patch/lens0907-0908/build_swf.py'
    module=load('capability_named_importer',path)
    donor=SwfAbc(DONOR_PATH)
    source_view=module.View(donor,asm)
    target_view=module.View(e.swf,asm)
    importer=module.Importer(target_view,source_view)
    source_label_map={v:k for k,v in bodies.label_map(donor.abc).items()}
    target_label_map={v:k for k,v in bodies.label_map(e.abc).items()}
    sources={b[0]:i for i,b in enumerate(donor.abc.bodies)}
    selected=[]
    original_count=len(e.abc.bodies)
    contracts=[]
    for label in labels:
        si=source_label_map[label]
        sm=donor.abc.bodies[si][0]
        for op in asm.decode(donor.abc.bodies[si][5]):
            if op.name=='pushstring' and any(x in donor.abc.s(op.args[0]).lower() for x in ('riven','unit_prefix_m','unit_prefix_b','unit_prefix_t')):
                raise ValueError('excluded donor dependency in '+label)
            if op.op in module.MULTINAME_OPS and 'riven' in donor.abc.mn_name(op.args[0]).lower():
                raise ValueError('riven symbol in selected donor body: '+label)
        if label in target_label_map:
            ti=target_label_map[label]
            e.body(label)
            tm=e.abc.bodies[ti][0]
            if label in insertion_only:
                proof=module.insertion_proof(target_view.normalized(ti),source_view.normalized(si))
                if not proof:
                    raise ValueError('donor replacement is not additive: '+label)
            contracts.append({'label':label,'before_sha':digest(e.abc.bodies[ti][5]),'new':False})
        else:
            tm=len(e.abc.methods)
            ti=len(e.abc.bodies)
            e.abc.methods.append([0,[],0,0,None,None])
            e.abc.bodies.append([tm,1,1,1,1,b'\x47',[],[]])
            contracts.append({'label':label,'new':True})
        importer.methods[sm]=tm
        selected.append((sm,tm,label,ti))
    pending=list(selected)
    seen=set()
    for sm,tm,label,ti in pending:
        if sm in seen:
            continue
        seen.add(sm)
        for op in asm.decode(donor.abc.bodies[sources[sm]][5]):
            if op.op in (0x40,0x44) and importer.methods.get(op.args[0]) is None:
                child=op.args[0];mid=len(e.abc.methods);bi=len(e.abc.bodies)
                importer.methods[child]=mid
                e.abc.methods.append([0,[],0,0,None,None]);e.abc.bodies.append([mid,1,1,1,1,b'\x47',[],[]])
                pending.append((child,mid,label+'/closure:'+str(child),bi))
        e.abc.methods[tm]=importer.info(sm)
        body=importer.body(sources[sm],tm)
        checks=check_body(e.abc,body)
        e.abc.bodies[ti]=body
        if ti<original_count:
            e.report[label]={'body':ti,'before':e.contract[label]['sha'],'after':digest(body[5]),
                'before_header':e.contract[label]['header'],'after_header':body[1:5],'static_check':checks,
                'donor':DONOR_SHA,'insertion_only':label in insertion_only}
        else:
            e.new_methods.append({'label':label,'body':ti,'name':label.split('/')[-1],
                 'sha256':digest(body[5]),'header':body[1:5],'static_check':checks,'donor_method':sm,
                 'signature':e.abc.methods[tm]})
    # Append only selected traits; omitted slots and all donor cinit/iinit stay out.
    selected_mids={sm for sm,_,_,_ in selected}
    for ci,row in enumerate(donor.abc.instances):
        cls=donor.abc.mn_name(row[0])
        for static,traits in [(False,row[6]),(True,donor.abc.classes[ci][1])]:
            for trait in traits:
                short=donor.abc.mn_name(trait.name).split('::')[-1]
                method=trait.data[0]=='method' and trait.data[2] in selected_mids
                slot=trait.data[0]=='slot' and (cls,short,static) in slots
                if not method and not slot:
                    continue
                tci,trow=e.instance(cls)
                target_traits=e.abc.classes[tci][1] if static else trow[6]
                exists=[x for x in target_traits if e.abc.mn_name(x.name)==donor.abc.mn_name(trait.name)]
                if exists:
                    if slot:
                        raise ValueError('donor slot already exists: '+short)
                    continue
                if slot and not static:
                    raise ValueError('instance state needs explicit ABI adapter: '+short)
                mapped=importer.trait(trait)
                target_traits.append(mapped)
                e.traits.append((cls,short,static))
                if slot:
                    e.added_state.append({'class':cls,'name':short,'type':e.abc.mn_name(mapped.data[2]),
                        'static':static,'ios':'requires_static_storage_AOT_mapping','donor':DONOR_SHA})
    bodies._CACHE.pop(id(e.abc),None)
    e.donor_contract=getattr(e,'donor_contract',[])+contracts
    return {'donor_sha256':DONOR_SHA,'selected':list(labels),'actual_method_and_closure_count':len(seen)}

def donor_dash(e):
    ball='pinball.scene.battle.battle.squad.ball::BallImpl'
    names=['wfxTeleportNearTarget','wfxDashLanding','wfxGetDashPending','wfxTryDashReplacement',
           'wfxUpdateDashReplacement','wfxFindDashEnemy','wfxDashWallOverlap','wfxDashPointClear',
           'wfxSafeDashLanding','wfxDashV2Landing','wfxRefreshDashLanding']
    labels=['BallImpl/'+n for n in names]+['BallImpl$/'+n for n in
        ['wfxParseDashTags','wfxParseDashV2Tags','wfxParseDashLeaderTags','wfxFilterLeaderDash']]
    hooks=['BallImpl/'+n for n in ['update','tryEscape','move','enterEscapingState','applyMovement']]
    labels+=hooks+['BattleCharacterLogic/wfxPreloadDash']
    if not DEFER_FINAL_DASH_HELPER:
        labels.append('MemberImpl/wfxRunDashAction')
    result=graft_donor(e,labels,[(ball,'wfxDashPending',True)],hooks)
    label='BattleCharacterLogic/resolvePathCollection'
    e.insert(label,2,[('getlocal_0',),('getlocal_1',),('callpropvoid',e.q('wfxPreloadDash'),1)])
    return result

def donor_leader_display(e):
    labels=json.loads((CONTRACTS/'leader-display-labels.json').read_text('utf-8'))['labels']
    get='TriggerableAbilityDialogAllAbilitiesGenerator/get'
    result=graft_donor(e,[l for l in labels if l!=get])
    ins=asm.decode(e.body(get)[5])
    if [op.name for op in ins[-2:]]!=['getlocal','returnvalue'] or ins[-2].args!=[5]:
        raise ValueError('leader display return array anchor differs')
    e.insert(get,len(ins)-2,[('getlocal_0',),('getlocal',5),('getlocal_1',),('getlocal_3',),
                  ('callpropvoid',e.q('wfxAppendUnisonLeader'),3)])
    return result

def equipment(e):
    return group_module(129, 'equipment-rules-data', 'equipment/patches.py').build(e)

def unique(e):
    return group_module(130, 'direct-target-unique', 'direct_unique/patches.py').build(e)

def hidden(e):
    return group_module(131, 'wfx-hidden-unique-icons', 'hidden_icons/patches.py').build(e)

def leader_kinds(e):
    return group_module(155, 'leader-table-patched-kinds', 'leader_kinds/patch.py').build(e)

def guard(e):
    # Full historic guard parser requires code36's intermediate body. Review the
    # R11-derived parser and add the narrow hasGuarded hook independently here.
    module = group_module(193, 'perfect-guard-wfx43', 'guard/patch.py')
    e.body(module.GUARD)
    current = e.body(module.GUARD)
    expected = module.LOCKS[module.GUARD]
    if digest(current[5]) != expected['sha'] or current[1:5] != expected['header']:
        raise asm.AsmError('hasGuarded differs from reviewed native anchor')
    module.patch_has_guarded(e)
    return {'hook': 'hasGuarded', 'code': 43,
            'parser': 'zero/nonnegative guard parameters accepted by installed query parser',
            'signed_parameter_extension': 'not_installed_in_this_group'}

GROUPS = [
    ('194-board2', board, []),
    ('163-carry', carry, []),
    ('112-116-core', core, []),
    ('112-query-fallback', query, ['core_failed']),
    ('117-118-pf', pf, []),
    ('119-fever-items',fever_items,[]),
    ('120-121-leaders', leaders, []),
    ('122-overflow', overflow, []),
    ('129-equipment', equipment, []),
    ('131-hidden', hidden, []),
    ('155-leader-kinds', leader_kinds, []),
    ('193-guard', guard, ['query_available']),
    ('123-124-visuals-clamp', visuals, []),
    ('130-direct-unique', unique, []),
    ('125-fever', fever, []),
    ('125-superdamage', superdamage, []),
    ('125-superpreload', superpreload, []),
    ('126-128-voices-dual', voices, []),
    ('132-heal-damage', heal_damage, []),
    ('132-heal-resources', heal_resources, []),
    ('133-heal-fever', heal_fever, []),
    ('134-unlock-v2', unlockv2, []),
    ('135-leader-guard', leaderguard, []),
    ('136-window', windowguard, []),
    ('136-materials', fullmaterials, []),
    ('136-pedestals', pedestals, []),
    ('137-owner-main', ownermain, []),
    ('138-identity-tags',identity_tags,[]),
    ('139-caster-barrier',caster_barrier,[]),
    ('141-direct-count',direct_count,[]),
    ('142-143-heal-any',heal_any,[]),
    ('144-override',lambda e:pf_chain_group(e,'override'),[]),
    ('144-chain',lambda e:pf_chain_group(e,'chain'),[]),
    ('144-lifecycle',lambda e:pf_chain_group(e,'lifecycle'),[]),
    ('144-preload',pf_chain_preload,[]),
    ('144-damage',lambda e:pf_chain_group(e,'damage'),[]),
    ('153-trial-pf',trial_pf,[]),
    ('154-pf4-source',pf4,[]),
    ('156-combo-cap',combo_cap,[]),
    ('157-atlas-preload',atlas_preload,[]),
    ('158-summon-cutin',summon_cutin,[]),
    ('159-combo-base',combo_base,[]),
    ('160-dual-pf',dual_pf,[]),
    ('161-summon-flip',summon_flip,[]),
    ('162-ball-action',ball_action,[]),
    ('193-signed-parser',guard_signed,[]),
    ('140-leader-display',donor_leader_display,[]),
    ('dash-v2-final',donor_dash,[]),
]

def snapshot_existing(abc):
    return [copy.deepcopy(body) for body in abc.bodies]

def main():
    global DEFER_FINAL_DASH_HELPER
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--run',default='')
    ap.add_argument('--frozen-release-profile',action='store_true',
                    help='Replay the pinned successful construction order; apply final dash repair separately')
    args = ap.parse_args()
    order=None
    groups=GROUPS
    if args.frozen_release_profile:
        order=json.loads((CONTRACTS/'capability-order.json').read_text('utf-8'))
        available={row[0]:row for row in GROUPS}
        groups=[available[row['name']] for row in order['ordered_groups']]
        DEFER_FINAL_DASH_HELPER=order['historical_deferred_dash_helper']
    build_root=ROOT/'build'/args.run if args.run else ROOT/'build'
    report_path=build_root/'partial-report.json'
    if digest(BASE.read_bytes()) != BASE_SHA:
        raise ValueError('R11 extracted input differs from prior verified baseline')
    summary = {'status': 'partial_candidate_only', 'baseline_swf': str(BASE),
               'baseline_sha256': BASE_SHA, 'pr_head': '5f70aec391c011f8d3066d41021fe06f27c07f84',
               'device_tested': False, 'groups': [], 'excluded': [145,146,148,149,150,151,152,164,'165-192','195P6','195P7']}
    source = BASE
    success = set()
    if args.resume:
        summary=json.loads(report_path.read_text('utf-8'))
        successful=[g for g in summary['groups'] if g.get('status')=='built_partial']
        success={g['name'] for g in successful}
        if successful:
            source=Path(successful[-1]['output'])
            if digest(source.read_bytes()) != successful[-1]['output_sha256']:
                raise ValueError('resume candidate differs from prior receipt')
    selected = set(args.only.split(',')) if args.only else None
    for name, fn, needs in groups:
        if name=='163-carry':
            continue  # Replaced by the independently reviewed cn.carry helper.
        if name in success:
            continue
        if selected is not None and name not in selected:
            continue
        if 'core_failed' in needs and '112-116-core' in success:
            continue
        if 'query_available' in needs and not success.intersection({'112-116-core','112-query-fallback'}):
            summary['groups'].append({'name': name, 'status':'dependency_unavailable'})
            continue
        print('START '+name, flush=True)
        entry = {'name': name, 'input': str(source)}
        try:
            swf = SwfAbc(source)
            editor = R11Editor(swf)
            detail = fn(editor)
            editor.apply()
            changed = set(editor.report)
            # The source Editor deep-copies original bodies before any patch.
            touched_indices = {bodies.resolve(editor.abc, label) for label in changed}
            for index, before in enumerate(editor.original_bodies):
                if index not in touched_indices and body_bytes(editor.abc.bodies[index]) != body_bytes(before):
                    raise ValueError('undeclared original body mutation: '+str(index))
            for label in changed:
                check_body(editor.abc, editor.body(label))
            candidate = output_path(build_root/f'{name}.partial.swf')
            raw = compose(editor)
            candidate.write_bytes(raw)
            reread = SwfAbc(candidate)
            if reread._raw != editor.abc.serialize():
                raise ValueError('serialized final ABC readback differs')
            extra_reports={}
            for tag,aux in editor.extra_editors.items():
                reread_aux=SwfAbc(candidate,tag=tag.encode())
                if reread_aux._raw != aux.abc.serialize():
                    raise ValueError('aux ABC readback differs: '+tag)
                extra_reports[tag]={'contract':aux.contract,'changed':aux.report,
                                    'added_methods':aux.new_methods,'added_state':aux.added_state}
            envelope_result=envelope(swf,reread,{tag for tag,_ in editors(editor)})
            entry.update(status='built_partial', output=str(candidate), output_sha256=digest(raw),
                         baseline_contract=editor.contract, changed=editor.report,
                         added_methods=editor.new_methods, added_state=editor.added_state,
                         traits=editor.traits, pools=editor.pool.report(), detail=detail,
                         aux=extra_reports,envelope=envelope_result,
                         semantic_relocations=getattr(editor,'semantic_relocations',[]),
                         donor_contract=getattr(editor,'donor_contract',[]),
                         unchanged_original_bodies=len(editor.original_bodies)-len(touched_indices))
            source=candidate
            success.add(name)
            print('BUILT '+name, flush=True)
        except Exception as exc:
            entry.update(status='rejected_group', error=repr(exc), traceback=traceback.format_exc())
            print('REJECT '+name+' '+repr(exc), flush=True)
        summary['groups'].append(entry)
        summary['latest_partial_swf']=str(source)
        output_path(report_path).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
    if args.run:
        output_path(ROOT/'build/partial-report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
    if order is not None:
        expected={row['name']:row['expected_output_sha256'] for row in order['ordered_groups']}
        for row in summary['groups']:
            if row.get('status')=='built_partial' and row['name'] in expected:
                if row['output_sha256']!=expected[row['name']]:
                    raise ValueError('Frozen stage output differs: '+row['name'])
        required=set(expected) if selected is None else selected
        if required-success:
            raise ValueError('Selected frozen groups did not complete: '+str(sorted(required-success)))
    print(json.dumps({'latest_partial_swf':str(source),'groups':[{k:v for k,v in x.items() if k in ('name','status','error')} for x in summary['groups']]},ensure_ascii=False),flush=True)

if __name__ == '__main__':
    main()
