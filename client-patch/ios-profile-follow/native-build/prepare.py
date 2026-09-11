from pathlib import Path
import hashlib, json, sys, zipfile, subprocess, os

ROOT = Path(os.environ.get('STARPOINT_IOS_PROFILE_WORK', r'F:\codex\ios-profile-follow-port-20260908'))
REPO = Path(r'F:\codex\startpoint-cn-private-clean')
LEGACY = Path(r'F:\codex\ios-rush-leaderboard-port-20260830')
sys.path.insert(0, str(LEGACY))
from wrap_abc_swf import swf_tag
import struct

def sha(b): return hashlib.sha256(b).hexdigest()
def run(*a):
    p = subprocess.run([str(x) for x in a], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if p.returncode: raise RuntimeError(p.stdout + p.stderr)
    return p.stdout

def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    ipa = Path(r'F:\codex\ios-artifacts\iOS-1.8.4-kulo-private-final-fantasy-soul-memberview-v6-rush-leaderboard-v3-r12b-navigation-abyss-multibothboss-level120-test-unsigned.ipa')
    assert sha(ipa.read_bytes()) == 'f44710abcbb6c657f25a205b8d72ca597be551f19e2f7b02a9591605339dcc40'
    with zipfile.ZipFile(ipa) as z:
        native=z.read('Payload/worldflipper.app/worldflipper')
        swf=z.read('Payload/worldflipper.app/worldflipper_ios_release.swf')
    assert sha(native)=='530db20daa356162b617c5d853335d5c4d2a09965fd89c2151a1dca03bccc1e8'
    assert sha(swf)=='2b6d7d9c4420872245053bc4150a913a208a589fc282ec0f65a43957618de6f9'
    (ROOT/'baseline-worldflipper').write_bytes(native)
    (ROOT/'baseline.swf').write_bytes(swf)
    n=struct.unpack_from('<Q',native,0x63b4b80+32)[0]
    stripped=native[0x59aed10:0x59aed10+n]
    assert sha(stripped)=='680b11a01a20dff64c4cf49f23b2bfa8b2bd30419a2857a078bb25cc25e23394'
    (ROOT/'baseline-stripped.abc').write_bytes(stripped)
    full=Path(r'F:\codex\ios-rush-navigation-port-20260907\build-r12b\navigation-full-restored.abc').read_bytes()
    assert sha(full)=='50d040382b26741ee773fbb76b2f87cbeb0152e334f762a44d560726937ced2c'
    assert hashlib.sha1(full).digest()==native[0x63b4b80:0x63b4b80+20]
    (ROOT/'baseline-full.abc').write_bytes(full)
    run(sys.executable, LEGACY/'wrap_abc_swf.py',ROOT/'baseline-full.abc',ROOT/'baseline-full.swf')
    java=Path(r'D:\java\bin\java.exe')
    ffdec=Path(r'F:\codex\tools\ffdec-26.2.1\app\ffdec-cli.jar')
    classes=['pinball.scene.playerProfile.PlayerProfileView', 'pinball.scene.playerProfile.profile.otherProfile.OtherProfileLogic', 'pinball.scene.event.rush.ranking.party.RushEventRankingPartyScene']
    for kind, f in [('ios', 'baseline-full.swf')]:
        out=run(java,'-Xmx4g','-jar',ffdec,'-onerror','abort','-format','script:pcode','-selectclass',','.join(classes),'-export','script',ROOT/(kind+'-pcode'),ROOT/f)
        (ROOT/(kind+'-export.log')).write_text(out,'utf-8')
    toolsdir=ROOT/'java'; toolsdir.mkdir(exist_ok=True)
    run(r'D:\java\bin\javac.exe','-cp',ffdec,'-d',toolsdir, REPO/'client-patch/character-carousel/FindMethodBody.java')
    pairs=[x for pair in zip(classes,['refreshFollowRelationButtons','applyButton','copyPlayedParty']) for x in pair]
    found=run(java,'-cp',str(toolsdir)+';'+str(ffdec),'FindMethodBody',ROOT/'baseline-full.swf',*pairs)
    (ROOT/'ios-method-locations.txt').write_text(found,'utf-8')
    print(found)

if __name__=='__main__': main()
