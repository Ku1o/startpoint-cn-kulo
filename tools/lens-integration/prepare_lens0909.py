"""Prepare the approved 0909 subset against current effective CN bytes.

Writes sparse candidates only. No donor code, clients, databases or CDN writes.
"""
from __future__ import annotations
import argparse, base64, copy, io, json, math, zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import prepare_content as p
import wf_rogue_bundle as b
import wf_rogue_build as rb

ENVY = 'devil_commander_evil_envy_80'
ENVY_CLONE = 'mod_fb_envy_trial_actor'
ENVY_ROUTINE = 'mod_fb_envy_trial'
RACE = 'master/gacha_odds/cnmod_ashen_verdict_gacha_character_5.orderedmap'
BOSS = 'master/battle/boss/'

def payload(node):
    if isinstance(node, dict): return {'__n__': {k:payload(v) for k,v in node.items()}}
    return base64.b64encode(p.zlib.compress(node.encode('utf-8'))).decode()

def csvline(cells):
    out=io.StringIO(newline='');p.csv.writer(out,lineterminator='').writerow(cells);return out.getvalue()

def leaves(node, path=()):
    if isinstance(node,dict):
        for k,v in node.items():yield from leaves(v,path+(k,))
    else: yield path,node

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--donor',type=Path,required=True)
    ap.add_argument('--review',type=Path,required=True);ap.add_argument('--work',type=Path,required=True)
    args=ap.parse_args();w=args.work.resolve();d=args.donor.resolve()
    assert not w.is_relative_to((p.REPO/'.cdn').resolve());w.mkdir(parents=True,exist_ok=True)
    chain=p.Chain();assert chain.tail=='1.4.102', 're-review changed baseline'
    assets={};logical={};changes=[];tables={};before_tables={};server={};server_before={}
    def get(n):return assets.get(('common',p.hrel(n))) or chain.get(('common',p.hrel(n)))
    def tbl(n):
        if n not in tables:
            tables[n]=b.q.parse_node(get(n));before_tables[n]=copy.deepcopy(tables[n])
        return tables[n]
    def srv(n):
        if n not in server:
            raw=(p.REPO/'assets'/n).read_bytes();server_before[n]=raw;server[n]=json.loads(raw)
        return server[n]

    source=[];all_assets={}
    for archive in sorted(d.glob('archive-*-diff/*.zip')):
        source.append({'path':str(archive),'sha256':p.sha(archive.read_bytes())})
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            for member in z.namelist():
                parts=member.split('/');assert len(parts)==4 and parts[0]=='production'
                key=(p.REVERSE_ROOTS[parts[1]],'/'.join(parts[2:]));all_assets[key]=z.read(member)
    recovered=p.readj(args.review/'resolved-asset-paths.json');selected=[];deferred=[]
    for row in p.readj(args.review/'asset-comparison.json'):
        key=(row['root'],row['rel']);n=recovered.get(row['rel'],row['logical'])
        assert p.hrel(n)==row['rel'] and p.sha(all_assets[key])==row['sha256']
        # Only approved characters and their new action dependencies. Independent
        # sprite/effect atlas optimizations await the user's resource decision.
        include=(row['root'] in ('android','medium') or 'white_tiger_summer' in n
                 or n.endswith('.action.dsl.amf3.deflate') or '/zenith_explosion/' in n)
        if include: assets[key]=all_assets[key];logical[key]=n;selected.append(n)
        else: deferred.append(n)

    donor_tables=p.readj(d/'client-tables/client_tables_payload.json')
    for n,rows in donor_tables.items():
        if n==RACE:continue
        rows=copy.deepcopy(rows)
        if n==BOSS+'general_boss_state.orderedmap':
            # The author changed the official shared Envy routine. Clone the
            # whole donor result, retaining the original stored row verbatim.
            envy=p.merge_node(get(n),{'__n__':{ENVY:rows.pop(ENVY)}},[n],[])
            private=b.q.parse_node(envy)[ENVY]
            rows[ENVY_ROUTINE]=payload(private)
        if n=='master/quest/boss_battle_quest.orderedmap':
            merged=p.merge_node(get(n),{'__n__':rows},[n],[])
            original=b.q.parse_node(get(n));incoming=b.q.parse_node(merged)
            for path,row in leaves(incoming):
                quest_id=b._cells(row)[0]
                if not quest_id.isdigit() or not 1099001<=int(quest_id)<=1099023:continue
                parent=original;dest=tbl(n)
                for k in path[:-1]:parent=parent[k];dest=dest[k]
                current=b._cells(parent[path[-1]]);new=b._cells(row)
                assert current[69]=='35' and current[119]=='1'
                for col in (99,105):current[col]=new[col]
                dest[path[-1]]=csvline(current)
            continue
        key=('common',p.hrel(n));logical[key]=n
        assets[key]=p.merge_node(get(n),{'__n__':rows},[n],changes)

    gb=tbl(BOSS+'general_boss.orderedmap');levels=tbl(BOSS+'boss_level.orderedmap')
    variables=tbl(BOSS+'general_boss_variable.orderedmap');watch=tbl(BOSS+'general_enemy_watch.orderedmap')
    zones=tbl('master/battle/zone.orderedmap')
    rb._tbl=lambda n:tbl(n)
    refs=rb.code_referenced_bosses(gb);assert not refs['degraded']
    aliases=[]
    def clone(source,target,routine=None):
        assert target not in gb and target not in levels
        assert rb.identity_clone_locked_boss_reason([source],code_references=refs) is None
        gb[target]=copy.deepcopy(gb[source]);levels[target]=copy.deepcopy(levels[source])
        if source in variables:variables[target]=copy.deepcopy(variables[source])
        selfwatch=watch.setdefault('1',{})
        if source in selfwatch:selfwatch[target]=copy.deepcopy(selfwatch[source])
        count=rb.clone_enemy_watch_partner_aliases(watch,source,target)
        assert rb.enemy_watch_partner_alias_error(watch,source,target) is None
        if routine:
            originals=set()
            for level,row in gb[target].items():
                cells=b._cells(row);originals.add(cells[42]);cells[42]=routine;gb[target][level]=csvline(cells)
            assert len(originals)==1;oldroutine=originals.pop()
            if target in selfwatch and oldroutine in selfwatch[target]:
                selfwatch[target][routine]=copy.deepcopy(selfwatch[target][oldroutine])
            for kind in watch.values():
                for own in kind.values():
                    for phase in own.values():
                        partner=phase.get('1',{}).get(target,{})
                        if oldroutine in partner:partner[routine]=copy.deepcopy(partner[oldroutine])
        aliases.append({'source':source,'target':target,'routine':routine,'partner_aliases':count})
    clone(ENVY,ENVY_CLONE,ENVY_ROUTINE)
    # Donor's new actors and existing private actors also need watch aliases
    # when switching their routine; retain the official actor/routine branches.
    for target,source_id in [('mod_fb_eye_s2','eye_dragon_multibattle_boss'),('mod_fb_hero_s2','hero_big_boss_kc_multi')]:
        if source_id in variables and target not in variables:variables[target]=copy.deepcopy(variables[source_id])
        if source_id in watch.get('1',{}) and target not in watch['1']:watch['1'][target]=copy.deepcopy(watch['1'][source_id])
        rb.clone_enemy_watch_partner_aliases(watch,source_id,target)
    for target in [k for k in gb if k.startswith('mod_fb_')]:
        routines={b._cells(v)[42] for v in gb[target].values()}
        for newroutine,oldroutine in [('mod_fb_eye_trial','eye_dragon_multibattle_boss'),('mod_fb_hero_trial','hero_big_boss_multi')]:
            if newroutine not in routines:continue
            own=watch.get('1',{}).get(target,{})
            if oldroutine in own:own[newroutine]=copy.deepcopy(own[oldroutine])
            for kind in watch.values():
                for node in kind.values():
                    for phase in node.values():
                        partner=phase.get('1',{}).get(target,{})
                        if oldroutine in partner:partner[newroutine]=copy.deepcopy(partner[oldroutine])
    # The user deferred single-player native scaling changes. Keep the same
    # actor in both slots: 55% HP / 50% TP remains the native solo behavior.
    parity=[]
    for name,layers in zones.items():
        if not name.startswith('mod_five_boss_'):continue
        for layer,row in layers.items():
            cells=b._cells(row)
            for col in (24,28,32):
                if cells[col] in ('','(None)'):continue
                assert cells[col-1]=='1' and cells[col+1]=='1' and cells[col]==cells[col+2]
                source_id=cells[col]
                if source_id==ENVY:source_id=ENVY_CLONE
                cells[col]=source_id;cells[col+2]=source_id
            layers[layer]=csvline(cells)
    # The donor's aggregate HP arithmetic used a different scene roster.
    # Resolve each CN scene and actual enemy level, then solve only quest c99.
    # Private trials, levels and official boss statistics remain independent.
    curves=tbl(rb.CURVE_TABLES['hp'])
    rb._CURVES={'hp':{k:{lv:float(v) for lv,v in row.items()} for k,row in curves.items()}}
    fields=tbl('master/battle/field_data.orderedmap');hp_receipts=[]
    quests=tbl('master/quest/boss_battle_quest.orderedmap')
    for path,row in list(leaves(quests)):
        cells=b._cells(row)
        if not cells[0].isdigit() or not 1099001<=int(cells[0])<=1099023:continue
        _,zone,layers=b._field_context(cells[109],fields,zones)
        codes=[b._cells(layer)[col] for layer in layers.values() for col in (24,28,32)
               if b._cells(layer)[col] not in ('','(None)')]
        level=int(cells[106]);assert level in rb.GENERAL_HP_LEVEL_SCALE
        assert all(b._cells(levels[code])[1]=='hit_hp_basic_normal' and b._cells(levels[code])[4]=='hit_hp_boss' for code in codes)
        bases=[rb.true_stat(code,'hp',level,levels) for code in codes]
        assert all(value and value[1]=='*' for value in bases)
        raw_hp=sum(value[0]*rb.GENERAL_HP_LEVEL_SCALE[level] for value in bases)
        donor_coefficient=cells[99];cells[99]=format(300_000_000_000/raw_hp,'.15g')
        parent=quests
        for k in path[:-1]:parent=parent[k]
        parent[path[-1]]=csvline(cells)
        hp_receipts.append({'quest':int(cells[0]),'field':cells[109],'enemy_level':level,'actors':codes,
            'donor_coefficient':donor_coefficient,'cn_coefficient':cells[99],
            'donor_result_in_cn':sum(math.floor(value[0]*rb.GENERAL_HP_LEVEL_SCALE[level]*float(donor_coefficient)) for value in bases)})
    for n,node in tables.items():
        key=('common',p.hrel(n));logical[key]=n
        assets[key]=p.merge_node(get(n),payload(node),[n],changes)
    assert p.rawmap(assets[('common',p.hrel(BOSS+'general_boss_state.orderedmap'))])[ENVY]==p.rawmap(chain.get(('common',p.hrel(BOSS+'general_boss_state.orderedmap'))))[ENVY]
    # Untouched official boss/level/variable rows and non-five-boss zones remain
    # byte-identical. Additive watch aliases never alter an existing leaf.
    for n in (BOSS+'general_boss.orderedmap',BOSS+'boss_level.orderedmap',BOSS+'general_boss_variable.orderedmap','master/battle/zone.orderedmap'):
        old=p.rawmap(chain.get(('common',p.hrel(n))));new=p.rawmap(assets[('common',p.hrel(n))])
        for k,v in old.items():
            if not k.startswith(('mod_fb_','mod_five_boss_')):assert new[k]==v,(n,k)

    character=p.readj(d/'server-data/lens0909_character_rows.json')
    for n,rows in character.items():srv(n).update(copy.deepcopy(rows))
    for base,ext in [('character.json','character_rank_p5b.json'),('cdndata/character.json','cdndata/character_rank_p5b.json'),('cdndata/character_text.json','cdndata/character_text_rank_p5b.json'),('mana_node.json','mana_node_cnmod.json'),('mana_node.json','mana_node_rank_p5b.json')]:
        for k in character[base]:
            if k in srv(ext):srv(ext)[k]=copy.deepcopy(srv(base)[k])
    effective={**srv('gacha.json'),**srv('gacha_cnmod.json'),**srv('gacha_rank_p5b.json')}
    pool=copy.deepcopy(effective['990002']);oldpool=copy.deepcopy(pool)
    rows=pool['pool']['1'];assert len(rows)==286 and sum(r['odds'] for r in rows)==950000
    donor_pool=p.readj(d/'server-data/lens0909_gacha_rows.json')['gacha.json']['990002']
    summer=copy.deepcopy(next(x for x in donor_pool['pool']['1'] if x['id']==149990))
    summer.update(odds=0,rarity=0,isExchangeable=False,isRateUp=False)
    assert not any(r['id']==149990 for r in rows);rows.append(summer)
    assert rows[:-1]==oldpool['pool']['1']
    for n in ('gacha.json','gacha_cnmod.json','gacha_rank_p5b.json'):
        if '990002' in srv(n):srv(n)['990002']=copy.deepcopy(pool)
    key=('common',p.hrel(RACE));logical[key]=RACE
    outer=p.rawmap(chain.get(key));assert len(outer)==1;name=next(iter(outer));inner=p.rawmap(outer[name])
    assert len(inner)==286;assert '286' not in inner
    inner['286']=p.packcsv([['149990','5','0','false','true','false','false']])
    assets[key]=p.packmap({name:p.packmap(inner)})
    # Pool notes retain our own policies, with an explicit preview-only notice.
    note='rich_text/cnmod_ashen_verdict_gacha_note.html.deflate';key=('common',p.hrel(note));logical[key]=note
    text=p.wf_atf.inflate(chain.get(key)).decode('utf-8')
    text+='\n<p>・夏日白虎仅作角色预览展示，抽取权重为 0，不可抽取或兑换。</p>\n'
    assets[key]=p.wf_atf.deflate(text.encode('utf-8'))
    jobs=[];receipts=[]
    for key,raw in sorted(assets.items()):
        if raw[1:4] in (b'png',b'PNG'):
            assert raw[:8]==p.wf_assets.PNG_FAKE
            p.Image.open(io.BytesIO(p.wf_assets.png_decode_stored(raw))).load()
        if key[0]!='android':continue
        n=logical[key];pngkey=('medium',p.hrel(n.replace('.atf.deflate','.png')))
        png=p.wf_assets.png_decode_stored(assets[pngkey]);out=w/'ios'/key[1]
        if out.exists():
            receipt=p.wf_atf.validate_cutin_platform_pair(p.wf_atf.inflate(raw),p.wf_atf.inflate(out.read_bytes()),png)
            receipts.append({'logical':n,'path':str(out),'sha256':p.sha(out.read_bytes()),'png_sha256':p.sha(png),'pair':receipt})
            continue
        jobs.append((n,png,raw,str(out)))
    print(f'Prepared characters/difficulty/pool; solo scaling unchanged; encoding {len(jobs)} iOS textures, reused {len(receipts)} verified pairs',flush=True)
    with ProcessPoolExecutor(max_workers=4) as pool_executor:
        futures={pool_executor.submit(p.ios_job,j):j[0] for j in jobs}
        for future in as_completed(futures):
            receipt=future.result();receipts.append(receipt);print('iOS complete: '+receipt['logical'],flush=True)
    for receipt in receipts:
        key=('ios',p.hrel(receipt['logical']));logical[key]=receipt['logical'];assets[key]=Path(receipt['path']).read_bytes()
    inventory=[]
    for key,raw in sorted(assets.items()):
        old=chain.get(key)
        if raw==old:continue
        out=w/'resources'/p.ROOTS[key[0]]/key[1];out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(raw)
        inventory.append({'root':key[0],'rel':key[1],'logical':logical[key],'member':p.member(key),'sha256':p.sha(raw),'before_sha256':p.sha(old) if old else None,'bytes':len(raw)})
    server_inventory=[]
    for n,obj in sorted(server.items()):
        before=server_before[n]
        if json.loads(before)==obj:continue
        out=w/'server/assets'/n;p.savej(out,obj)
        server_inventory.append({'path':'assets/'+n,'before_sha256':p.sha(before),'sha256':p.sha(out.read_bytes())})
    for name,obj in {'resources':inventory,'server-files':server_inventory,'source-receipts':source,'shared-table-changes':changes,
        'current-resource-sources':chain.reads,'ios-pairs':receipts,'recovered-paths':recovered,'approved-gacha':pool,
        'boss-parity':parity,'boss-hp-adjustments':hp_receipts,'watch-aliases':aliases,'resource-decisions':{'accepted':selected,'deferred':deferred},
        'prepare-report':{'baseline_version':chain.tail,'baseline_manifest_sha256':p.sha(chain.manifest_bytes),'resources':len(inventory),'server_files':len(server_inventory),'status':'candidate'}}.items():p.savej(w/(name+'.json'),obj)
    print(f'Candidate: {len(inventory)} resources, {len(server_inventory)} server JSON files',flush=True)

if __name__=='__main__':main()
