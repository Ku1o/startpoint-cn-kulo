"""Keep the existing native equipment-gather wrapper around the new resolver."""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
import struct
import platform_draw as d
MID=18392
WRAPPER=0x10d9d9030
FIVE_WRAPPER=0x106207aa0
TAIL=0x106207af4

def apply(baseline,actual,report,offset_of):
 fn,=[r for r in report['functions'] if r['method']==MID]
 d.require(not any(f':{MID}:' in r['symbol'] for r in report['relocations']),'direct resolver cross-call bypasses equipment wrapper')
 begin=offset_of(baseline,WRAPPER);tail=offset_of(baseline,TAIL)
 d.require(baseline[begin:begin+8]==bytes.fromhex('fd7bbba9e00701a9'),'original 0x50 wrapper frame required')
 d.require(d.branch_target(struct.unpack_from('<I',baseline,begin+24)[0],WRAPPER+24)==0x10d9d8000,'native equipment-gather BL changed')
 d.require(d.branch_target(struct.unpack_from('<I',baseline,begin+48)[0],WRAPPER+48)==FIVE_WRAPPER,'equipment-to-five-in-one tail changed')
 d.require(d.branch_target(struct.unpack_from('<I',baseline,tail)[0],TAIL)==0x104963a08,'five-in-one original stock resolver call changed')
 data=bytearray(actual);active=struct.unpack_from('<Q',baseline,d.INFO+48)[0];sites=[offset_of(baseline,active+MID*8),d.LEGACY_TABLE+MID*8]
 for off in sites:data[off:off+8]=baseline[off:off+8]
 hooks=[r for r in report['hooks'] if r['method']==MID]
 for r in hooks:data[r['offset']:r['offset']+4]=baseline[r['offset']:r['offset']+4]
 data[tail:tail+4]=d.branch(TAIL,fn['address'],True);report['hooks']=[r for r in report['hooks'] if r['method']!=MID];report['table_sites']=[i for i in report['table_sites'] if i not in sites]
 report['platform_equipment']=dict(method=MID,wrapper=WRAPPER,wrapper_file_offset=begin,wrapper_bytes=52,retained_native_equipment_gather=0x10d9d8000,five_in_one_wrapper=FIVE_WRAPPER,original_stock_resolver=0x104963a08,retained_five_in_one_postprocessing=True,tail=TAIL,tail_file_offset=tail,compiled_function=fn['address'],before_tail=baseline[tail:tail+4].hex(),after_tail=bytes(data[tail:tail+4]).hex(),retained_table_sites=sites,restored_default_hooks=hooks,native_executed=False)
 verify(baseline,data,report,offset_of);return bytes(data)

def verify(baseline,actual,report,offset_of):
 r=report['platform_equipment'];fn,=[f for f in report['functions'] if f['method']==MID];begin=offset_of(baseline,WRAPPER);tail=offset_of(baseline,TAIL)
 d.require(r['compiled_function']==fn['address'] and r['tail_file_offset']==tail,'equipment bridge target/offset mismatch')
 five=offset_of(baseline,FIVE_WRAPPER)
 d.require(actual[begin:begin+52]==baseline[begin:begin+52],'equipment wrapper arguments/gather/frame/tail differ')
 d.require(actual[five:tail]==baseline[five:tail] and actual[tail+4:five+208]==baseline[tail+4:five+208] and actual[tail:tail+4]==d.branch(TAIL,fn['address'],True),'five-in-one wrapper differs outside one re-bound stock resolver BL')
 active=struct.unpack_from('<Q',baseline,d.INFO+48)[0]
 for off in (offset_of(baseline,active+MID*8),d.LEGACY_TABLE+MID*8):d.require(actual[off:off+8]==baseline[off:off+8],'resolver entry no longer retains equipment wrapper')
 d.require(not any(h['method']==MID for h in report['hooks']),'ordinary resolver hook remains')
 return dict(status='original_equipment_gather_wrapper_retained',compiled_function=fn['address'],tail_file_offset=tail,native_executed=False)
