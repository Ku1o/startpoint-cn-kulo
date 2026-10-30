"""Composition API with a fresh child process for generic assembler module names."""
from pathlib import Path
import json,subprocess,sys
import bootstrap
from input_config import work_path
ROOT=Path(__file__).resolve().parent

def apply_to_candidate(input_swf,expected_sha256,output_swf):
 output=Path(output_swf).resolve()
 if not output.is_relative_to(work_path('carry163')) or output==Path(input_swf).resolve():raise ValueError('output must stay in carry163 and differ from input')
 command=[sys.executable,'-B',str(ROOT/'build.py'),'--input',str(Path(input_swf).resolve()),'--sha',expected_sha256,'--output',str(output)]
 p=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=90)
 if p.returncode:raise RuntimeError('carry163 composition rejected: '+p.stdout+p.stderr)
 return json.loads(output.with_suffix('.json').read_text(encoding='utf-8'))
