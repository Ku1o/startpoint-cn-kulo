"""Android private roles, repository tools and external scratch outputs."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parent
ANDROID=ROOT.parent
RELEASE=ANDROID.parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(RELEASE))
import release_config as _r

def configuration():return _r.configuration()
def repo_path(relative=''):return _r.repo_path(relative)
def work_path(relative=''):return _r.work_path('android/'+relative)
def sha(raw):
    import hashlib
    return hashlib.sha256(raw).hexdigest()
def input_sha(role):return configuration()['android']['inputs'][role]['sha256'].lower()
def input_path(role):
    digest=input_sha(role)
    pins=json.loads((ROOT/'input-hashes.json').read_text())
    if role in pins and digest!=pins[role]:raise ValueError('Adopted input identity differs: '+role)
    return _r.require_sha(_r.input_path('android.inputs.'+role+'.path'),digest)
def runtime():
    value=json.loads(input_path('air_config').read_text(encoding='utf-8-sig'))
    for key in ('sdk','java'):
        if not Path(value[key]).is_absolute():raise ValueError('air_config.'+key+' must be absolute')
    return value

def require_output(path):
    path=Path(path).resolve()
    if not path.is_relative_to(work_path()) or path.exists():raise ValueError('Fresh work_dir/android output required')
    return path

def configure_support():
    if not __debug__:raise RuntimeError('Do not use Python -O; proof assertions are required')
    settings=RELEASE/'settings'
    support=repo_path('client-patch/pr43-port/support')
    pins=json.loads((settings/'contracts/repository-support.json').read_text())
    for name,digest in pins.items():_r.require_sha(support/name,digest)
    sys.path[:0]=[str(ROOT),str(settings/'support'),str(support)]

def helper_path(kind):
    name={'abc':'StageCarryState.abc','swc':'StageCarryState.swc'}[kind]
    built=work_path('carry163/helper-build')/name
    digest=json.loads((ROOT/'input-hashes.json').read_text())['carry_helper_'+kind]
    if not built.is_file():return input_path('carry_helper_'+kind)
    if kind=='abc':return _r.require_sha(built,digest)
    # SWC ZIP timestamps can differ after a clean compile. Validate its exact
    # executable ABC, not an unrelated historical ZIP timestamp/container hash.
    import zipfile,zlib
    from swfabc import swftags
    with zipfile.ZipFile(built) as archive:raw=archive.read('library.swf')
    body=zlib.decompress(raw[8:]) if raw[:3]==b'CWS' else raw[8:]
    units=[]
    for code,at,header,size in swftags.iter_tags(body):
        if code==82:
            payload=body[at+header:at+header+size];end=payload.index(b'\0',4)
            units.append(payload[end+1:])
    if len(units)!=1 or sha(units[0])!=json.loads((ROOT/'input-hashes.json').read_text())['carry_helper_abc']:
        raise ValueError('Fresh SWC adopted executable ABC differs')
    return built

def capability_module():
    # Existing patch tools use the generic module name bootstrap. Bind the
    # capability bootstrap only while loading that module, then restore caller.
    import importlib.util
    if 'port_capabilities' in sys.modules:return sys.modules['port_capabilities']
    directory=ANDROID/'capabilities'
    previous=sys.modules.get('bootstrap')
    spec=importlib.util.spec_from_file_location('bootstrap',directory/'bootstrap.py')
    capboot=importlib.util.module_from_spec(spec);sys.modules['bootstrap']=capboot
    try:
        spec.loader.exec_module(capboot)
        spec=importlib.util.spec_from_file_location('port_capabilities',directory/'port_capabilities.py')
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module
        spec.loader.exec_module(module)
        return module
    except BaseException:
        sys.modules.pop('port_capabilities',None)
        raise
    finally:
        if previous is None:sys.modules.pop('bootstrap',None)
        else:sys.modules['bootstrap']=previous

def tool_root():return ROOT
