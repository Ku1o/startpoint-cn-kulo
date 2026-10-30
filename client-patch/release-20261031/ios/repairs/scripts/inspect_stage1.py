"""DRAFT, NOT EXECUTED: bounded read-only inspection of the 17 repair QNames.

Reads one frozen full ABC and sparse native ranges, never the IPA/SWF. Imports
only the standalone ABC/opcode readers, never a historical preparation main.
Writes a fresh report directory under this task; does not prepare native code.
"""
from __future__ import annotations
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
import argparse, bisect, ctypes, hashlib, importlib.util, json, os, struct, sys, time
from pathlib import Path
sys.dont_write_bytecode = True

TASK = cfg.work('repairs')
CLIENT = Path(cfg.path('input_root'))
BASE_FULL = Path(cfg.path('settings_full_abc'))
BASE_NATIVE = Path(cfg.path('settings_native'))
PREVIOUS_LINK = Path(cfg.path('settings_link_report'))
PREVIOUS_PACKAGE = Path(cfg.path('settings_package_report'))
PARSER = Path(cfg.repo('client-patch/lens0907-0908/vendor'))
INFO = 104549248
ABC_SHA = '672757b40180eb960dde989b8f659b37cc32229a03a5c903b0bbdc3be6bc814e'
NATIVE_SHA = '7d803626d4cd5debc00cb17b633bbfeec3a9d04ef6b7beed4f068d2e17b6215f'
IPA_SHA = 'b38629f65e8506720cc27200b4c87fd51613b78593899c0248a46ffc2e3a9d24'
TARGET_SHA = 'f8e60c4461eefd16ecc0581625d5e44c9983ae0d514d2901714ea187c185660f'
LEDGER_OWNER = 'pinball.scene.battle.battle.ability::InstantAbility'
LEDGER = 'wfxHpLossLedger'
MAX_CLOSURES = 128
MAX_DECODED_INSTRUCTIONS = 100000
MN_OPS = {0x04,0x05,0x45,0x46,0x4a,0x4c,0x4e,0x4f,0x59,0x5b,0x5c,0x5d,0x5e,
          0x5f,0x60,0x61,0x66,0x68,0x6a,0x80,0x86,0xb2}
START = time.monotonic()

def require(ok, message):
    if not ok:
        raise ValueError(message)

def deadline():
    require(time.monotonic() - START < 58, 'Stage1 internal 58-second deadline')

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def same_path(left, right):
    return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(str(Path(right).resolve()))

def limited_read(path, maximum):
    path = Path(path)
    require(path.is_file() and 0 < path.stat().st_size <= maximum, f'Input size refused: {path}')
    deadline()
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    require(len(raw) <= maximum, 'Input grew beyond read bound')
    return raw

def read_json(path, maximum=12*1024**2):
    return json.loads(limited_read(path, maximum).decode('utf-8-sig'))

