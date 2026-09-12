"""Read the final DEX with baksmali and recover every original method by removing hooks."""
import re, zipfile

def canonical(text):
    result=[]
    for method in re.split(r'(?=^\.method )', text, flags=re.M):
        labels={}
        method=re.sub(r':(?:try_start|try_end|catchall|catch|cond|goto|pswitch|sswitch|array)_[A-Za-z_0-9]+',
            lambda match: labels.setdefault(match[0], ':L'+str(len(labels))), method)
        result.append('\n'.join(line.strip() for line in method.splitlines()
            if line.strip() and not line.strip().startswith('#')))
    return '\n'.join(result)

def verify(work, java, libraries, run):
    with zipfile.ZipFile(work/'native.apk') as archive:
        (work/'original.dex').write_bytes(archive.read('classes.dex'))
    run([java,'-jar',libraries/'baksmali.jar','d','-o',work/'baseline-smali',work/'original.dex'],work,'baseline-decode')
    count=0
    for source in (work/'baseline-smali').rglob('*.smali'):
        text=(work/'readback-smali'/source.relative_to(work/'baseline-smali')).read_text()
        if source.name=='A.smali':
            text=text.replace('    invoke-static {p2}, Lcn/startpoint/StartupCache;->run(Landroid/content/pm/ApplicationInfo;)V\n\n','',1)
        if source.name=='S.smali':
            text=text.replace('    invoke-virtual {p1}, Landroid/content/Context;->getApplicationInfo()Landroid/content/pm/ApplicationInfo;\n\n'
                '    move-result-object v0\n\n'
                '    invoke-static {v0}, Lcn/startpoint/StartupCache;->run(Landroid/content/pm/ApplicationInfo;)V\n\n','',1)
        assert canonical(text)==canonical(source.read_text()),source
        count+=source.read_text().count('.method ')
    assert count==35 and len(list((work/'readback-smali').rglob('*.smali')))==6
    return count
