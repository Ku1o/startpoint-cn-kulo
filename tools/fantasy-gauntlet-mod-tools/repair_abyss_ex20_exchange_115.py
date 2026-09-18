"""Sparse, preimage-checked 1.4.114 -> 1.4.115 repair; never writes pristine CDN.

Clone the complete ordinary shark family with exact identifier substitutions.
Keep official resources immutable and preserve native trial absolute thresholds.
"""
from __future__ import annotations
import argparse, copy, csv, hashlib, io, json, os, sys, zipfile, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.update(WF_SERVER_DIR=str(ROOT), WF_CDN_DIR=str(ROOT/'.cdn/cn'), WF_LIVE_CDN='1')
import wf_quest_lib as q
import wf_live_cdn as live
import wf_rogue_build as rb
import wf_dsl, wf_dsl_sig, wf_quest_time_revision as rev
sys.path.insert(0, str(ROOT/'tools/lens-integration'))
from prepare_content import rawmap, packmap

SHA = lambda b: hashlib.sha256(b).hexdigest()
B = 'master/battle/boss/'
SUFFIX = '.action.dsl.amf3.deflate'
NAMES = ['general_boss','general_boss_state','general_boss_variable','boss_level',
         'funnel_level','funnel/general_funnel','funnel/general_funnel_state',
         'funnel/general_funnel_variable','general_enemy_watch']
FIELD = 'master/battle/field_data.orderedmap'
ZONE = 'master/battle/zone.orderedmap'
QUEST = rev.RUSH_QUEST_LOGICAL
ODDS = 'master/gacha_odds/cnmod_abyss_limited_gacha_character_5.orderedmap'
NOTE = 'rich_text/cnmod_abyss_limited_gacha_note.html.deflate'

def walk(x):
    yield x
    if isinstance(x, dict):
        for v in x.values(): yield from walk(v)
    elif isinstance(x, list):
        for v in x: yield from walk(v)

def exact(x, mapping):
    if isinstance(x, dict): return {mapping.get(k,k):exact(v,mapping) for k,v in x.items()}
    if isinstance(x, list): return [exact(v,mapping) for v in x]
    return mapping.get(x,x) if isinstance(x,str) else x

def rows_exact(x, mapping):
    if isinstance(x,dict): return {mapping.get(k,k):rows_exact(v,mapping) for k,v in x.items()}
    rows=list(csv.reader(io.StringIO(x)))
    changed=[[','.join(mapping.get(s,s) for s in c.split(',')) for c in row] for row in rows]
    if changed == rows: return x
    out=io.StringIO(newline='');csv.writer(out,lineterminator='\n').writerows(changed)
    return out.getvalue().rstrip('\n')

def sparse(old, node):
    """Retain each untouched compressed leaf byte-for-byte."""
    if old is not None and q.parse_node(old)==node: return old
    if isinstance(node,dict):
        prior=rawmap(old) if old is not None else {}
        return packmap({k:sparse(prior.get(k),v) for k,v in node.items()})
    return q.build_node(node)