def require_bounded_job(wall_limit_seconds=60):
    """Refuse direct Python invocation outside the approved Windows Job tree."""
    require(os.name == 'nt', 'Windows bounded launcher required')
    require(0 < wall_limit_seconds <= 180, 'Task wall budget outside authorization')
    from ctypes import wintypes as w
    class Basic(ctypes.Structure):
        _fields_ = [('p',ctypes.c_int64),('j',ctypes.c_int64),('flags',w.DWORD),
                    ('minimum',ctypes.c_size_t),('maximum',ctypes.c_size_t),
                    ('active',w.DWORD),('affinity',ctypes.c_size_t),
                    ('priority',w.DWORD),('scheduling',w.DWORD)]
    class Io(ctypes.Structure):
        _fields_ = [(n,ctypes.c_uint64) for n in ('a','b','c','d','e','f')]
    class Extended(ctypes.Structure):
        _fields_ = [('basic',Basic),('io',Io),('process',ctypes.c_size_t),
                    ('job',ctypes.c_size_t),('peakProcess',ctypes.c_size_t),
                    ('peakJob',ctypes.c_size_t)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.IsProcessInJob.argtypes = [w.HANDLE,w.HANDLE,ctypes.POINTER(w.BOOL)]
    kernel.IsProcessInJob.restype = w.BOOL
    kernel.QueryInformationJobObject.argtypes = [w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.c_void_p]
    kernel.QueryInformationJobObject.restype = w.BOOL
    inside = w.BOOL()
    require(kernel.IsProcessInJob(kernel.GetCurrentProcess(),None,ctypes.byref(inside)) and inside.value,
            'Not running inside a Windows Job')
    current = Extended()
    require(kernel.QueryInformationJobObject(None,9,ctypes.byref(current),ctypes.sizeof(current),None),
            'Cannot inspect current Job; no unrestricted fallback')
    require(current.basic.flags & 0x2300 == 0x2300, 'Missing kill-on-close and process/job memory hard limits')
    require(not current.basic.flags & 0x1800, 'Breakaway/silent-breakaway Job is not permitted')
    require(0 < current.job <= 1536*1024**2 and 0 < current.process <= 1536*1024**2,
            'Current Job memory limit is outside this task authorization')
    return dict(jobMemoryBytes=current.job, processMemoryBytes=current.process,
                jobLimitFlags=current.basic.flags, launcherWallLimitRequiredSeconds=wall_limit_seconds,
                wallLimitEvidence='external run_bounded receipt; memory Job query does not establish wall timeout')

class SparseNative:
    """Bound total native reads, including load commands and function starts."""
    def __init__(self, path):
        self.path = Path(path)
        self.size = self.path.stat().st_size
        self.stream = self.path.open('rb')
        self.total = 0
        self.reads = []
        head = self.read(0,32,'Mach-O header')
        require(struct.unpack_from('<I',head)[0] == 0xfeedfacf, 'Expected little-endian arm64 Mach-O')
        require(struct.unpack_from('<I',head,4)[0] == 0x0100000c, 'Expected arm64')
        count, amount = struct.unpack_from('<II',head,16)
        require(0 < count <= 128 and 0 < amount <= 65536, 'Load-command bound')
        raw = self.read(32,amount,'load commands')
        self.segments = []
        commands = []
        at = 0
        for _ in range(count):
            kind, size = struct.unpack_from('<II',raw,at)
            require(size >= 8 and at+size <= len(raw), 'Load-command extent')
            row = raw[at:at+size]
            commands.append((kind,row))
            if kind == 0x19:
                vm, vs, off, fs = struct.unpack_from('<QQQQ',row,24)
                self.segments.append(dict(name=row[8:24].split(b'\0')[0].decode(), vm=vm, vs=vs, off=off, fs=fs))
            at += size
        require(at == amount, 'Load-command total differs')
        starts = [r for k,r in commands if k == 0x26]
        require(len(starts) == 1, 'One LC_FUNCTION_STARTS required')
        offset, size = struct.unpack_from('<II',starts[0],8)
        require(0 < size <= 512*1024, 'Function-start metadata bound')
        data = self.read(offset,size,'LC_FUNCTION_STARTS metadata')
        self.starts = []
        value = running = shift = 0
        for byte in data:
            value |= (byte & 127) << shift
            if byte & 128:
                shift += 7
                require(shift <= 63, 'Oversized function-start ULEB')
            else:
                if not value:
                    break
                running += value
                self.starts.append(0x100000000 + running)
                require(len(self.starts) <= 250000, 'Function-start count bound')
                value = shift = 0

    def read(self, offset, length, why):
        deadline()
        require(0 <= offset and 0 <= length <= 512*1024 and offset+length <= self.size, 'Sparse read extent')
        require(self.total + length <= 2*1024**2, 'Total native read cap 2MiB exceeded')
        self.stream.seek(offset)
        result = self.stream.read(length)
        require(len(result) == length, 'Short native read')
        self.total += length
        self.reads.append(dict(offset=offset, bytes=length, purpose=why))
        return result

    def offset(self, va, length=1):
        hits = [s['off']+va-s['vm'] for s in self.segments
                if s['vm'] <= va and va+length <= s['vm']+s['fs']]
        require(len(hits) == 1, f'Native address unmapped/ambiguous: {va:x}')
        return hits[0]

    def at(self, va, length, why):
        return self.read(self.offset(va,length),length,why)

    def function_span(self, va):
        index = bisect.bisect_right(self.starts,va)-1
        if index < 0 or index+1 >= len(self.starts):
            return None
        return dict(start=self.starts[index], end=self.starts[index+1], exactStart=self.starts[index] == va)

    def close(self):
        self.stream.close()

def namespace(abc, mn_index):
    row = abc.multinames[mn_index]
    if row[0] in (7,13):
        kind, text = abc.namespaces[row[1]]
        return dict(kind=kind, uri=abc.s(text), localName=abc.s(row[2]))
    return dict(multiname=list(row), text=abc.mn_name(mn_index))

def trait_record(abc, trait):
    return dict(name=abc.mn_name(trait.name), namespace=namespace(abc,trait.name),
                kind=trait.kind, attr=trait.attr, data=trait.data, metadata=trait.metadata)

def method_record(abc, mid):
    row = abc.methods[mid]
    return dict(raw=row, returns=abc.mn_name(row[0]), arguments=[abc.mn_name(x) for x in row[1]],
                flags=row[3], options=row[4], parameterNames=row[5])

def body_shape(abc, body, asm):
    if body is None:
        return dict(classification='no_ABC_body', nativeSemanticsRecovered=False)
    code = body[5]
    instructions = asm.decode(code)
    # Shape evidence only. A return-shaped body does not identify native logic.
    material = [i for i in instructions if i.op not in (0x02,0x09,0xef,0xf0,0xf1)]
    tiny = len(material) <= 6 and any(i.op in (0x47,0x48) for i in material)
    return dict(classification='tiny_return_shape_stub_suspected' if tiny else 'nontrivial_ABC_body',
                bodyHeader=body[:5], codeBytes=len(code), codeSha256=sha(code),
                instructions=len(instructions), exceptions=body[6],
                activationTraits=[trait_record(abc,t) for t in body[7]],
                nativeSemanticsRecovered=False,
                warning='ABC shape classification is not proof of equivalence to native implementation')

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--full-abc',type=Path,required=True)
    ap.add_argument('--previous-link',type=Path,required=True)
    ap.add_argument('--previous-package',type=Path,required=True)
    ap.add_argument('--targets',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args = ap.parse_args()
    output = args.output.resolve()
    runs = (TASK/'runs').resolve()
    require(runs.is_relative_to(TASK.resolve()) and output.is_relative_to(runs) and output != runs,
            'Output must be a new child of this task/runs')
    require(not output.exists(), 'Existing output refused')
    require(same_path(args.full_abc,BASE_FULL), 'Unexpected frozen ABC path')
    require(same_path(args.previous_link,PREVIOUS_LINK), 'Unexpected previous-link path')
    require(same_path(args.previous_package,PREVIOUS_PACKAGE),
            'Unexpected previous-package path')
    job = require_bounded_job()
    target_raw = limited_read(args.targets,128*1024)
    require(sha(target_raw) == TARGET_SHA, 'Frozen17 target-plan identity changed')
    targets = json.loads(target_raw.decode('utf-8-sig'))
    require(len(targets['methods']) == targets['candidateBusinessMethods'] == 17, 'Business scope differs')
    linked = read_json(args.previous_link)
    package = read_json(args.previous_package,128*1024)
    require(linked['native_sha256'] == package['native_sha256'] == NATIVE_SHA, 'Previous native evidence differs')
    require(package['ipa_sha256'] == IPA_SHA and linked['full_abc_sha256'] == ABC_SHA, 'Previous carrier evidence differs')
    native_path = Path(linked['native_file'])
    require(same_path(native_path,BASE_NATIVE), 'Unexpected native source path')
    require(native_path.stat().st_size == 243796608, 'Frozen native size differs; do not rehash in Stage1')
    raw = limited_read(args.full_abc,8*1024**2)
    require(sha(raw) == ABC_SHA, 'Frozen full ABC differs')
    # Standalone parser only: no prepare/build/native-support module import.
    spec = importlib.util.spec_from_file_location('acceptance_readonly_asm',PARSER/'abcasm/asm.py')
    asm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(asm)
    abcfmt = asm.load_abc_module('abcfmt')
    abc = abcfmt.ABC(raw)
    require(len(abc.methods) == linked['total_methods'] == 101833, 'Current MethodInfo count differs')
    by_mid = {b[0]:b for b in abc.bodies}
    require(len(by_mid) == len(abc.bodies), 'Duplicate method body IDs')
    class_ids = {}
    for ci,inst in enumerate(abc.instances):
        class_ids.setdefault(abc.mn_name(inst[0]),[]).append(ci)
    native = SparseNative(native_path)
    try:
        info = native.read(INFO,168,'AOTInfo current pointers')
        require(info[:20].hex() == linked['full_abc_sha1'], 'Actual AOTInfo digest does not match previous evidence')
        active, count, flags, activation = (struct.unpack_from('<Q',info,x)[0] for x in (48,56,64,88))
        require(count == len(abc.methods), 'Actual native AOT method count differs')
        protected = {}
        # Current equipment active entry gathers first; its legacy entry starts
        # at the preserved five wrapper. They intentionally are not identical.
        for protected_mid, expected_entry, expected_legacy in (
                (18392,linked['platform_equipment']['wrapper'],linked['platform_equipment']['five_in_one_wrapper']),
                (66181,linked['platform_draw']['retained_active_table_entry'],linked['platform_draw']['retained_active_table_entry'])):
            labels = []
            for ci,inst in enumerate(abc.instances):
                owner = abc.mn_name(inst[0])
                for static,traits in ((False,inst[6]),(True,abc.classes[ci][1])):
                    for trait in traits:
                        if trait.kind in (1,2,3) and trait.data[2] == protected_mid:
                            labels.append(owner+('$' if static else '')+'/'+abc.mn_name(trait.name)+'|'+str(trait.kind))
            entry = struct.unpack('<Q',native.at(active+protected_mid*8,8,'protected wrapper active pointer'))[0]
            legacy = struct.unpack('<Q',native.read(0x62c0780+protected_mid*8,8,'protected wrapper legacy pointer'))[0]
            require(entry == expected_entry and legacy == expected_legacy,
                    f'Protected {protected_mid} dispatch differs: active={entry:x}, legacy={legacy:x}, expected={expected_entry:x}/{expected_legacy:x}')
            protected[str(protected_mid)] = dict(actualMethodInfo=protected_mid,labels=labels,
                activeEntry=entry,legacyEntry=legacy,methodInfo=method_record(abc,protected_mid),
                abcBody=body_shape(abc,by_mid.get(protected_mid),asm),
                wrapperEntryPrefixHex=native.at(entry,96,'protected wrapper entry prefix').hex())
        records = []
        layouts = {}
        roots = set()
        for target in targets['methods']:
            deadline()
            owner, name, static = target['owner'], target['name'], target['static']
            hits = class_ids.get(owner,[])
            require(len(hits) == 1, f'Owner absent/ambiguous: {owner}')
            ci, = hits
            inst, cls = abc.instances[ci], abc.classes[ci]
            if owner not in layouts:
                script = [(i,row[0]) for i,row in enumerate(abc.scripts)
                          if any(t.kind == 4 and t.data[2] == ci for t in row[1])]
                layouts[owner] = dict(classIndex=ci, instancePrefix=inst[:6], classCinit=cls[0],
                    owningScripts=[dict(scriptIndex=i,initializer=mid) for i,mid in script],
                    instanceSlots=[trait_record(abc,t) for t in inst[6] if t.kind in (0,6)],
                    staticSlots=[trait_record(abc,t) for t in cls[1] if t.kind in (0,6)],
                    instanceTraits=[trait_record(abc,t) for t in inst[6]],
                    staticTraits=[trait_record(abc,t) for t in cls[1]],
                    rawNativeFieldOffsetsVerified=False)
            traits = cls[1] if static else inst[6]
            found = [t for t in traits if t.kind in (1,2,3) and namespace(abc,t.name).get('localName') == name]
            record = dict(owner=owner,name=name,static=static,group=target['group'],candidateAdded=target.get('added',False))
            if not found:
                record.update(status='absent_expected_new_candidate' if target.get('added') else 'missing_old_target_blocked',
                              actualMethodInfo=None)
                records.append(record)
                continue
            require(len(found) == 1, f'Method name ambiguous, namespace review needed: {owner}/{name}')
            trait, = found
            mid = trait.data[2]
            roots.add(mid)
            pointer = struct.unpack('<Q',native.at(active+mid*8,8,'selected active MethodInfo pointer'))[0]
            flag_bytes = native.at(flags+mid*4,4,'selected native flags')
            activation_bytes = native.at(activation+mid*16,16,'selected activation descriptor')
            entry = native.at(pointer,96,'selected native entry prefix')
            initializer_id = struct.unpack_from('<i',activation_bytes)[0]
            require(initializer_id == -1 or 0 <= initializer_id < count, 'Native activation initializer shape differs')
            record.update(status='existing_QName_inspected_not_semantically_verified',actualMethodInfo=mid,
                trait=trait_record(abc,trait), methodInfo=method_record(abc,mid),
                abcBody=body_shape(abc,by_mid.get(mid),asm),nativeEntry=pointer,
                nativeEntryFileOffset=native.offset(pointer,96),nativeEntryPrefixHex=entry.hex(),
                nativeContainingFunction=native.function_span(pointer),nativeFlagsHex=flag_bytes.hex(),
                nativeActivationHex=activation_bytes.hex(),nativeActivationInitializer=initializer_id,
                nativeActivationInitHandler=struct.unpack_from('<Q',activation_bytes,8)[0],
                nativeMethodEnvIdentityVerified=False,
                otherActiveEntryAliasesProvenAbsent=False,
                protectedDispatchOverlap=[r['actualMethodInfo'] for r in protected.values()
                                          if mid == r['actualMethodInfo'] or pointer == r['activeEntry']])
            records.append(record)
        ledger_ci, = class_ids[LEDGER_OWNER]
        ledger_inst, ledger_class = abc.instances[ledger_ci], abc.classes[ledger_ci]
        ledger_traits = [trait_record(abc,t) for t in ledger_class[1]
                         if namespace(abc,t.name).get('localName') == LEDGER]
        ledger_roots = {ledger_class[0]}
        ledger_scripts = [(i,mid) for i,(mid,traits) in enumerate(abc.scripts)
                          if any(t.kind == 4 and t.data[2] == ledger_ci for t in traits)]
        ledger_roots.update(mid for _,mid in ledger_scripts)
        pending = list(sorted(roots|ledger_roots))
        visited = set()
        scans = []
        instruction_total = 0
        while pending:
            deadline()
            mid = pending.pop()
            if mid in visited:
                continue
            require(len(visited) < MAX_CLOSURES, 'Selected current closure/initializer scan bound exceeded')
            visited.add(mid)
            if mid not in by_mid:
                scans.append(dict(method=mid,status='no_ABC_body'))
                continue
            instructions = asm.decode(by_mid[mid][5])
            instruction_total += len(instructions)
            require(instruction_total <= MAX_DECODED_INSTRUCTIONS, 'Selected decoded instruction bound exceeded')
            closures, direct, ledger_accesses, hard_slots, class_references, dispatch_review = [], [], [], [], [], []
            activation_methods=[]
            for trait in by_mid[mid][7]:
                if trait.data[0] in ('method','function'):
                    activation_methods.append(trait.data[2]);pending.append(trait.data[2])
            for at,ins in enumerate(instructions):
                if ins.op == 0x40:
                    require(0 <= ins.args[0] < len(abc.methods), 'newfunction target outside ABC')
                    closures.append(dict(instruction=at,method=ins.args[0]))
                    pending.append(ins.args[0])
                elif ins.op == 0x44:
                    direct.append(dict(instruction=at,method=ins.args[0],argumentCount=ins.args[1]))
                elif ins.op == 0x58:
                    class_references.append(dict(instruction=at,classIndex=ins.args[0]))
                if ins.op in (0x43,0x4b,0x4d):
                    dispatch_review.append(dict(instruction=at,opcode=ins.op,arguments=ins.args,
                                                reason='raw dispatch opcode requires explicit importer/ABI review'))
                if ins.op in MN_OPS and ins.args and abc.mn_name(ins.args[0]).split('::')[-1] == LEDGER:
                    ledger_accesses.append(dict(instruction=at,operation=ins.name,multiname=ins.args[0],
                                                namespace=namespace(abc,ins.args[0])))
                if ins.op == 0x2c and abc.s(ins.args[0]) == LEDGER:
                    ledger_accesses.append(dict(instruction=at,operation='reflection_string_requires_review'))
                if ins.op in (0x6c,0x6d,0x6e,0x6f):
                    hard_slots.append(dict(instruction=at,operation=ins.name,slot=ins.args[0],
                                           ledgerOwnershipProven=False))
            scans.append(dict(method=mid,instructions=len(instructions),newfunction=closures,
                              callstatic=direct,newclass=class_references,ledgerAccesses=ledger_accesses,
                              hardSlotAccesses=hard_slots,dispatchReview=dispatch_review,
                              activationMethodReferences=activation_methods,
                              source='current frozen iOS only'))
        report = dict(status='readonly_current_ios_17_QName_inspection_source_closures_and_ABI_review_pending',
            businessCandidates=17,actualAotTargetCount=None,
            previousIdentityEvidenceReused=dict(ipaSha256=IPA_SHA,nativeSha256=NATIVE_SHA,
                fullAbcSha256=ABC_SHA,ipaOpened=False,nativeRehashed=False,
                actualNativeAotInfoDigestRead=True,nativeSize=native.size),
            targetsPlanSha256=sha(target_raw),fullAbcBytesRead=len(raw),currentMethods=count,
            targets=records,ownerLayouts=layouts,
            protectedDispatch=protected,
            currentBodyClosureScan=dict(roots=sorted(roots),ledgerInitializerRoots=sorted(ledger_roots),
                visitedMethods=sorted(visited),instructions=instruction_total,methods=scans,
                finalDonorClosureSetProven=False,callstaticReferencesFollowedRecursively=False),
            ledger=dict(owner=LEDGER_OWNER,currentTraits=ledger_traits,declaredIncomingType='*',
                incomingTypeSentinel=0,incomingLazyValue='Dictionary(true)',
                sourceLedgerAccessAuditPending=True,wildcardAtomAbiVerified=False,
                newSidecarLifecycleSetPending=True,
                proposedNewSidecar='cn.release::AcceptanceRepairsState20261031',
                proposedNewSidecarExists=bool(class_ids.get('cn.release::AcceptanceRepairsState20261031'))),
            nativeSparseReads=dict(bytesRead=native.total,maximumBytes=2*1024**2,reads=native.reads),
            jobAtEntry=job,semanticStubEquivalenceProven=False,
            oldSlotsModified=False,oldPlatformProductsModified=False,nativeExecuted=False,
            stage2Ready=False,
            blockers=['review actual MethodInfo/namespace and unexpected target presence/absence',
                      'bind final source real bodies/closure/initializers; current native entry is not semantic proof',
                      'review old native Number/int/Atom/MethodEnv/layout ABI and stub replacement semantics',
                      'implement unique new wildcard sidecar/accessors and full lifecycle AOT contract'])
        deadline()
        output.mkdir(parents=True,exist_ok=False)
        with (output/'report.json').open('x',encoding='utf-8') as stream:
            json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False)
            stream.write('\n')
        print(json.dumps(dict(status=report['status'],output=str(output/'report.json'),
                              existing=sum(r['actualMethodInfo'] is not None for r in records),
                              nativeReadBytes=native.total,actualAotTargetCount=None)))
    finally:
        native.close()

if __name__ == '__main__':
    main()
