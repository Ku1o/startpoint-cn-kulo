"""Replace only finite normal/EX acquisition sources from merged reward data."""
from __future__ import annotations
import copy
import csv
import io
from collections import defaultdict
from wf_abyss_modes import NORMAL_EVENT, EX_EVENT

def chance(value, floor):
    if isinstance(value,dict):
        value=value['start']+value.get('per_round',0)*(floor-value.get('base_round',floor))
    return max(0,min(1,float(value)))

def required_sources(configs: dict, folders: dict) -> dict[str,list[list[str]]]:
    result=defaultdict(lambda:defaultdict(float))
    def add(item,event,floor,weight):
        if weight>0:
            result[str(item)][('16',str(event),'',str(floor),str(event*1000+floor))]+=weight
    for event in (NORMAL_EVENT,EX_EVENT):
        config=configs[str(event)]
        if config.get('pool_draws',0):
            raise ValueError('weighted pool requires an explicit acquisition contract')
        for row in config.get('per_round_drops',[]):
            if row['type']!='item':raise ValueError('non-item reward requires its own search table')
            lo,hi=row.get('rounds',[1,30])
            if not 1<=lo<=hi<=30:raise ValueError('compatibility endless cannot be an item source')
            for floor in range(lo,hi+1):
                if floor in row.get('exclude_rounds',[]):continue
                slots=row.get('slots',1)
                guarantee=row.get('guaranteed_slots',0 if 'chance' in row else slots)
                if not 0<=guarantee<=slots:raise ValueError('invalid drop slots')
                weight=row.get('count',1)*(guarantee+(slots-guarantee)*chance(row.get('chance',1),floor))
                add(row['id'],event,floor,weight)
        for row in folders[str(event)]['1']:
            add(row['id'],event,30,row['count'])
        for row in config.get('folder_clear_chance',[]):
            add(row['id'],event,30,row['count']*chance(row['chance'],30))
        for row in config.get('folder_clear_random',[]):
            pool=row['pool']
            if not pool or len(set(pool))!=len(pool):raise ValueError('invalid random pool')
            weight=sum(row['pick'])/2/len(pool)*sum(row['count'])/2*chance(row.get('chance',1),30)
            for item in pool:add(item,event,30,weight)
    return {item:[list(ref)+[format(weight,'.12g')] for ref,weight in refs.items()] for item,refs in result.items()}

def owned(row):
    return len(row)>=5 and row[0]=='16' and row[1] in (str(NORMAL_EVENT),str(EX_EVENT)) and row[3].isdigit() and 1<=int(row[3])<=30

def replace_sources(table: dict, expected: dict) -> dict:
    result=copy.deepcopy(table)
    for item in set(table)|set(expected):
        leaf=table.get(item,'')
        if isinstance(leaf,bytes):leaf=leaf.decode('utf-8')
        old=list(csv.reader(io.StringIO(leaf))) if leaf else []
        rows=[row for row in old if not owned(row)]+expected.get(item,[])
        stream=io.StringIO()
        csv.writer(stream,lineterminator='\n').writerows(rows)
        result[item]=stream.getvalue().rstrip('\n')
    validate_sources(result,expected)
    return result

def validate_sources(table: dict, expected: dict):
    actual={}
    for item,leaf in table.items():
        if isinstance(leaf,bytes):leaf=leaf.decode('utf-8')
        rows=[row for row in csv.reader(io.StringIO(leaf)) if owned(row)]
        if rows:actual[item]=sorted(rows)
    wanted={item:sorted(rows) for item,rows in expected.items() if rows}
    if actual!=wanted:raise ValueError('missing, stale or inconsistent normal/EX acquisition source')
