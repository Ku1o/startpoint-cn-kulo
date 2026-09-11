"""Prepare 1.4.105 part 3 without SWF edits or shared-manifest writes.

Only item descriptions and the item-to-quest index change. The manifest owner
integrates this independent part after checking all sibling package members.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import zipfile
import prepare_content as p
import five_boss_art_contract as art

ITEM = 'master/item/item.orderedmap'
SEARCH = 'master/search/item_quest_search.orderedmap'
RUSH = 'master/quest/event/rush_event_quest.orderedmap'
BOSS = 'master/quest/boss_battle_quest.orderedmap'
ARCHIVE = 'pinball-1.4.104-1.4.105-3-how-to-get-sources.zip'
AUDIT = 'assets/asset-patch/audit/how-to-get-sources-1.4.105'
BATTLE_IDS = {2370097,2370098,2370099,2370100,2370101,10000143,10000144,10000145,10000146,10000147,999013,999014}
NOTES = {
    2370097: '入手方式：完成幻想连战第15关整轮通关奖励，非救援结算获得1个。需依次完成整轮关卡。',
    2370098: '入手方式：幻想连战第5、10、15关协力首领结算，分别获得5、10、20枚。',
    2370099: '入手方式：深渊连战逐层通关奖励，不同层数的保底数量与概率槽不同。',
    2370100: '入手方式：深渊连战第30层整轮通关概率奖励，或深渊活动商店兑换。需依次完成整轮关卡。',
    2370101: '入手方式：深渊连战第30层整轮通关概率奖励。需依次完成整轮关卡。',
    10000143: '入手方式：深渊连战第30层整轮通关必得1～2张；幻想连战第15关整轮通关（非救援）获得1张；五重交换所可用10个深界结晶兑换1张。',
    10000144: '入手方式：五重决战整轮通关，50%概率获得1张。',
    10000145: '入手方式：五重决战整轮通关获得5个；满足手动奖励倍率条件时获得10个。',
    10000146: '入手方式：首次完成五重决战的纪念奖励。仅首通获得，已经领取后无法通过重复挑战再次获得。',
    10000147: '入手方式：五重决战整轮通关，25%概率获得；数量随适用的手动奖励倍率变化。',
    999013: '入手方式：深渊连战部分层数概率掉落，或深渊活动商店兑换。',
    999014: '入手方式：深渊连战指定层数和整轮通关概率奖励，或幻想、深渊活动商店兑换。',
    999015: '入手方式：旧版道具已停用，不再通过现用赛季奖励发放。现用竞速池请使用竞速池扭蛋券。',
    999016: '入手方式：旧版道具已停用，不再通过现用赛季奖励发放。现用竞速池请使用竞速池十连券。',
    999017: '入手方式：深渊赛季排行榜结算奖励。请从深渊活动入口进入排行榜，查看当前赛季排行报酬和结算时间。',
    999018: '入手方式：深渊赛季排行榜结算奖励。请从深渊活动入口进入排行榜，查看当前赛季排行报酬和结算时间。',
}

def quest_row(event: int, quest: int, expected: float):
    return ['16',str(event),'',str(quest),str(event*1000+quest),format(expected,'.12g')]

def reward_sources(config):
    result = {str(i): [] for i in BATTLE_IDS}
    def add(item, event, quest, expected):
        rows=result[str(item)]
        row=quest_row(event,quest,expected)
        old=next((r for r in rows if r[:5]==row[:5]),None)
        if old: old[5]=format(float(old[5])+expected,'.12g')
        else: rows.append(row)
    # Read the effective server schedule, including chance curves and exclusions.
    for drop in config['per_round_drops']:
        if drop.get('type')!='item' or drop['id'] not in BATTLE_IDS: continue
        low,high=drop.get('rounds',[1,config['rounds']])
        for round_id in range(low,high+1):
            if round_id in drop.get('exclude_rounds',[]): continue
            chance=drop.get('chance',0)
            if isinstance(chance,dict):
                chance=chance['start']+chance.get('per_round',0)*(round_id-chance.get('base_round',round_id))
            chance=max(0,min(1,chance))
            slots=drop.get('slots',1)
            assert isinstance(slots,int) and slots>0
            guaranteed=drop.get('guaranteed_slots',0 if 'chance' in drop else slots)
            assert isinstance(guaranteed,int)
            guaranteed=max(0,min(slots,guaranteed))
            expected=drop.get('count',1)*(guaranteed+(slots-guaranteed)*chance)
            if expected>0: add(drop['id'],700099,round_id,expected)
    for drop in config['folder_clear_chance']:
        if drop['type']==0 and drop['id'] in BATTLE_IDS:
            add(drop['id'],700099,30,drop['count']*drop['chance'])
    for drop in config['folder_clear_random']:
        if len(drop['pool'])!=1 or drop['pool'][0] not in BATTLE_IDS: continue
        assert drop.get('pick')==[1,1]
        add(drop['pool'][0],700099,30,sum(drop['count'])/2*drop.get('chance',1))
    for round_id,count in [(5,5),(10,10),(15,20)]: add(2370098,700098,round_id,count)
    add(2370097,700098,15,1)
    add(10000143,700098,15,1)
    for item,expected in [(10000144,0.5),(10000145,5),(10000146,0),(10000147,0.25)]:
        # Zero is a neutral sort hint for the one-time proof, not a repeatable yield.
        result[str(item)].append(['2','1','99','1','1099001',str(expected)])
    assert all(result.values())
    return result

def verify_server_contract():
    config=p.readj(p.REPO/'assets/rogue_event.json')
    assert config['enabled'] and config['events']['700099']['rounds']==30
    event=copy.deepcopy(config['events']['700099'])
    # Apply the runtime extension's exact duplicate/equivalence contract.
    extra=p.readj(p.REPO/'assets/rogue_event_cnmod.json')['events']['700099']
    for drop in extra.get('folder_clear_chance',[]):
        old=next((d for d in event['folder_clear_chance'] if (d['type'],d['id'])==(drop['type'],drop['id'])),None)
        if old is None: event['folder_clear_chance'].append(drop)
        else: assert old==drop,'effective rogue extension drift'
    mode=(p.REPO/'src/lib/mode15.ts').read_text('utf-8')
    for snippet in ['5: 5,','10: 10,','15: 20,','const fullClear = ref.stage === 15 && !options.rescue;',
                    'id: MODE15_FULL_CLEAR_TOKEN_ID, count: 1','id: MODE15_FULL_CLEAR_TICKET_ID, count: 1']:
        assert snippet in mode,('review changed Fantasy rewards',snippet)
    five=(p.REPO/'src/multi/five-boss/rewards.ts').read_text('utf-8')
    for snippet in ['FIVE_BOSS_BLUEPRINT_DROP_RATE = 0.5','amount: 5 * input.rewardMultiplier',
                    'if (input.firstClear)','checkedRandomFloat(randomFloat) < 0.25']:
        assert snippet in five,('review changed Five Boss rewards',snippet)
    assert p.readj(p.REPO/'assets/boss_coin_shop.json')['99']['990099002']['costs']==[{'id':10000145,'amount':10}]
    return event

def build_tables(before, sources):
    items=p.rawmap(before[ITEM]);search=p.rawmap(before[SEARCH])
    for item,note in NOTES.items():
        rows=p.csvrows(items[str(item)])
        assert len(rows)==1 and len(rows[0])==23
        assert '入手方式：' not in rows[0][5],'already patched; select exact preimage'
        rows[0][5]+='\n\n'+note
        items[str(item)]=p.packcsv(rows)
    for item,rows in sources.items():
        assert item not in search,'already indexed; review new upstream sources'
        search[item]=p.packcsv(rows)
    return {ITEM:p.packmap(items),SEARCH:p.packmap(search)}

def validate_tables(before, after, sources, read):
    old_items,new_items=p.rawmap(before[ITEM]),p.rawmap(after[ITEM])
    assert old_items.keys()==new_items.keys()
    for key,raw in old_items.items():
        if int(key) in NOTES:
            expected=p.csvrows(raw);expected[0][5]+='\n\n'+NOTES[int(key)]
            assert p.csvrows(new_items[key])==expected,('non-description field changed',key)
        else: assert new_items[key]==raw,('unrelated item changed',key)
    old_search,new_search=p.rawmap(before[SEARCH]),p.rawmap(after[SEARCH])
    assert set(new_search)-set(old_search)==set(sources)
    assert all(new_search[k]==v for k,v in old_search.items())
    rush=p.rawmap(read(RUSH));boss=p.rawmap(p.rawmap(read(BOSS))['1'])
    for item,rows in sources.items():
        assert p.csvrows(new_search[item])==rows
        for row in rows:
            assert len(row)==6 and float(row[5])>=0
            if row[0]=='16':
                assert row[1] in ['700098','700099']
                assert 1<=int(row[3])<=(15 if row[1]=='700098' else 30),'hidden/training quest'
                quest=p.csvrows(p.rawmap(rush[row[1]])[row[3]])[0]
                assert quest[0]==row[4] and int(quest[2])==int(row[3])
                if int(row[3])>1:
                    previous=['16',row[1],'',str(int(row[3])-1),str(int(row[4])-1)]
                    assert quest[9:14]==previous,'missing previous-round visibility gate'
                    if row[1]=='700098':
                        assert quest[36:41]==previous,'missing Fantasy selection gate'
            else:
                assert row[:5]==['2','1','99','1','1099001']
                assert p.csvrows(p.rawmap(boss['99'])['1'])[0][0]=='1099001'
    # Preserve current preload closure and the separate 20px/40px image contracts.
    display=art.validate_display(lambda name: after.get(name) or read(name))
    return {'existing_item_rows':len(old_items),'existing_search_rows':len(old_search),
            'new_search_keys':len(sources),'new_source_rows':sum(map(len,sources.values())),
            'description_rows':len(NOTES),'five_boss_display_contract':display}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work',type=Path,required=True)
    ap.add_argument('--apply-source-package',action='store_true')
    args=ap.parse_args();work=args.work.resolve()
    assert work.is_relative_to(Path('F:/codex/work').resolve())
    work.mkdir(parents=True,exist_ok=True)
    chain=p.Chain();assert chain.tail=='1.4.105'
    tail=[x for x in chain.manifest['patches'] if x.get('enabled') and x['version']=='1.4.105'][0]
    assert tail['depends_on']=='1.4.104' and ARCHIVE not in tail.get('chain',[])
    def read(name):
        raw=chain.get(('common',p.hrel(name)))
        assert raw is not None,('missing dependency',name)
        return raw
    before={n:read(n) for n in [ITEM,SEARCH]}
    sources=reward_sources(verify_server_contract());after=build_tables(before,sources)
    checks=validate_tables(before,after,sources,read)
    for label,blobs in [('before',before),('prepared',after)]:
        for name,raw in blobs.items():
            dest=work/label/p.member(('common',p.hrel(name)));dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
    payloads={p.member(('common',p.hrel(n))):b for n,b in after.items()}
    archive=work/ARCHIVE
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,raw in sorted(payloads.items()):
            info=zipfile.ZipInfo(name,(2026,9,11,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,raw)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and set(z.namelist())==set(payloads)
        assert all(z.read(n)==b for n,b in payloads.items())
    integrity={'name':ARCHIVE,'size':archive.stat().st_size,'sha256':p.sha(archive.read_bytes()),
               'members':len(payloads),'files':sorted(payloads)}
    report={'version':'1.4.105','depends_on':'1.4.104','part':3,'archive':integrity,
            'checks':checks,'sources':sources,'notes':NOTES,'source_reads':chain.reads,
            'resources':[{'logical':n,'member':p.member(('common',p.hrel(n))),
                          'before_sha256':p.sha(before[n]),'after_sha256':p.sha(after[n]),
                          'changed_rows':sorted(NOTES) if n==ITEM else sorted(map(int,sources))} for n in after],
            'manifest_before_sha256':p.sha(chain.manifest_bytes),'manifest_written':False,
            'swf_changed':False,'runtime_synced':False,'device_tested':False,
            'save_impact':'No IDs, inventory, schema or persisted progress changed.',
            'limitations':['Native UI cannot add a ranking button or dynamically hide an already claimed first-clear source without SWF changes.',
                          'Rush sources target the actual reward round and keep the existing unlock checks; no hidden quest or fake first-round reward.']}
    for name,obj in [('report.json',report),('archive-integrity.json',integrity)]:p.savej(work/name,obj)
    if args.apply_source_package:
        # No writes to manifest or loose resources: one coordinator owns those.
        dest=p.REPO/'assets/asset-patch/active'/ARCHIVE
        assert not dest.exists(),'refuse rewriting another package'
        for sibling in dest.parent.glob('pinball-1.4.104-1.4.105-*.zip'):
            with zipfile.ZipFile(sibling) as z: assert not (set(z.namelist()) & set(payloads)),('sibling overlap',sibling)
        assert (p.REPO/'assets/asset-patch/manifest.json').read_bytes()==chain.manifest_bytes,'manifest changed; re-review'
        dest.write_bytes(archive.read_bytes())
        assert p.sha(dest.read_bytes())==integrity['sha256']
        for name in ['report.json','archive-integrity.json']:
            out=p.REPO/AUDIT/name;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes((work/name).read_bytes())
    print(json.dumps({'archive':integrity,'checks':checks},ensure_ascii=True))

if __name__=='__main__':main()
