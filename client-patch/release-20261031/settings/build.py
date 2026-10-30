"""Compose only adopted settings UI -> conditional render on a pinned no-degree core.
All heavy execution must run inside the release's external bounded Job wrapper.
"""
from pathlib import Path
import argparse, json, subprocess, sys
from input_config import ROOT, input_path, input_sha, require_output

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    out=require_output(args.out);out.mkdir(parents=True)
    commands=[
        [sys.executable,'-B',str(ROOT/'ui/build.py'),'--out',str(out/'ui')],
        [sys.executable,'-B',str(ROOT/'render/build.py'),'--input',str(out/'ui/core-ui.partial.swf'),
         '--input-sha256',None,'--output',str(out/'settings.swf')]]
    for index,command in enumerate(commands):
        if index:
            previous=json.loads((out/'ui/report.json').read_text(encoding='utf-8'))
            command[command.index(None)]=previous['output_sha256']
        result=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=120)
        (out/('step-'+str(index)+'.log')).write_bytes(result.stdout+result.stderr)
        if result.returncode:raise RuntimeError('Settings composition failed at step '+str(index))
    # Re-open each output: no historical degree helper or special shop body allowed.
    from degree_retraction import verify
    final=json.loads((out/'settings.json').read_text(encoding='utf-8'))
    result={'status':'static_composed_not_AIR_or_device_acceptance',
            'corecarry_sha256':input_sha('corecarry'),
            'ui_sha256':previous['output_sha256'],'output_sha256':final['output_sha256'],
            'degree_retraction':verify(out/'settings.swf'),
            'order':['core+carry without degree or old195','UI','revision3 conditional195'],
            'output':str(out/'settings.swf')}
    (out/'composition.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
