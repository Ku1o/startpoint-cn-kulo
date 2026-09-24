from pathlib import Path
import argparse,importlib.util
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('author_package',HERE.parent/'author-content-1043/package_android.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
SWF_SHA='caea4de3f02591211dfb4359f37281b60696c6433719ef6383fbefb6844e4091'
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--swf',type=Path,required=True);ap.add_argument('--work',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    p.main(a.swf,a.work,a.out,expected_swf=SWF_SHA,label='author-unified-damage')
