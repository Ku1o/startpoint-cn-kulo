import importlib.util, sys, zipfile
from pathlib import Path
from types import SimpleNamespace
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('admission_swf',HERE.parent/'startup-cache/build_swf.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
root=HERE.parents[1]
work=root/'outputs/client-admission-work';work.mkdir(exist_ok=True)
with zipfile.ZipFile(root/'outputs/shop-first-open-lan-test-20260913/StarPoint-CN-1.8.1-shop-first-open-lan-test-20260913.apk') as z:
    (work/'input.swf').write_bytes(z.read('assets/worldflipper_android_release.swf'))
abcs=[t for t in s.parts(work/'input.swf')[2] if t[0]==82]
main=s.m.View(SimpleNamespace(abc=abcs[-1][3]),s.m.asm)
for label,ids in main.by_label.items():
    if any(x.lower() in label.lower() for x in sys.argv[1:]):
        print(ids,label)
        if '--dump' in sys.argv:
            for i in ids: print(main.normalized(i))
