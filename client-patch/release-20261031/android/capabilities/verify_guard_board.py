"""Execute actual final bytecode with the archived independent object worlds.

Only definitions are loaded from verify.py; old build/main/IO entry points are
not imported or called. This is an AVM2 interpreter check, not Adobe AIR/device.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import inspect
import itertools
import json
import math
from pathlib import Path
import types
from types import SimpleNamespace

import port_capabilities as p
import avm_interp as base_interp

def require(ok,message):
    if not ok:
        raise AssertionError(message)

def definitions(path,patch=None):
    tree=ast.parse(path.read_text('utf-8-sig'))
    tree.body=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))]
    env=dict(copy=copy,hashlib=hashlib,inspect=inspect,itertools=itertools,json=json,
        math=math,Path=Path,types=types,SimpleNamespace=SimpleNamespace,require=require,
        base_interp=base_interp,asm=p.asm,bodies=p.bodies,patch=patch)
    original=ast.parse(path.read_text('utf-8-sig'))
    for node in original.body:
        if isinstance(node,ast.Assign):
            try:
                value=ast.literal_eval(node.value)
            except (ValueError,TypeError):
                continue
            for target in node.targets:
                if isinstance(target,ast.Name):
                    env[target.id]=value
    exec(compile(tree,str(path),'exec'),env)
    env['VM']=env['_build_vm']()
    return env

def main():
    report=json.loads((p.ROOT/'build/partial-report.json').read_text('utf-8'))
    final=Path(report['latest_partial_swf'])
    selected=next(g for g in reversed(report['groups']) if g.get('status')=='built_partial')
    require(p.digest(final.read_bytes())==selected['output_sha256'],'partial identity differs')
    before=p.SwfAbc(p.BASE).abc
    after=p.SwfAbc(final).abc
    results={'status':'interpreter_only','input':str(final),'input_sha256':selected['output_sha256'],
        'air_tested':False,'device_tested':False,'groups':{}}
    for number,relative in [(193,'193-perfect-guard-wfx43/source/verify.py'),
                            (194,'194-gerald-mana-board2-lv120/source/board2/verify.py')]:
        try:
            patch=p.group_module(194,'gerald-mana-board2-lv120','board2/patch.py') if number==194 else None
            env=definitions(p.REFERENCES/relative,patch)
            cases,executed=env['run_behavior_cases'](before,after)
            results['groups'][str(number)]={'passed':True,'cases':cases,'executed_methods':executed}
            print(str(number)+' PASS '+str(len(cases)),flush=True)
        except Exception as exc:
            import traceback
            results['groups'][str(number)]={'passed':False,'error':repr(exc),'traceback':traceback.format_exc()}
            print(str(number)+' FAIL '+repr(exc),flush=True)
    (p.ROOT/'build/guard-board-interpreter.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n','utf-8')
    require(all(g['passed'] for g in results['groups'].values()),'a behavior group failed')

if __name__=='__main__':
    main()