def deflate(b):
    c=zlib.compressobj(9,zlib.DEFLATED,-15);return c.compress(b)+c.flush()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,required=True)
    ap.add_argument('--apply',action='store_true');args=ap.parse_args()
    work=args.work.resolve();assert not work.is_relative_to((ROOT/'.cdn').resolve())
    work.mkdir(parents=True,exist_ok=True)
    mp=ROOT/'assets/asset-patch/manifest.json';manifest_bytes=mp.read_bytes();manifest=json.loads(manifest_bytes)
    assert manifest['cdn_version']=='1.4.114', 'repair requires exact preceding release'
    before={}; provenance={};payload={}
    def read(logical):
        if logical not in before:
            v=live.read_logical(logical);before[logical]=v.data
            provenance[logical]={'archive':str(v.archive.relative_to(ROOT)) if v.archive.is_relative_to(ROOT) else v.archive.name,
                                 'member':v.member,'sha256':SHA(v.data)}
        return before[logical]
    tables={name:q.parse_node(read(B+name+'.orderedmap')) for name in NAMES}
    originals=copy.deepcopy(tables)
    actors={'shark'}|{k for k in tables['funnel/general_funnel'] if 'shark' in k and 'score_event' not in k}
    actions={};queue=set()
    for name in ('general_boss','funnel/general_funnel'):
        for actor in actors & tables[name].keys():
            for row in walk(tables[name][actor]):
                if isinstance(row,str):
                    for cell in rb.cells(row):queue.update(v for v in cell.split(',') if v.startswith('battle/action/'))
    while queue:
        path=queue.pop()
        if path in actions:continue
        tree=wf_dsl.parse_dsl(zlib.decompress(read(path+SUFFIX),-15))['tree']
        wf_dsl_sig.validate_action_dsl(tree);actions[path]=tree
        queue.update(v.removesuffix(SUFFIX) for v in walk(tree) if isinstance(v,str) and v.startswith('battle/action/'))
    assert len(actors)==21 and len(actions)==68
    assert {v[1] for t in actions.values() for v in walk(t) if isinstance(v,list) and len(v)==2 and v[0]=='Funnel'} <= actors
    mapping={a:'mod_ex20_'+a for a in actors}
    mapping.update({a:'battle/action/enemy/action/mod_ex20/'+a.rsplit('/',1)[1] for a in actions})
    inverse={v:k for k,v in mapping.items()};assert len(inverse)==len(mapping)
    for path,tree in sorted(actions.items()):
        new=exact(tree,mapping)
        assert exact(new,inverse)==tree
        wf_dsl_sig.validate_action_dsl(new)
        raw=wf_dsl.encode_amf3(new);assert wf_dsl.parse_dsl(raw)['tree']==new
        payload[mapping[path]+SUFFIX]=deflate(raw)
    # Ordinary boss + every auxiliary, state, variable and HP row are private.
    scale=float(rb.cells(tables['boss_level']['mod_abyss_ex_boss20'])[2])/float(rb.cells(tables['boss_level']['shark'])[2])
    trials=[]
    for name in NAMES[:-1]:
        for actor in sorted(actors & originals[name].keys()):
            source=originals[name][actor];new=rows_exact(source,mapping)
            assert rows_exact(new,inverse)==source
            if name=='funnel_level':
                cells=rb.cells(new);cells[2]=format(float(cells[2])*scale,'.12g');new=rb.join(cells,False)
            if name=='funnel/general_funnel_state':
                baseline=copy.deepcopy(new)
                new=rb.scale_general_damage_checks(new,source_max_hp=1,target_max_hp=scale)
                for a,b in zip(rb.general_damage_check_records(baseline),rb.general_damage_check_records(new)):
                    assert abs(a['percentage']-b['percentage']*scale)<1e-7
                    assert a['row_without_percentage']==b['row_without_percentage']
                    trials.append({'actor':mapping[actor],'state':a['state_id'],'before_percent':a['percentage'],'after_percent':b['percentage'],'hp_scale':scale})
            tables[name][mapping[actor]]=new
    assert len(trials)==9
    # Preserve the tower's scaled HP, restrictions and entry actions.
    newboss=rows_exact(originals['general_boss']['mod_abyss_ex_boss20'],mapping)
    for level,row in newboss.items():
        cells=rb.cells(row)
        score='battle/action/enemy/action/boss_shark/boss_shark_score_event$pre_action'
        parts=cells[109].split(',');assert parts.count(score)==1
        parts[parts.index(score)]=mapping['battle/action/enemy/action/boss_shark/boss_shark$pre_action']
        cells[109]=','.join(parts);newboss[level]=rb.join(cells,False)
    tables['general_boss'][mapping['shark']]=newboss
    tables['boss_level'][mapping['shark']]=originals['boss_level']['mod_abyss_ex_boss20']
    # Clone watch self + partner branches, dropping score-only partners.
    for kind,group in originals['general_enemy_watch'].items():
        for actor,branch in group.items():
            if actor not in actors:continue
            branch=copy.deepcopy(branch)
            for routine,partners in branch.items():
                for partner_kind,partner_codes in partners.items():
                    for code in list(partner_codes):
                        if 'score_event' in code:del partner_codes[code]
                        else:assert code in actors,(actor,code)
            tables['general_enemy_watch'][kind][mapping[actor]]=rows_exact(branch,mapping)
    # No existing official or private family is overwritten.
    for name,table in tables.items():
        if name=='general_enemy_watch':
            assert all(table[kind][k]==v for kind,group in originals[name].items() for k,v in group.items()),name
        else:
            assert all(table[k]==v for k,v in originals[name].items()),name
        raw=sparse(read(B+name+'.orderedmap'),table)
        if raw!=before[B+name+'.orderedmap']:payload[B+name+'.orderedmap']=raw
    for color in ('blue','brown','red'):
        for row in tables['funnel/general_funnel'][mapping['shark_'+color]].values():
            assert rb.cells(row)[32]==mapping['shark']
    for logical in (FIELD,ZONE,QUEST):read(logical)
    fields=q.parse_node(before[FIELD]);zones=q.parse_node(before[ZONE]);quests=q.parse_node(before[QUEST])
    field=rb.cells(fields['mod_abyss_ex_f20']);newfield='mod_abyss_ex_f20_115';newzone='mod_abyss_ex_z20_115'
    # The normal battle uses exactly the existing shark terrain and layer set.
    native=[f for f,row in fields.items() if rb.cells(row)[:2]==field[:2] and any('shark'==v for r in zones.get(rb.cells(row)[2],{}).values() for v in rb.cells(r))]
    assert native, 'no ordinary shark battle on the exact terrain'
    read(field[1]+'.amf3.deflate')
    field[2]=newzone;fields[newfield]=rb.join(field,False)
    zones[newzone]=rows_exact(zones['mod_abyss_ex_z20'],{'mod_abyss_ex_boss20':mapping['shark']})
    row=rb.cells(quests['700100']['20']);assert row.count('mod_abyss_ex_f20')==1
    row[row.index('mod_abyss_ex_f20')]=newfield
    quests['700100']['20']=rb.join(row,False)
    for logical,table in ((FIELD,fields),(ZONE,zones),(QUEST,quests)):payload[logical]=sparse(before[logical],table)
    # The exchange flag alone changes. Odds and all other pool metadata survive.
    server={};server_before={}
    for rel in ('assets/gacha.json','assets/gacha_cnmod.json'):
        raw=(ROOT/rel).read_bytes();obj=json.loads(raw);prior=copy.deepcopy(obj)
        pool=obj['990001']
        items=[v for rows in pool['pool'].values() for v in rows]
        for ident in (149988,149990):
            found=[v for v in items if v['id']==ident];assert len(found)==1 and found[0]['isExchangeable'] is False
            found[0]['isExchangeable']=True
        server[rel]=(json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode();server_before[rel]=SHA(raw)
        (work/'before'/rel).parent.mkdir(parents=True,exist_ok=True);(work/'before'/rel).write_bytes(raw)
    odds=q.parse_node(read(ODDS));changes=0
    def exchange(node):
        nonlocal changes
        if isinstance(node,dict):return {k:exchange(v) for k,v in node.items()}
        rows=list(csv.reader(io.StringIO(node)));touched=False
        for row in rows:
            if row[0] in ('149988','149990'):
                assert row[5]=='false';row[5]='true';changes+=1;touched=True
        if not touched:return node
        out=io.StringIO(newline='');csv.writer(out,lineterminator='\n').writerows(rows)
        return out.getvalue().rstrip('\n')
    payload[ODDS]=sparse(before[ODDS],exchange(odds));assert changes==2
    note=zlib.decompress(read(NOTE),-15).decode()
    old='新增七位、夏日白、盾牌座与十五位小 Boss 不可兑换；校园碧安卡、校园希尔媞、校园奈芙提姆、水杰拉尔、秋灯九尾可以使用250点兑换点数兑换。'
    new='新增七位与十五位小 Boss 不可兑换；夏日白、盾牌座、校园碧安卡、校园希尔媞、校园奈芙提姆、水杰拉尔、秋灯九尾可以使用250点兑换点数兑换。'
    assert note.count(old)==1;payload[NOTE]=deflate(note.replace(old,new).encode())
    members={'production/upload/'+q.hashed_rel(k):v for k,v in payload.items()}
    markers=rev.quest_time_revisions(members)
    report={'version':'1.4.115','actors':mapping,'native_fields':native,'hp_scale':scale,'trials':trials,
            'provenance':provenance,'resources':{k:{'sha256':SHA(v),'member':'production/upload/'+q.hashed_rel(k)} for k,v in payload.items()},
            'server_preimages':server_before,'quest_time_revisions':{'rush:700100':markers['rush:700100']},
            'save_impact':'No schema, saved character IDs or reward changes. Only EX time-record revision advances; challenge progression is retained.',
            'device_verified':False,'cloud_deployed':False}
    for logical,raw in payload.items():
        path=work/'payloads'/q.hashed_rel(logical);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    (work/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    if args.apply:
        assert mp.read_bytes()==manifest_bytes
        for rel,digest in server_before.items():assert SHA((ROOT/rel).read_bytes())==digest
        name='pinball-1.4.114-1.4.115-1-abyss-ex20-exchange.zip';dest=ROOT/'assets/asset-patch/active'/name
        assert not dest.exists()
        with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for key,raw in sorted(members.items()):
                zi=zipfile.ZipInfo(key,(2026,9,18,0,0,0));zi.compress_type=zipfile.ZIP_DEFLATED;z.writestr(zi,raw)
        with zipfile.ZipFile(dest) as z:assert z.testzip() is None and {k:z.read(k) for k in z.namelist()}==members
        integrity={'name':name,'size':dest.stat().st_size,'sha256':SHA(dest.read_bytes()),'members':len(members),'files':sorted(members)}
        audit='assets/asset-patch/audit/abyss-ex20-exchange-1.4.115'
        manifest['patches'].append({'id':'abyss-ex20-exchange-20260918','type':'patch','name':'EX三兄弟与深渊角色兑换修复',
          'description':'第20关改用普通讨伐三兄弟的独立完整战斗族；开放夏日白与盾牌座250点兑换。',
          'depends_on':'1.4.114','version':'1.4.115','enabled':True,'archive':name,'archive_size':integrity['size'],
          'archive_integrity':[integrity],'files':sorted(members),'quest_time_revisions':report['quest_time_revisions'],
          'changes':['三兄弟恢复传伤和阶段切换，保留本关血量与限制。','两名角色开放兑换，抽取概率保持不变。','仅EX成绩版本更新，保留普通塔成绩及挑战进度。'],
          'audit':{'directory':audit}})
        manifest['cdn_version']='1.4.115'
        for rel,raw in server.items():(ROOT/rel).write_bytes(raw)
        mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
        (ROOT/audit).mkdir(parents=True,exist_ok=True)
        (ROOT/audit/'report.json').write_bytes((work/'report.json').read_bytes())
        rev.validate_current_chain(ROOT)
    print(json.dumps({'applied':args.apply,'resources':len(payload),'actors':len(actors),'actions':len(actions),'trials':len(trials)},ensure_ascii=False))

if __name__=='__main__':main()
