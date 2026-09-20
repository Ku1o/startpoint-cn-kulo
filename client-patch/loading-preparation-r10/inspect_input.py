import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'loading-diagnostic'))
from common import s

tags = s.parts(Path(sys.argv[1]))[2]
for tag in tags:
    if tag[0] != 82 or tag[2][4:-1] not in (b'boot_ffc6', b'cn.diagnostics.LoadingTrace'):
        continue
    view = s.m.View(SimpleNamespace(abc=tag[3]), s.m.asm)
    for label, indices in view.by_label.items():
        if any(x in label for x in ('LoadingSceneBase/gotoNextScene|', 'LoadingSceneBase/startNextSceneAssetLoadWithDetail|',
                 'BattleScene/leaveHandler|', 'BattleScenePlayingStateImpl/update|', 'LoadingTrace$/mark|', 'LoadingTrace$/firstFrame|')):
            for bi in indices:
                print(tag[2][4:-1].decode(), bi, label, 'signature', tag[3].bodies[bi][:5])
                print(view.normalized(bi))
