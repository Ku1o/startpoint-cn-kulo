"""Reproduce the missing folder membership using the effective CDN resources."""
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/lens-integration'))
import prepare_content as p


def audit(work):
    chain = p.Chain()
    def read(logical):
        raw = chain.get(('common',p.hrel(logical))); assert raw
        dest = work/'before'/logical; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(raw)
        return p.rawmap(raw)
    search = read('master/search/item_quest_search.orderedmap')
    listed = read('master/quest/event/event_list.orderedmap')
    folders = read('master/quest/event/event_folder_events.orderedmap')
    events = read('master/quest/event/hard_multi_event.orderedmap')
    quests = read('master/quest/event/hard_multi_event_quest.orderedmap')
    available = {tuple(p.csvrows(raw)[0][:2]) for raw in listed.values()}
    grouped = {}
    for folder, rows in folders.items():
        for raw in p.rawmap(rows).values():
            row=p.csvrows(raw)[0]
            grouped[tuple(row[:2])] = folder
    checks=[]
    for item in range(40401,40413):
        source=[r for r in p.csvrows(search[str(item)]) if r[0]=='18' and 1001<=int(r[1])<=1006]
        assert len(source)==1
        row=source[0];key=('13',row[1])
        assert key not in available, 'old empty-result reproduction changed'
        assert key in grouped, 'folder-backed source missing'
        event=p.csvrows(events[row[1]])[0]
        quest=p.csvrows(p.rawmap(quests[row[1]])[row[3]])[0]
        assert quest[0]==row[4] and quest[5:7]==['2025-07-10 12:00:00','(None)']
        assert event[23:25]==['2025-07-10 12:00:00','(None)']
        assert quest[7:12]==['7','1','','38','1038']
        checks.append({'item':item,'quest':int(row[4]),'folder':grouped[key],
                       'ordinary_list_missing':True,'folder_membership_found':True})
    for event in ('700098','700099'):
        assert ('11',event) not in available and ('11',event) in grouped
    report={'version':chain.tail,'mech_checks':checks,'fantasy_abyss_same_filter_failure':True,
            'condition':'Folder unlocked and event within playable period; native quest filters remain.',
            'reads':chain.reads,'device_acceptance':False}
    p.savej(work/'source-gate-audit.json',report)
    print(json.dumps({'mech_materials':len(checks),'fantasy_abyss_folder_sources':True}))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,required=True)
    audit(ap.parse_args().work.resolve())
