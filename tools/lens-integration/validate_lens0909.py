"""Independent 0909 acceptance checks for rules, private routines and exact scope."""
import argparse, copy, math
from pathlib import Path
import prepare_content as p
import prepare_lens0909 as prep
import wf_rogue_bundle as b
import wf_rogue_build as rb

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,required=True);ap.add_argument('--donor',type=Path,required=True)
    args=ap.parse_args();w=args.work;c=p.Chain();report=p.readj(w/'prepare-report.json')
    assert p.sha(c.manifest_bytes)==report['baseline_manifest_sha256']
    inventory=p.readj(w/'resources.json');index={(x['root'],x['rel']):x for x in inventory}
    cache={}
    def read(n,before=False):
        key=('common',p.hrel(n));row=index.get(key)
        if before or not row:return c.get(key)
        raw=(w/'resources/upload'/row['rel']).read_bytes();assert p.sha(raw)==row['sha256'];return raw
    def table(n,before=False):
        key=(n,before)
        if key not in cache:cache[key]=b.q.parse_node(read(n,before))
        return cache[key]
    donor=p.readj(args.donor/'client-tables/client_tables_payload.json')
    role_leaves=0
    for n,rows in donor.items():
        if n.startswith(('master/battle/','master/quest/','master/gacha_odds/')):continue
        expected=b.q.parse_node(p.merge_node(read(n,True),{'__n__':rows},[n],[]))
        assert table(n)==expected,n
        role_leaves+=len(list(prep.leaves(table(n))))
    quests='master/quest/boss_battle_quest.orderedmap'
    expected=b.q.parse_node(p.merge_node(read(quests,True),{'__n__':donor[quests]},[quests],[]))
    current=dict(prep.leaves(table(quests)));old=dict(prep.leaves(table(quests,True)))
    authored=dict(prep.leaves(expected));quest_receipts=[]
    rb._CURVES={'hp':{k:{lv:float(v) for lv,v in row.items()} for k,row in table(rb.CURVE_TABLES['hp']).items()}}
    for path,row in current.items():
        before=b._cells(old[path]);after=b._cells(row)
        if not after[0].isdigit() or not 1099001<=int(after[0])<=1099023:
            assert row==old[path];continue
        target=b._cells(authored[path]);diff={i for i,(x,y) in enumerate(zip(before,after)) if x!=y}
        assert diff=={99,105},(path,diff)
        assert after[105]==target[105]
        assert math.isclose(float(after[105]),float(before[105])*12)
        assert after[69]=='35' and after[119]=='1'
        quest_receipts.append({'quest':int(after[0]),'boss_hp_multiplier':after[99],'boss_tp_multiplier':after[105],
                               'time_frames':after[111],'single_hp_factor':0.55,'single_tp_factor':0.5})
    assert len(quest_receipts)==23
    states=prep.BOSS+'general_boss_state.orderedmap';state=table(states);original=table(states,True)
    assert p.rawmap(read(states))[prep.ENVY]==p.rawmap(read(states,True))[prep.ENVY]
    envy_expected=b.q.parse_node(p.merge_node(read(states,True),{'__n__':{prep.ENVY:donor[states][prep.ENVY]}},[states],[]))[prep.ENVY]
    assert state[prep.ENVY_ROUTINE]==envy_expected
    changes=0
    old_envy=dict(prep.leaves(original[prep.ENVY]))
    for path,row in prep.leaves(state[prep.ENVY_ROUTINE]):
        a=b._cells(old_envy[path]);z=b._cells(row);diff={i for i,(x,y) in enumerate(zip(a,z)) if x!=y}
        if diff:assert diff=={23} and a[23]=='80' and z[23]=='240';changes+=1
    assert changes==296
    for k,v in p.rawmap(read(states,True)).items():assert p.rawmap(read(states))[k]==v,('official routine changed',k)
    watch=table(prep.BOSS+'general_enemy_watch.orderedmap');oldwatch=table(prep.BOSS+'general_enemy_watch.orderedmap',True)
    newleaves=dict(prep.leaves(watch))
    for path,value in prep.leaves(oldwatch):assert newleaves[path]==value,('existing watch changed',path)
    assert watch['1'][prep.ENVY_CLONE][prep.ENVY_ROUTINE]==oldwatch['1'][prep.ENVY][prep.ENVY]
    partners=0
    for kind,nodes in oldwatch.items():
        for code,routines in nodes.items():
            for routine,node in routines.items():
                if prep.ENVY in node.get('1',{}):
                    assert watch[kind][code][routine]['1'][prep.ENVY_CLONE][prep.ENVY_ROUTINE]==node['1'][prep.ENVY][prep.ENVY]
                    partners+=1
    assert partners==2
    levels=table(prep.BOSS+'boss_level.orderedmap');general=table(prep.BOSS+'general_boss.orderedmap')
    fields=table('master/battle/field_data.orderedmap');zones=table('master/battle/zone.orderedmap')
    totals=[]
    for receipt in quest_receipts:
        if receipt['quest']==1099001:continue # entry alias, selected scene follows
        questrow=next(b._cells(row) for path,row in current.items() if b._cells(row)[0]==str(receipt['quest']))
        field=questrow[109];terrain,zone,rows=b._field_context(field,fields,zones)
        codes=[]
        for row in rows.values():
            cells=b._cells(row)
            for col in (24,28,32):
                assert cells[col]==cells[col+2]
                if cells[col] in ('','(None)'):continue
                assert cells[col]!=prep.ENVY and not cells[col].startswith('mod_fb_solo_')
                codes.append(cells[col]);assert '100' in general[cells[col]]
        enemy_level=int(questrow[106])
        bases=[rb.true_stat(code,'hp',enemy_level,levels) for code in codes]
        assert all(x and x[1]=='*' for x in bases)
        hp=sum(math.floor(x[0]*rb.GENERAL_HP_LEVEL_SCALE[enemy_level]*float(questrow[99])) for x in bases)
        assert abs(hp-300_000_000_000)<=len(codes),(field,hp,enemy_level)
        totals.append({'quest':receipt['quest'],'field':field,'multi_hp':hp,'time_frames':questrow[111]})
    race=p.readj(w/'approved-gacha.json');rows=race['pool']['1']
    assert len(rows)==287 and sum(x['odds'] for x in rows)==950000
    summer=next(x for x in rows if x['id']==149990)
    assert summer['odds']==0 and summer['isExchangeable'] is False
    oldrace=p.readj(p.REPO/'assets/gacha_rank_p5b.json')['990002']
    comparable=copy.deepcopy(race);comparable['pool']['1']=[x for x in rows if x['id']!=149990]
    assert comparable==oldrace
    client=[b._cells(row) for _,row in prep.leaves(table(prep.RACE))]
    expected=[[str(x['id']),str(x['rank']),str(x['odds']),str(x['isRateUp']).lower(),str(x['isLimited']).lower(),str(x['isExchangeable']).lower(),str(x['trialReadingForced']).lower()] for x in rows]
    assert client==expected
    decisions=p.readj(w/'resource-decisions.json')
    for n in decisions['deferred']:
        if n=='rich_text/cnmod_ashen_verdict_gacha_note.html.deflate':
            assert p.wf_atf.inflate(read(n)).startswith(p.wf_atf.inflate(read(n,True)))
        else:assert ('common',p.hrel(n)) not in index,n
    for row in p.readj(w/'server-files.json'):
        old=p.readj(p.REPO/row['path']);new=p.readj(w/'server'/row['path'])
        allowed={'990002'} if 'gacha' in row['path'] else {'149990','119996','169994','169997'}
        assert all(new[k]==v for k,v in old.items() if k not in allowed),row['path']
    terrain=p.readj(w/'five-boss-terrain-audit-v2.json');assert terrain['status']=='passed' and terrain['scene_count']==22
    sparse=p.readj(w/'validation-report.json');assert len(sparse['dsl_signature_and_round_trip'])==10 and not sparse['unresolved_paths']
    result={'status':'passed','resources_inventory_sha256':p.sha((w/'resources.json').read_bytes()),
            'server_inventory_sha256':p.sha((w/'server-files.json').read_bytes()),
            'quest_rows':quest_receipts,'stage_hp':totals,'envy_trial_rows':changes,'envy_partner_aliases':partners,
            'existing_watch_leaves_preserved':len(list(prep.leaves(oldwatch))),'race_five_star_count':len(rows),
            'solo_scaling':'deferred by user; native 0.55 HP / 0.5 TP unchanged','terrain_scenes':22,'dsl_count':10,
            'resource_count':len(inventory),'deferred_resources':len(decisions['deferred']),'ios_pairs':len(p.readj(w/'ios-pairs.json'))}
    p.savej(w/'acceptance-report.json',result)
    print('PASS: 23 quest rows; 22 HP/time scenes; 296 private Envy trials; original watch leaves and pools preserved')

if __name__=='__main__':main()
