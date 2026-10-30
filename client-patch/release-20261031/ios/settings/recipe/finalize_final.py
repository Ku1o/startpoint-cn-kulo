"""Finalize all actual compiled functions; accept only one of two strict switch proofs."""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
cfg.bind_tools()
from pathlib import Path
import argparse,json,sys
sys.dont_write_bytecode=True
from types import SimpleNamespace
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
SOURCE=Path(cfg.repo('client-patch'))
sys.path[:0]=[cfg.path('libraries'),str(SOURCE/'ios-r11-port'),str(HERE.parent)]
import link_stage,finalize_delta,switch_adapter
original=finalize_delta.verify_switch_tables
def strict_switch(*args,**kwargs):
 try:return original(*args,**kwargs)
 except ValueError as first:
  try:return switch_adapter.verify_switch_tables(*args,**kwargs)
  except ValueError as second:raise ValueError(f'{args[0]} Both independent strict compiler switch recognizers rejected: original={first}; spilled={second}') from second
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
 with patch.object(finalize_delta,'verify_switch_tables',strict_switch):report=link_stage.finalize(SimpleNamespace(output=args.output))
 print(json.dumps(dict(status=report['status'],native_sha256=report['native_sha256'],unwind_finalized=report['unwind_finalized'])))
