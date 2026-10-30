"""Clean child process avoids shared bootstrap/asm module collisions."""
from pathlib import Path
import subprocess,sys,json
import bootstrap
ROOT=Path(__file__).resolve().parent
def apply_to_candidate(input_swf,expected_sha256,output_swf):
 p=subprocess.run([sys.executable,'-B',str(ROOT/'build.py'),'--input',str(input_swf),'--input-sha256',expected_sha256,'--output',str(output_swf)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
 return json.loads(Path(output_swf).with_suffix('.json').read_text(encoding='utf-8'))
