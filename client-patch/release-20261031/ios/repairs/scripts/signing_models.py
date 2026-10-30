"""Exact six signing-layout models with file-backed, bounded-copy storage.

Only allocation changes from native_support.verify_signing_models. Every mode,
synthetic signature byte, header update, rebase and full loader-range comparison
remains. No existing native/package is written. Temporary model stays in TASK.
"""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
import hashlib,mmap,struct,tempfile
from pathlib import Path
import repair_common as c

def verify_signing_models(native):
    import native_support as support
    from macho_signing_layout import assert_signable_layout,ldid_code_limit,linkedit_ranges,signature_range
    link=support.backend()
    assert_signable_layout(native)
    command,signature,_=signature_range(native)
    ranges=linkedit_ranges(native)
    expected=link.read_rebase(native)['entries']
    modes=(('signature',signature),('ldid',ldid_code_limit(native)))
    # assert_signable_layout already requires this equality. Keep both modes
    # and all three sizes; reuse only the immutable source-prefix backing file.
    c.require(all(limit==signature for _,limit in modes),'Signing limits differ; cannot reuse backing prefix')
    scratch=c.TASK/'scratch/signing-models';scratch.mkdir(parents=True,exist_ok=True)
    checked=[];chunk_size=1024*1024
    with tempfile.TemporaryFile(dir=scratch,prefix='model-',suffix='.native') as backing:
        for at in range(0,signature,chunk_size):
            chunk=memoryview(native)[at:min(signature,at+chunk_size)]
            c.require(backing.write(chunk)==len(chunk),'Short synthetic model prefix write')
            del chunk
        backing.flush()
        for mode,limit in modes:
            for size in (0x80000,0x200000,0x400000):
                backing.truncate(limit+size);backing.flush()
                with mmap.mmap(backing.fileno(),limit+size,access=mmap.ACCESS_WRITE) as result:
                    struct.pack_into('>III',result,limit,0xfade0cc0,size,0)
                    for at in range(limit+12,limit+size,chunk_size):
                        stop=min(limit+size,at+chunk_size);result[at:stop]=b'\xa5'*(stop-at)
                    struct.pack_into('<II',result,command+8,limit,size)
                    tail=link.segments(result)[-1];length=len(result)-tail['off']
                    struct.pack_into('<Q',result,tail['command']+48,length)
                    struct.pack_into('<Q',result,tail['command']+32,link.aot.align(length,0x4000))
                    assert_signable_layout(result)
                    c.require(link.read_rebase(result)['entries']==expected,'Synthetic model rebases differ')
                    for row in ranges:
                        begin,end=row['offset'],row['offset']+row['size']
                        for at in range(begin,end,chunk_size):
                            stop=min(end,at+chunk_size)
                            c.require(result[at:stop]==native[at:stop],f'{mode}/{size}/{row["name"]} full loader bytes differ')
                    checked.append(dict(mode=mode,signature_size=size,loader_metadata_preserved=True,
                        allocation='task-local file-backed mmap; source prefix copied once in <=1MiB chunks',
                        all_loader_range_bytes_compared=True,rebase_entries_equal=True,
                        adapter_sha256=c.sha(Path(__file__).read_bytes())))
    return checked
