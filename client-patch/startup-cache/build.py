"""Reproducible, pinned LAN build; changes only SWF, AIR UUID and audited primary DEX."""
import hashlib, importlib.util, json, re, shutil, subprocess, sys, uuid, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SDK = Path('F:/codex/ios-rush-leaderboard-port-20260830/AIRSDK_51.2.1.5')
JAVA = Path('D:/java/bin/java.exe')
ALIB = SDK/'lib/android/lib'
APKTOOL = Path('F:/codex/tools/apktool_3.0.3.jar')
BASE = ROOT/'outputs/player-login-cumulative-lan-test-20260910/StarPoint-CN-1.8.1-player-login-abyss-lens-lan-test.apk'
BASE_SHA = '27de717e8864ea35a329032fa3f7dc23e8d99e3f6187b411a39f321d1509a200'
BASE_UUID = '88472c39-ba54-42fa-bfc0-a34e7fd34aea'
CERT = '569d19a3578d4cba16e3d6e7ad8ccab4fa667efc758deef6c9be3adb99919894'
STUBS = {
    'android/content/pm/ApplicationInfo.java': 'package android.content.pm; public class ApplicationInfo { public String packageName,dataDir,sourceDir; public int uid; }',
    'android/os/Process.java': 'package android.os; public class Process { public static int myUid(){return 0;} }',
    'android/util/Log.java': 'package android.util; public class Log { public static int i(String t,String m){System.out.println(t+": "+m);return 0;} public static int w(String t,String m){System.out.println(t+": "+m);return 0;} }',
}

def sha(data): return hashlib.sha256(data).hexdigest()

