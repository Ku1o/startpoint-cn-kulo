"""A separate local QA app for URI grants, clipboard and bounded fixture testing."""
import sys, zipfile, shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import *
def main():
    root=WORK/'phone-qa';root.mkdir(exist_ok=True);classes=root/'classes';classes.mkdir(exist_ok=True)
    manifest=root/'AndroidManifest.xml';shutil.copyfile(HERE/'tests/PhoneQA.xml',manifest)
    b.run([b.JAVA.with_name('javac.exe'),'--release','8','-encoding','UTF-8','-cp',WORK/'android-30.jar','-d',classes,HERE/'tests/PhoneReceiver.java',HERE/'tests/PhoneProbe.java'],root,'compile')
    with zipfile.ZipFile(root/'input.jar','w') as z:
        for p in classes.rglob('*.class'):z.write(p,p.relative_to(classes).as_posix())
    b.run([b.JAVA,'-cp',b.SDK/'lib/android/bin/d8.jar','com.android.tools.r8.D8','--lib',WORK/'android-30.jar','--min-api','21','--output',root,root/'input.jar'],root,'d8')
    b.run([b.SDK/'lib/android/bin/aapt.exe','package','-f','-M',manifest,'-I',WORK/'android-30.jar','-F',root/'unsigned.apk'],root,'aapt')
    with zipfile.ZipFile(root/'unsigned.apk','a') as z:z.write(root/'classes.dex','classes.dex')
    digest=sha(b''.join((HERE/'tests'/name).read_bytes() for name in ['PhoneReceiver.java','PhoneProbe.java','PhoneQA.xml']))
    apk=root/('phone-qa-'+digest[:12]+'.apk')
    if not apk.exists():b.run(['powershell','-NoProfile','-NonInteractive','-File',HERE.parent/'lens0907-0908/sign_apk.ps1','-InputApk',root/'unsigned.apk','-OutputApk',apk,'-ApkSigner',b.ALIB/'apksigner.jar','-Java',b.JAVA],root,'sign')
    (root/'current-apk.txt').write_text(str(apk),encoding='utf8');print(apk)
if __name__=='__main__':main()
