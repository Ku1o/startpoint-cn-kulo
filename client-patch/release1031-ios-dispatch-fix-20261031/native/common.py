"""Pinned iOS dispatch-repair inputs and bounded-stage helpers."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
from pathlib import Path
import hashlib, importlib.util, json, sys
sys.dont_write_bytecode = True
TASK = Path(str(fc.client() / 'revision-ios-dispatch-fix-20261031'))
CLIENT = TASK.parent
SOURCE = Path(str(fc.REPO / 'client-patch'))
LIBRARIES = Path(str(fc.private('libraries')))
SDK = Path(str(fc.private('sdk')))
DEPENDENCIES = fc.private('dependencies')
BACKGROUND = Path(str(fc.tool('support/process/run_background.py')))
STUBS = fc.private('runtime_stubs')
PREVIOUS = CLIENT/'revision-settings/ios'
REPAIRS = CLIENT/'revision-ios-acceptance-repairs'
PUBLIC = CLIENT/'revision-public-admission-20261031/ios/build01'
ABC_SHA = '257b0b0a3e3b448ede2407b4b01d22584a5de6b988bbe81d2bc4df112c7de9d3'
NATIVE_SHA = '96178c8c96a872cdca0ab61706f15f9130168041431d1583114bf0ab62bb3d37'
SWF_SHA = '080950b5b4ccd96dc92693a8c06f56a2da83a7ca2fff58269875435784c0037b'
IPA = Path(str(fc.private('followup_public_ipa')))
IPA_SHA = 'f4e08c4e5a65de080ca323eaaa35c6a0af90280bf942edcfab050d73f84d3bd8'

def require(ok, message):
    if not ok: raise ValueError(message)

def sha(raw): return hashlib.sha256(raw).hexdigest()

def read(path, maximum=20*1024**2):
    path = Path(path)
    require(path.is_file() and path.stat().st_size <= maximum, 'JSON input path/size refused')
    return json.loads(path.read_text('utf-8-sig'))

def fresh(path):
    path = Path(path).resolve()
    require(path.is_relative_to(TASK.resolve()) and path != TASK.resolve(), 'Output outside repair task')
    require(not path.exists(), 'Fresh output required: '+str(path))
    return path

def dump(path, document):
    path = fresh(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2, default=str)
        stream.write('\n')

def module(name, path):
    spec=importlib.util.spec_from_file_location(name, path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def framework():
    sys.path[:0]=[str(LIBRARIES),str(SOURCE/'lens0907-0908'),str(SOURCE/'pr43-ios'),
                  str(SOURCE/'ios-r11-port'),str(fc.tool('repairs/scripts'))]
    import build_swf as p
    return p

def bounded_job(max_seconds=180):
    guard=module('dispatch_job_guard', fc.tool('support/process/job_guard.py'))
    return guard.require_bounded_job(max_seconds)

def baseline_reports():
    """Rebind immutable linkage evidence after the proven equal-width rotation."""
    directory=TASK/'baseline'
    if directory.exists():
        return directory/'link-report.json', directory/'package.json'
    previous=read(REPAIRS/'runs/link03/link-report.json')
    public=read(CLIENT/'revision-public-admission-20261031/RESULT.json')['ios']
    require(public['nativeSha256']==NATIVE_SHA and public['fullAbcSha256']==ABC_SHA and
            public['sha256']==IPA_SHA, 'Current public receipt drifted')
    full=(PUBLIC/'full.abc').read_bytes()
    require(sha(full)==ABC_SHA, 'Current public full ABC changed')
    full_sha1=hashlib.sha1(full).hexdigest()
    previous.update(native_file=str(PUBLIC/'worldflipper'),swf_file=str(PUBLIC/'main.swf'),
        full_abc_file=str(PUBLIC/'full.abc'),native_sha256=NATIVE_SHA,swf_sha256=SWF_SHA,
        full_abc_sha256=ABC_SHA,full_abc_sha1=full_sha1,total_methods=101843,
        previous_rotation_receipt=str(CLIENT/'revision-public-admission-20261031/RESULT.json'),
        status='linked_native_not_executed',unwind_finalized=True)
    # Historical runtime bytes precede the equal-width admission rotation.
    # The linker reads the current runtime directly from the pinned native.
    previous.pop('runtime_abc_sha256',None)
    previous.pop('runtime_abc_file',None)
    prior=read(PREVIOUS/'linked01/link-report.json')
    methods=[r['method'] for r in prior['functions']+previous['functions']]
    require(len(methods)==len(set(methods))==356, 'Cumulative function list identity changed')
    previous['functions']=prior['functions']+previous['functions']
    source=previous['source_ipa']
    source.update(ipa=str(IPA),ipa_sha256=IPA_SHA,size_bytes=public['bytes'],
        native_sha256=NATIVE_SHA,swf_sha256=SWF_SHA,full_abc=str(PUBLIC/'full.abc'),
        full_abc_sha256=ABC_SHA,full_abc_sha1=full_sha1,aot_method_count=101843,
        admission_id='ios-184-r1031-final-public-20261031',
        build_id='ios-184-r1031-final-public-20261031')
    package=dict(status='unsigned_offline_candidate',ipa=str(IPA),ipa_sha256=IPA_SHA,
        native_sha256=NATIVE_SHA,swf_sha256=SWF_SHA,size_bytes=public['bytes'],
        total_methods=101843,full_abc_sha256=ABC_SHA,full_abc_sha1=full_sha1,
        reused_rotation_evidence=True)
    directory.mkdir()
    dump(directory/'link-report.json', previous)
    dump(directory/'package.json', package)
    return directory/'link-report.json', directory/'package.json'
