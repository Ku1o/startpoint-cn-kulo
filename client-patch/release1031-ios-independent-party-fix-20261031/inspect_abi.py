"""Small exact-function disassembly and original ABC call contracts."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
import types
import common as c
def main():
    c.bounded_job();p=c.framework();a=p.abcfmt.ABC(c.ABC.read_bytes())
    for mid in c.TARGETS:
        m=a.methods[mid];print(mid,'return',a.mn_name(m[0]),'args',[a.mn_name(x) for x in m[1]],'flags',m[3],'defaults',m[4])
    for inst in a.instances:
        if a.mn_name(inst[0]) not in ('pinball.scene.loading::LoadingTask','pinball.dialog.processing::ServiceLauncher'):continue
        print('CLASS',a.mn_name(inst[0]),'BASE',a.mn_name(inst[1]),'FIELDS',[(a.mn_name(t.name),a.mn_name(t.data[2])) for t in inst[6] if t.kind in (0,6)])
    from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM
    linked=c.read(c.TASK/'linked01/link-report.json');md=Cs(CS_ARCH_ARM64,CS_MODE_ARM)
    with open(linked['native_file'],'rb') as f:
        for row in linked['functions']:
            f.seek(row['file_offset']);raw=f.read(row['size']);print('METHOD',row['method'],hex(row['address']))
            for i in md.disasm(raw,row['address']):print(hex(i.address-row['address']),i.mnemonic,i.op_str)
            print('CALLS',[(hex(r['offset']),r['symbol'],hex(r['target'])) for r in linked['relocations'] if r['method']==row['method'] and r['type']==2])
if __name__=='__main__':main()
