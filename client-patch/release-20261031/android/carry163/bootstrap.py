from pathlib import Path
import sys,hashlib
ROOT=Path(__file__).resolve().parent
ANDROID=next(p for p in ROOT.parents if p.name=='android')
sys.dont_write_bytecode=True
sys.path.insert(0,str(ANDROID/'test-support'))
from input_config import configure_support
configure_support()
def sha(raw):return hashlib.sha256(raw).hexdigest()
