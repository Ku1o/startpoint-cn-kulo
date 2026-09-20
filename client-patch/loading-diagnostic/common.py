import hashlib, importlib.util, json, os, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
WORK=Path(os.environ.get('STARPOINT_LOADING_DIAG_WORK','F:/codex/work/loading-diagnostic-20260913')).resolve()
BASE_SHA='35e0e7c777798594d68c9bcd74c507c6f0b7d065453e0425c301258c6bc38ac6'
SWF_SHA='e60cc4a82e3b305257040dedc54d180794234e2c2d4d3cef68a105b9f8405927'
BASE_UUID='dda17e46-ff9f-40bd-8bff-9e1acb542738'
BUILD='CN-LOAD-20260913-r6'
REVISION=BUILD.rsplit('-',1)[1]

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj

b=module('loading_native_build',HERE.parent/'startup-cache/build.py')
s=module('loading_swf_model',HERE.parent/'startup-cache/build_swf.py')
native=module('loading_native_verify',HERE.parent/'startup-cache/verify_native.py')
def sha(data):return hashlib.sha256(data).hexdigest()
def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def baseline():
    checker=module('loading_baseline_check',HERE.parent/'verify_android_baseline.py')
    identity=checker.verify('public')
    assert identity['apk_sha256']==BASE_SHA and identity['swf_sha256']==SWF_SHA
    assert identity['uniqueappversionid']==BASE_UUID
    return identity
