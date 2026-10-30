from pathlib import Path
import sys, hashlib
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from input_config import configure_support
configure_support()
def sha(raw): return hashlib.sha256(raw).hexdigest()
