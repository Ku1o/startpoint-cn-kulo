"""Exact R11 shop withdrawal contract; no historical degree group is ever selected."""
import argparse, copy, hashlib, json
from pathlib import Path
from input_config import configure_support, input_path, require_output
configure_support()
import bodies
from swfabc import SwfAbc
from editor import body_bytes
LABELS = ('EventItemExchangeShopScene/buttonClicked', 'ShopProductBuyDialog/beforePrepare')

def reject_helper(abc):
    if any(abc.s(i) == 'cnDegreeShopId' for i in range(len(abc.strings))):
        raise ValueError('Historical cnDegreeShopId helper/pool must not enter the no-degree base')

def verify(path):
    base = SwfAbc(input_path('r11')).abc; candidate = SwfAbc(path).abc
    reject_helper(candidate); rows=[]
    for label in LABELS:
        old = base.bodies[bodies.resolve(base,label)]
        new = candidate.bodies[bodies.resolve(candidate,label)]
        if body_bytes(old) != body_bytes(new) or base.methods[old[0]] != candidate.methods[new[0]]:
            raise ValueError('Native R11 complete shop method differs: '+label)
        rows.append({'label':label,'method_info':new[0],
                     'code_sha256':hashlib.sha256(new[5]).hexdigest(),
                     'full_body_exact_r11':True,'method_info_exact_r11':True})
    return {'methods':rows,'cnDegreeShopIdPresent':False}

def restore_native_shops(editor):
    """Only restore these two bodies; require pre-existing native MID/signature layout.
    Historical helper removal is intentionally not guessed: compose a no-degree core.
    """
    base=SwfAbc(input_path('r11')).abc; reject_helper(editor.abc)
    for label in LABELS:
        old=base.bodies[bodies.resolve(base,label)]
        index=bodies.resolve(editor.abc,label); current=editor.abc.bodies[index]
        if current[0]!=old[0] or editor.abc.methods[current[0]]!=base.methods[old[0]]:
            raise ValueError('R11 shop MethodInfo layout differs: '+label)
        editor.abc.bodies[index]=copy.deepcopy(old)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--swf',required=True)
    ap.add_argument('--sha256',required=True);ap.add_argument('--output',required=True);args=ap.parse_args()
    raw=Path(args.swf).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=args.sha256:raise ValueError('Candidate SHA mismatch')
    result=verify(args.swf);out=require_output(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