def run(command, work, label, timeout=180):
    p = subprocess.Popen([str(x) for x in command], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        output, _ = p.communicate(timeout=timeout)
        (work/(label+'.log')).write_bytes(output)
        if p.returncode: raise RuntimeError(label+' failed:\n'+output.decode('utf8','replace')[-6000:])
        return output.decode('utf8', 'replace')
    finally:
        if p.poll() is None:
            subprocess.run(['taskkill', '/PID', str(p.pid), '/T', '/F'], capture_output=True, timeout=15)
            p.wait(timeout=15)

def build(work):
    work.mkdir(parents=True, exist_ok=False)
    assert sha(BASE.read_bytes()) == BASE_SHA
    uid = str(uuid.uuid4()); (work/'uuid.txt').write_text(uid)
    with zipfile.ZipFile(BASE) as z:
        (work/'input.swf').write_bytes(z.read('assets/worldflipper_android_release.swf'))
        with zipfile.ZipFile(work/'native.apk', 'w') as mini:
            for name in ['classes.dex', 'AndroidManifest.xml']: mini.writestr(name, z.read(name))
    compiler = [JAVA, '-Dflexlib='+str(SDK/'frameworks'), '-Xmx512m', '-jar', SDK/'lib/compc-cli.jar',
                '+configname=air', '-swf-version=44', '-target-player=32.0', '-debug=false']
    for name, src, cls in [('login', HERE.parent/'player-login/src', 'cn.account.PlayerLogin'),
                            ('details', HERE.parent/'abyss-detail-ui/src', 'cn.ui.AbyssDetails'),
                            ('empty', HERE/'src', 'cn.asset.EmptyUpdate')]:
        run([*compiler, '-compiler.source-path='+str(src), '-include-classes='+cls,
             '-output='+str(work/(name+'.swc'))], work, 'compile-'+name)
    run([sys.executable, HERE/'build_swf.py', work], work, 'swf-build')
    ffdec=Path('F:/codex/tools/ffdec_26.2.1/ffdec.jar')
    check_classes=work/'ffdec-classes';check_classes.mkdir()
    run([JAVA.with_name('javac.exe'),'-cp',ffdec,'-d',check_classes,HERE/'CompareBodies.java'],work,'ffdec-compile')
    run([JAVA,'-Xmx2g','-cp',str(ffdec)+';'+str(check_classes),'CompareBodies',work/'input.swf',
         work/'client-three-fixes.swf'],work,'ffdec-verify')
    print('SWF graft verified', flush=True)
    # Only compile stubs for the three stable Android symbols used by this helper.
    # None of these stubs are packaged; Android provides the real implementations.
    for relative, text in STUBS.items():
        dest = work/'stubs'/relative; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_text(text)
    identity = work/'generated/cn/startpoint/BuildIdentity.java'; identity.parent.mkdir(parents=True)
    identity.write_text('package cn.startpoint; final class BuildIdentity { static final String ID="'+uid+'"; }')
    classes = work/'javaclasses'; classes.mkdir()
    run([JAVA.with_name('javac.exe'), '--release', '8', '-d', classes,
         *sorted((work/'stubs').rglob('*.java')), identity, HERE/'native/cn/startpoint/StartupCache.java'], work, 'javac')
    with zipfile.ZipFile(work/'cleanup.jar', 'w') as jar:
        for file in sorted((classes/'cn').rglob('*.class')): jar.write(file, file.relative_to(classes).as_posix())
    dex = work/'helper-dex'; dex.mkdir()
    run([JAVA, '-cp', SDK/'lib/android/bin/d8.jar', 'com.android.tools.r8.D8', '--min-api', '21',
         '--output', dex, work/'cleanup.jar'], work, 'd8')
    run([JAVA, '-jar', APKTOOL, 'd', '--no-assets', '--no-res', '-o', work/'native', work/'native.apk'], work, 'native-decode')
    run([JAVA, '-jar', ALIB/'baksmali.jar', 'd', '-o', work/'helper-smali', dex/'classes.dex'], work, 'helper-decode')
    smali = work/'native/smali'
    original = {p.relative_to(smali).as_posix():p.read_text() for p in smali.rglob('*.smali')}
    hooks = {
        's/h/e/l/l/A.smali': (
            '.method public instantiateClassLoader(Ljava/lang/ClassLoader;Landroid/content/pm/ApplicationInfo;)Ljava/lang/ClassLoader;',
            '    invoke-static {p2}, Lcn/startpoint/StartupCache;->run(Landroid/content/pm/ApplicationInfo;)V\n\n'),
        's/h/e/l/l/S.smali': (
            '.method protected attachBaseContext(Landroid/content/Context;)V',
            '    invoke-virtual {p1}, Landroid/content/Context;->getApplicationInfo()Landroid/content/pm/ApplicationInfo;\n\n'
            '    move-result-object v0\n\n'
            '    invoke-static {v0}, Lcn/startpoint/StartupCache;->run(Landroid/content/pm/ApplicationInfo;)V\n\n')}
    for name, (method, insert) in hooks.items():
        text = original[name]; assert text.count(method) == 1
        start = text.index(method); at = text.index('    const/4', start)
        patched = text[:at] + insert + text[at:]
        assert patched.replace(insert, '', 1) == text
        (smali/name).write_text(patched)
    for file in (work/'helper-smali').rglob('*.smali'):
        dest = smali/file.relative_to(work/'helper-smali'); assert not dest.exists()
        dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(file, dest)
    run([JAVA, '-jar', ALIB/'smali.jar', 'a', '-a', '21', '-o', work/'classes.dex', smali], work, 'native-assemble')
    run([JAVA, '-jar', ALIB/'baksmali.jar', 'd', '-o', work/'readback-smali', work/'classes.dex'], work, 'native-readback')
    # Decoder formatting may differ; compare the rebuilt DEX against a same-tool baseline round trip.
    run([JAVA, '-jar', ALIB/'smali.jar', 'a', '-a', '21', '-o', work/'roundtrip.dex', work/'native/smali'], work, 'native-repeat')
    assert (work/'roundtrip.dex').read_bytes() == (work/'classes.dex').read_bytes()
    for name, (method, insert) in hooks.items():
        assert (work/'readback-smali'/name).read_text().count('Lcn/startpoint/StartupCache;->run') == 1
    from verify_native import verify
    native_methods=verify(work,JAVA,ALIB,run)
    native_report = {'hooks': [x[0] for x in hooks.values()], 'original_classes': len(original),
                     'added_classes': len(list((work/'helper-smali').rglob('*.smali'))),
                     'only_two_existing_methods_have_insertions': True, 'stub_classes_packaged': False,
                     'original_methods_recovered_from_final_dex': native_methods}
    # Exact APK member verification (manifest differs ONLY in the mandatory AIR UUID).
    excluded = {'META-INF/MANIFEST.MF', 'META-INF/WF.SF', 'META-INF/WF.RSA'}
    payloads = {'assets/worldflipper_android_release.swf': (work/'client-three-fixes.swf').read_bytes(),
                'classes.dex': (work/'classes.dex').read_bytes()}
    with zipfile.ZipFile(BASE) as z, zipfile.ZipFile(work/'unsigned.apk', 'w') as out:
        manifest = z.read('AndroidManifest.xml'); assert manifest.count(BASE_UUID.encode('utf-16le')) == 1
        payloads['AndroidManifest.xml'] = manifest.replace(BASE_UUID.encode('utf-16le'), uid.encode('utf-16le'))
        for item in z.infolist():
            if item.filename not in excluded: out.writestr(item, payloads.get(item.filename, z.read(item.filename)))
    align = Path('F:/StartPointCN/wf_full_patch/build-tools/zipalign.exe')
    run([align, '-p', '4', work/'unsigned.apk', work/'aligned.apk'], work, 'align')
    output = work/'StarPoint-CN-1.8.1-cache-rounded-lan.apk'
    run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', HERE.parent/'lens0907-0908/sign_apk.ps1',
         '-InputApk', work/'aligned.apk', '-OutputApk', output, '-ApkSigner', ALIB/'apksigner.jar', '-Java', JAVA], work, 'sign')
    verification = run([JAVA, '-jar', ALIB/'apksigner.jar', 'verify', '--verbose', '--print-certs', output], work, 'sign-check')
    assert CERT in verification.lower() and 'Verified using v2 scheme (APK Signature Scheme v2): true' in verification
    run([align, '-c', '-p', '4', output], work, 'alignment-check')
    with zipfile.ZipFile(BASE) as old, zipfile.ZipFile(output) as new:
        assert set(old.namelist())-excluded == set(new.namelist())-excluded
        for name in set(old.namelist())-excluded:
            assert new.read(name) == payloads.get(name, old.read(name)), name
    report = {'base_apk_sha256': BASE_SHA, 'apk_sha256': sha(output.read_bytes()), 'uniqueappversionid': uid,
              'signer_sha256': CERT, 'changed_members': list(payloads), 'native': native_report,
              'swf': json.loads((work/'swf-verification.json').read_text()), 'device_tested': False}
    (work/'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(str(output), flush=True)
    # Remove only this build's disposable APK intermediates after exact payload verification.
    for name in ['unsigned.apk', 'aligned.apk']:
        file = (work/name).resolve(); assert file.parent == work.resolve(); file.unlink()

if __name__ == '__main__': build(Path(sys.argv[1]).resolve())
