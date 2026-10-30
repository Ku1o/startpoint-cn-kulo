"""Compose 1.4.258 -> 1.4.344 from explicit baseline and pinned source inputs.

The caller owns baseline resolution, external-input identity checks and output
serialization. This module returns sparse stored bytes and never writes files,
opens a candidate archive, invokes Git, or changes a manifest. Unknown historical
logical names are represented by the declared @sha1/<relative> key convention.
"""
from __future__ import annotations

import base64
import collections
import copy
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import struct
import sys
from types import SimpleNamespace
import zipfile
import zlib

ROOTS = {'common': 'upload', 'medium': 'medium_upload', 'small': 'small_upload',
         'android': 'android_upload', 'ios': 'ios_upload'}
REVERSE = {v: k for k, v in ROOTS.items()}
HASHED_PREFIX = '@sha1/'
codec = None


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _load_support(repo):
    """Use the existing repository orderedmap and platform/image codecs."""
    global codec
    source = Path(repo) / 'tools/rebuild_character_edge.py'
    module_spec = importlib.util.spec_from_file_location('_release344_rows', source)
    rows = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(rows)
    codec = SimpleNamespace(rawmap=rows.rawmap, packmap=rows.packmap,
                            csvrows=_csvrows, packcsv=_packcsv, sha=sha)
    sys.path.insert(0, str(Path(repo) / 'tools/fantasy-gauntlet-mod-tools'))
    import wf_assets
    import wf_mod_tool
    import wf_atf
    import wf_battle_atlas_repack
    from PIL import Image
    return SimpleNamespace(assets=wf_assets, core=wf_mod_tool, atf=wf_atf,
                           atlas=wf_battle_atlas_repack, Image=Image)


def _csvrows(raw):
    return list(csv.reader(io.StringIO(zlib.decompress(raw).decode('utf-8'))))


def _packcsv(rows):
    out = io.StringIO(newline='')
    csv.writer(out, lineterminator='\n').writerows(rows)
    return zlib.compress(out.getvalue().encode('utf-8'))


def _member(root, logical, support):
    if root not in ROOTS:
        raise ValueError('Unknown resource root: ' + str(root))
    if logical.startswith(HASHED_PREFIX):
        relative = logical[len(HASHED_PREFIX):]
    else:
        digest = support.core.sha1_path(logical)
        relative = digest[:2] + '/' + digest[2:]
    name = 'production/' + ROOTS[root] + '/' + relative
    _split_member(name)
    return name


def _split_member(name):
    if not re.fullmatch(r'production/(?:upload|medium_upload|small_upload|android_upload|ios_upload)/[0-9a-f]{2}/[0-9a-f]{38}', name):
        raise ValueError('Invalid stored resource member: ' + name)
    _, folder, prefix, tail = name.split('/')
    return REVERSE[folder], prefix + '/' + tail


def _map(raw):
    if raw is None:
        return None
    try:
        return codec.rawmap(raw)
    except (AssertionError, ValueError, UnicodeError, struct.error, zlib.error):
        return None


def _leaves(raw, path=()):
    mapped = _map(raw)
    if mapped is None:
        return {path: raw}
    result = {}
    for key, value in mapped.items():
        result.update(_leaves(value, path + (key,)))
    return result


def _changes(old, new, path=()):
    left, right = _map(old), _map(new)
    if left is not None and right is not None:
        result = []
        for key in dict.fromkeys([*left, *right]):
            if left.get(key) != right.get(key):
                if key not in left or key not in right:
                    result.append((path + (key,), left.get(key), right.get(key)))
                else:
                    result.extend(_changes(left[key], right[key], path + (key,)))
        return result
    return [(path, old, new)] if old != new else []


def _strip(raw, banned, path=()):
    mapped = _map(raw)
    if mapped is None:
        return raw
    result = {key: _strip(value, banned, path + (key,))
              for key, value in mapped.items() if path + (key,) not in banned}
    return raw if result == mapped else codec.packmap(result)


def _setleaf(raw, path, value):
    if not path:
        return value
    mapped = codec.rawmap(raw)
    mapped[path[0]] = _setleaf(mapped[path[0]], path[1:], value)
    return codec.packmap(mapped)


def _pr_terminal(context, spec, baseline, support):
    """Replay fixed PR archives and apply the adopted sparse exclusion policy."""
    current = {}
    bans = collections.defaultdict(set)
    restores = {}
    precontinue = {}
    excluded = {int(k): v for k, v in spec['excludedEdges'].items()}
    for edge in spec['edges']:
        version = edge['version']
        for alias in edge['archives']:
            # external() verifies the spec-declared entire source archive once.
            with zipfile.ZipFile(context.external(alias)) as archive:
                names = archive.namelist()
                if len(names) != len(set(names)):
                    raise ValueError('Duplicate source archive members: ' + alias)
                for name in names:
                    _split_member(name)
                    old = current[name] if name in current else baseline(name)
                    new = archive.read(name)
                    if version == spec['continueEdge']:
                        precontinue[name] = old
                    if version in excluded:
                        if _map(new) is None:
                            restores.setdefault(name, old)
                        else:
                            for path, before, after in _changes(old, new):
                                if any(path[:len(q)] == q for q in bans[name]):
                                    continue
                                if before is not None or after is None:
                                    raise ValueError('Excluded edge changes a pre-existing leaf')
                                bans[name].add(path)
                    current[name] = new
    final = dict(current)
    for name, raw in current.items():
        if name in restores:
            if restores[name] is None:
                final.pop(name, None)
            else:
                final[name] = restores[name]
        elif name in bans:
            final[name] = _strip(raw, bans[name])
    highest = set(spec['highestFiveIds'])
    for name, before in precontinue.items():
        left, right = _leaves(before), _leaves(final[name])
        five = '/eb/f8ef191' in name
        paths = [q for q in right if (q[:2] == ('1', '99') if five else q[:1] == ('300097',))]
        expected = spec['expectedFiveLeaves'] if five else spec['expectedPumpkinLeaves']
        if len(paths) != expected:
            raise ValueError('Continue-policy leaf count differs')
        for path in paths:
            prior, rows = codec.csvrows(left[path]), codec.csvrows(right[path])
            assert len(rows) == len(prior) == 1
            column = 119 if five else 125
            quest = int(rows[0][0])
            assert rows[0][column] == '0'
            assert rows[0][:column] + rows[0][column+1:] == prior[0][:column] + prior[0][column+1:]
            terminal_ban = quest in highest if five else quest == spec['highestPumpkinId']
            rows[0][column] = '0' if terminal_ban else prior[0][column]
            final[name] = _setleaf(final[name], path, codec.packcsv(rows))
    for name, paths in bans.items():
        surviving = _leaves(final[name])
        assert all(not any(q[:len(path)] == path for q in surviving) for path in paths)
    for name, prior in restores.items():
        assert final.get(name) == prior
    def get(root, logical):
        name = _member(root, logical, support)
        return final[name] if name in final else baseline(name)
    ios_expected = {r['logical']: r for r in spec['iosExpected']}
    for logical in spec['iosCutins']:
        name = _member('ios', logical, support)
        assert name not in final
        pnglogical = logical.removesuffix('.atf.deflate') + '.png'
        png = support.assets.png_decode_stored(get('medium', pnglogical))
        android = support.atf.inflate(get('android', logical))
        ios = support.atf.build_cutin_atf_ios(png, android)
        support.atf.validate_cutin_platform_pair(android, ios, png)
        raw = support.atf.deflate(ios)
        expected = ios_expected[logical]
        assert sha(raw) == expected['sha256'] and len(raw) == expected['bytes']
        final[name] = raw
    return final


def _apply_gacha(context, spec, get, put, support):
    selected_skills = {(r['root'], r['logical']): get(r['root'], r['logical'])
                       for r in spec['skillPrecedence']}
    for table in spec['tables']:
        logical = table['logical']
        before = codec.rawmap(get('common', logical))
        after = dict(before)
        for row in table['rows']:
            key = row['key']
            adopted = base64.b64decode(row['storedBase64'], validate=True)
            assert sha(adopted) == row['storedSHA256'] and len(adopted) == row['storedBytes']
            if row['nested'] and key in before:
                merged = codec.rawmap(before[key])
                merged.update(codec.rawmap(adopted))
                adopted = codec.packmap(merged)
            if logical == ITEM and key == '999023':
                cells = leaf(adopted)
                assert len(cells) == 23
                cells[3] = 'item/cnmod_halloween_surprise_2026_ticket'
                adopted = codec.packcsv([cells])
            if logical == 'master/gacha/gacha.orderedmap' and key == '990005':
                cells = leaf(adopted)
                assert len(cells) == 47 and cells[10] == '4' and cells[28] == '999023'
            after[key] = adopted
        allowed = {r['key'] for r in table['rows']}
        assert all(after[k] == v for k, v in before.items() if k not in allowed)
        assert [k for k in after if k in before] == list(before)
        put('common', logical, codec.packmap(after))
    # These source resources are from pinned original author registration edges,
    # not the historical merged candidate or a generated overlay archive.
    for row in spec['files']:
        if 'storedBase64' in row:
            raw = base64.b64decode(row['storedBase64'], validate=True)
        else:
            with zipfile.ZipFile(context.external(row['external'])) as archive:
                raw = archive.read(row['sourceMember'])
        assert len(raw) == row['bytes'] and sha(raw) == row['sha256'], row['logical']
        put(row['root'], row['logical'], raw)
    for row in spec['baselineExactDependencies']:
        assert sha(get(row['root'], row['logical'])) == row['sha256'], row['logical']
    for row in spec['smallDerivations']:
        medium = get('medium', row['logical'])
        assert sha(medium) == row['mediumSHA256'], row['logical']
        image = _image(medium, support)
        size = tuple(max(1, round(n * .7)) for n in image.size)
        assert list(size) == row['size']
        image = image.convert('RGBa').resize(size, support.Image.Resampling.LANCZOS).convert('RGBA')
        raw = _stored_image(image, support)
        assert len(raw) == row['bytes'] and sha(raw) == row['sha256'], row['logical']
        put('small', row['logical'], raw)
    for row in spec['skillPrecedence']:
        raw = selected_skills[row['root'], row['logical']]
        assert sha(raw) == row['sha256'], row['logical']
        put(row['root'], row['logical'], raw)


def _image(raw, support):
    with support.Image.open(io.BytesIO(support.assets.png_decode_stored(raw))) as image:
        image.load()
        return image.convert('RGBA')


def _stored_image(image, support, *, compress_level=None):
    out = io.BytesIO()
    options = {'optimize': True}
    if compress_level is not None:
        options['compress_level'] = compress_level
    image.save(out, 'PNG', **options)
    return support.assets.png_encode(out.getvalue())


def _apply_ticket(spec, get, put, support):
    logical, atlas = spec['logical'], spec['atlas']
    png = base64.b64decode(spec['approvedPngBase64'], validate=True)
    assert sha(png) == spec['pngSHA256']
    stored = support.assets.png_encode(png)
    assert sha(stored) == spec['storedSHA256']
    icon = _image(stored, support)
    assert icon.size == (20, 20) and icon.getchannel('A').getextrema() == (0, 255)
    before_png, before_atlas = get('common', atlas + '.png'), get('common', atlas + '.atlas.amf3.deflate')
    assert sha(before_png) == spec['beforePngSHA256']
    assert sha(before_atlas) == spec['beforeAtlasSHA256']
    image, frames = _image(before_png, support), support.atlas.decode_atlas(before_atlas)
    assert list(image.size) == spec['beforeSize']
    assert logical not in {r['n'] for r in frames}
    result = support.Image.new('RGBA', (image.width, image.height + 22))
    result.paste(image, (0, 0))
    result.paste(icon, (1, image.height + 1))
    frame = {'n': logical, 'w': 20, 'h': 20, 'x': 1, 'y': image.height + 1}
    assert frame == spec['frame'] and list(result.size) == spec['afterSize']
    after_frames = copy.deepcopy(frames) + [frame]
    after_png = support.atlas.encode_png(result)
    after_atlas = support.atlas.encode_atlas(after_frames)
    assert sha(after_png) == spec['afterPngSHA256']
    assert sha(after_atlas) == spec['afterAtlasSHA256']
    readback = _image(after_png, support)
    assert readback.crop((0, 0, *image.size)).tobytes() == image.tobytes()
    assert support.atlas.decode_atlas(after_atlas)[:-1] == frames
    put('common', logical + '.png', stored)
    put('common', atlas + '.png', after_png)
    put('common', atlas + '.atlas.amf3.deflate', after_atlas)
    trim_logical = 'master/generated/trimmed_image.orderedmap'
    trim = codec.rawmap(get('common', trim_logical))
    assert logical not in trim
    trim[logical] = codec.packcsv([['0', '0', '20', '20']])
    put('common', trim_logical, codec.packmap(trim))
    items = codec.rawmap(get('common', ITEM))
    item = leaf(items['999023'])
    assert item[3] == logical
    if spec['notice'] not in item[5]:
        item[5] += '\n' + spec['notice']
    items['999023'] = codec.packcsv([item])
    put('common', ITEM, codec.packmap(items))


def build(context, spec):
    """Return {(root, logical): stored_bytes}; no filesystem output is written.

    context.get_member(root, hashed_relative) resolves the explicit baseline.
    context.external(alias) returns a path verified against externalInputs by
    the unified entry. context.repo points at this source checkout. Only a
    genuinely absent resource returns None. Missing/corrupt enabled archives
    and resolver errors must propagate to the caller.
    """
    if (spec['baseVersion'], spec['targetVersion'], spec['hashedLogicalPrefix']) != ('1.4.258', '1.4.344', HASHED_PREFIX):
        raise ValueError('Release/baseline identity differs')
    support = _load_support(context.repo)
    before = {}
    known = {}
    def baseline(name):
        if name not in before:
            root, relative = _split_member(name)
            before[name] = context.get_member(root, relative)
        return before[name]
    current = _pr_terminal(context, spec['pr'], baseline, support)
    def get(root, logical):
        name = _member(root, logical, support)
        known[name] = (root, logical)
        raw = current[name] if name in current else baseline(name)
        if raw is None:
            raise FileNotFoundError((root, logical))
        return raw
    def put(root, logical, raw):
        if not isinstance(raw, bytes):
            raise TypeError('Stored resource must be bytes')
        name = _member(root, logical, support)
        known[name] = (root, logical)
        current[name] = raw
    _apply_gacha(context, spec['gacha'], get, put, support)
    native = spec['native']
    frozen = native['frozenClosedInput']
    closed = native['closedProducts']
    assert sorted(closed['closedWeaponIds']) == frozen['closedWeaponIds']
    assert sorted(closed['closedWeaponShopIds']) == frozen['closedWeaponShopIds']
    assert sorted([int(x['id']), int(x['weaponId'])] for x in closed['weaponShopProducts']) == frozen['productWeaponPairs']
    _apply_native(get, put, native['shop'], native['rewards'],
                  closed_boss_content=closed,
                  scoped_client_display_contract=native['nameplateCarrier'])
    _apply_ticket(spec['ticket'], get, put, support)
    result = {}
    for name, raw in current.items():
        if raw == baseline(name):
            continue
        if name in known:
            key = known[name]
        else:
            root, relative = _split_member(name)
            key = (root, HASHED_PREFIX + relative)
        result[key] = raw
    return result


# Native master-table recipe retained from the adopted sparse implementation.
# Its source-only configuration and obsolete client-helper status guards are
# replaced by the exact spec product/reward identities below.
SHOP='master/shop/event_item_shop.orderedmap'
SCORE='master/reward/score_reward.orderedmap'
RARE='master/reward/rare_score_reward.orderedmap'
SEARCH='master/search/item_quest_search.orderedmap'
ITEM='master/item/item.orderedmap'
RUSH='master/quest/event/rush_event_quest.orderedmap'
BOSS_SHOP='master/shop/boss_coin_shop.orderedmap'
BOSS_CATEGORY='master/shop/boss_coin_shop_category.orderedmap'
DEGREE='master/degree/degree.orderedmap'
WATER_NOTE='【本次更新奖励】本次奖励启用后，所有玩家（含此前已通关者）首次成功通关深渊连战EX第30战，可获得普通状态的水属性杰拉德1份。失败或退出不计；领取后再次通关不重复获得。原有进度、成绩与通塔奖励保留。'
CLOSED_ITEMS={'10000320','10000302'}

def leaf(data):
    rows=codec.csvrows(data)
    assert len(rows)==1, 'one row expected'
    return rows[0]

def edit_path(data,path,fn):
    if not path:return fn(data)
    table=codec.rawmap(data);key=str(path[0]);assert key in table,(path,'missing native key')
    changed=edit_path(table[key],path[1:],fn)
    if changed==table[key]:return data
    table[key]=changed;return codec.packmap(table)

def flat_rows(data):
    return {k:leaf(v) for k,v in codec.rawmap(data).items()}

def rewrite_table(data,fn):
    before=codec.rawmap(data);after={}
    for key,value in before.items():
        result=fn(key,leaf(value))
        if result is not None:after[key]=value if result==leaf(value) else codec.packcsv([result])
    return data if before==after else codec.packmap(after)

def shop_patch(raw,items,contract,degree_encoding=None):
    old=codec.rawmap(raw);table=dict(old);rows=flat_rows(raw)
    base=copy.deepcopy(rows['9730001']);assert len(base)==51 and base[:2]==['0','300097']
    wanted={str(x['shopId']):x for x in contract['shopRows']}
    assert len(wanted)==31 and contract['eventId']==300097 and contract['currency']==10009701
    # Replace only this event's product set. Other events remain byte-identical.
    for key,row in rows.items():
        if row[:2]==['0','300097'] and key not in wanted:table.pop(key)
    for sort,(key,spec) in enumerate(wanted.items(),1):
        reward=spec['reward'];kind=str(reward['type']);rid=str(reward.get('id',''))
        template=rows.get(key)
        if template is None:
            template=next((r for r in rows.values() if r[32]==kind and (r[33]==rid if rid else True)),base)
        row=copy.deepcopy(template)
        # Preserve the event's existing date and visibility gates. Neither the
        # draft nor a data update assigns an activity start time.
        row[0:3]=base[0:3];row[26:29]=base[26:29]
        for col in [3,4,5,6,12,15,17,20,22,24,31]:row[col]='(None)'
        for col in [16,21,23,25]:row[col]=''
        row[7]=spec['name'];row[8]=rows[key][8] if key in rows else key
        row[9]='1';row[10]=str(sort);row[11]=f"万圣活动兑换：每份{spec['name']}，消耗{spec['price']}枚万圣糖果，累计限购{spec['stock']}份。"
        if kind=='0':
            assert rid in items,('missing item definition',rid)
            row[13]=items[rid][3];row[14]=items[rid][17]
        elif kind=='1':row[13]='item/spends/ex_point/ex_point';row[14]='5'
        elif kind=='2':row[13]='scene/general/sprite_sheet/mana_a';row[14]='5'
        elif kind=='3':assert rid=='149985';row[13]=base[13];row[14]=base[14]
        else:raise AssertionError(('unreviewed shop reward type',kind))
        row[18]='10009701';row[19]=str(spec['price']);row[29]=row[30]=str(spec['stock'])
        row[32]=kind;row[33]=rid;row[34]=str(reward.get('count',1))
        # Clear all subsequent rewards, including stale donor outputs.
        for start in [35,38,41,44,47]:row[start]='(None)';row[start+1]=row[start+2]=''
        row[50]='false';table[key]=codec.packcsv([row])
    for spec in contract['nameplates']:
        key=str(spec['shopId']);row=leaf(table[key]);assert len(row)==51
        row[15]='0';row[16]=str(spec['userCost']['amount']);row[29]=row[30]='1'
        row[11]='玩家称号，累计限购1次。'
        if degree_encoding:
            # Reader-verified mapping only. Native enum is distinct from the
            # server ShopItemRewardType enum.
            row[int(degree_encoding['typeColumn'])]=str(degree_encoding['typeValue'])
            row[int(degree_encoding['idColumn'])]=str(spec['rewards'][0]['id'])
        table[key]=codec.packcsv([row])
    return codec.packmap(table)

def apply_scoped_nameplate_carrier(raw,shop_contract,display_contract,degree_definitions):
    """Encode the adopted existing native PassCardPoint presentation carrier.

    This deliberately does not claim native enum6 means Degree, does not place
    a degree ID in c33, and never grants/changes local player state.
    """
    expected={9700130:(9911401,44044),9700131:(9911403,33333),9700132:(9911404,6666666)}
    actual={int(x['shopId']):(int(x['degreeId']),int(x['price'])) for x in display_contract['products']}
    assert actual==expected and all(x['stock']==1 for x in display_contract['products'])
    assert len(display_contract['products'])==3
    assert display_contract['nativeTable']==SHOP
    assert display_contract['nativeRewardColumns']=={'32':'6','33':'(None)','34':'1'}
    server={int(x['shopId']):x for x in shop_contract['nameplates']}
    table=codec.rawmap(raw)
    for key,(degree,price) in expected.items():
        definition=leaf(degree_definitions[str(degree)])
        assert len(definition)==9
        spec=server[key]
        assert spec['rewards']==[{'count':1,'id':degree,'type':5}] and spec['stock']==1 and spec['userCost']=={'amount':price,'type':0}
        row=leaf(table[str(key)]);assert len(row)==51 and row[8]==str(key)
        fixed={0:'6',1:'700099',2:'11',7:definition[2],11:f'玩家称号。消耗{price}星导石兑换，每人累计限购1次。',13:'item/etc/degree',14:'5',15:'0',16:str(price),29:'1',30:'1',32:'6',33:'(None)',34:'1'}
        for column,value in fixed.items():row[column]=value
        assert all(row[start] in ['', '(None)'] for start in [35,38,41,44,47]),'unexpected additional nameplate reward carrier'
        table[str(key)]=codec.packcsv([row])
    return codec.packmap(table)

def patch_reward_groups(raw,groups):
    old=codec.rawmap(raw);out=dict(old)
    for group,rows in groups.items():
        key=str(group);inner=codec.rawmap(old[key]) if key in old else {}
        # Explicit group ownership includes replacements/removals of its rows.
        assert rows and len({str(x['position']) for x in rows})==len(rows)
        packed={str(x['position']):codec.packcsv([x['nativeRow']]) for x in rows}
        out[key]=codec.packmap(packed)
    return codec.packmap(out)

def remove_closed_rewards(score_raw,rare_raw):
    score=codec.rawmap(score_raw);rare=codec.rawmap(rare_raw);removed=[]
    for group,data in list(rare.items()):
        inner=codec.rawmap(data);new={}
        for key,value in inner.items():
            row=leaf(value)
            if (row[1]=='0' and row[2] in CLOSED_ITEMS) or (row[1]=='2' and row[2]=='139988') or (row[1]=='1' and row[2]=='5139881'):
                removed.append({'table':'rare','path':[group,key],'row':row})
            else:new[key]=value
        if new!=inner:rare[group]=codec.packmap(new)
    empty={group for group,data in rare.items() if not codec.rawmap(data)}
    for group,data in list(score.items()):
        inner=codec.rawmap(data);new={}
        for key,value in inner.items():
            row=leaf(value)
            closed=(row[1]=='0' and row[2]=='0' and row[3] in CLOSED_ITEMS) or (row[1]=='1' and row[6] in empty)
            if closed:removed.append({'table':'score','path':[group,key],'row':row})
            else:new[key]=value
        if new!=inner:score[group]=codec.packmap(new)
    # Definitions of items/characters and all recipe input costs stay intact.
    return codec.packmap(score),codec.packmap(rare),removed

def patch_boss_odds(get,put,contract):
    gacha=flat_rows(get('common','master/gacha/gacha.orderedmap'))
    banned=set(map(str,contract['bossRemoval']['ids']));assert len(banned)==25 and '169980' not in banned
    tables={name for gid in ['990001','990002'] for name in gacha[gid][14:17]};audit=[]
    for name in sorted(tables):
        logical=f'master/gacha_odds/{name}.orderedmap';before=get('common',logical);outer=codec.rawmap(before);after=dict(outer)
        assert name in outer,('odds group shape drift',name)
        inner=codec.rawmap(outer[name]);kept={};removed=[]
        for key,value in inner.items():
            row=leaf(value)
            if row[0] in banned:removed.append(int(row[0]))
            else:kept[key]=value
        if removed:after[name]=codec.packmap(kept);put('common',logical,codec.packmap(after))
        audit.append({'logical':logical,'removed':removed,'preservedRows':len(kept),'weightSemantics':'unchanged surviving relative weights; server must use same filtered entries'})
    return audit

def remove_closed_boss_products(raw,contract=None):
    """Remove exactly the54 frozen weapon products; retain shared categories."""
    assert contract is not None, 'explicit closed-product contract required'
    ids=set(map(str,contract['closedWeaponShopIds']));weapons=set(map(str,contract['closedWeaponIds']))
    assert len(ids)==len(weapons)==54,'exact54 closed weapon/product contract required'
    source={str(x['id']):str(x['weaponId']) for x in contract['weaponShopProducts']}
    assert set(source)==ids and set(source.values())==weapons
    before=codec.rawmap(raw);after=dict(before);removed=[]
    for key in sorted(ids,key=int):
        if key not in after:continue  # Idempotent application after final closure.
        row=leaf(after[key]);assert len(row)>34 and row[32:35]==['4',source[key],'1'],('closed product reward identity drift',key,row[32:35])
        removed.append({'shopId':int(key),'weaponId':int(source[key]),'category':int(row[0])})
        del after[key]
    assert all(after[k]==v for k,v in before.items() if k not in ids)
    return (raw if after==before else codec.packmap(after)),removed

def _apply_native(get_terminal,set_terminal,shop_contract,reward_contract,degree_encoding=None,closed_boss_content=None,scoped_client_display_contract=None):
    """Patch only declared rows and return resource/row evidence.

    reward_contract: {scoreGroups:{id:[{position,nativeRow}]},
      rareGroups:{id:[{position,nativeRow}]}}. This must be derived from final
    authoritative server data, including exact position values.
    """
    before={};after={}
    def get(root,logical):
        key=(root,logical)
        if key in after:return after[key]
        if key not in before:
            before[key]=get_terminal(root,logical);assert before[key] is not None,logical
        return before[key]
    def put(root,logical,raw):after[root,logical]=raw
    items=flat_rows(get('common',ITEM))
    degrees=codec.rawmap(get('common',DEGREE))
    shop=shop_patch(get('common',SHOP),items,shop_contract,degree_encoding)
    if scoped_client_display_contract is not None:
        assert degree_encoding is None,'scoped presentation carrier must not use fake native degree encoding'
        shop=apply_scoped_nameplate_carrier(shop,shop_contract,scoped_client_display_contract,degrees)
    put('common',SHOP,shop)
    for spec in shop_contract['nameplates']:
        key=str(spec['rewards'][0]['id']);row=leaf(degrees[key]);assert len(row)==9
        row[4]=f"获取方式：深渊连战活动商店，消耗{spec['userCost']['amount']}星导石兑换，每人累计限购1次。"
        degrees[key]=codec.packcsv([row])
    put('common',DEGREE,codec.packmap(degrees))
    assert set(map(str,reward_contract['scoreGroups'])) >= {'30009704','30009705','50105'}
    score=patch_reward_groups(get('common',SCORE),reward_contract['scoreGroups'])
    rare=patch_reward_groups(get('common',RARE),reward_contract['rareGroups'])
    score,rare,closed=remove_closed_rewards(score,rare);put('common',SCORE,score);put('common',RARE,rare)
    # Remove closed acquisition routes; a definition key with no routes is safe
    # and retains owned inventory support.
    raw=get('common',SEARCH);index=codec.rawmap(raw)
    removed_search={key:codec.csvrows(index[key]) for key in CLOSED_ITEMS if key in index}
    for key in CLOSED_ITEMS:index.pop(key,None)
    kind=str(reward_contract['adventReferenceKind'])
    assert kind.isdigit(),'reader-verified Advent QuestReferenceIdKind required'
    refs=[[kind,'300097','','4','300097004','20'],[kind,'300097','','5','300097005','200']]
    # Server quest category, shop family and client quest-reference enums are
    # distinct. The caller supplies the reader-verified native reference kind.
    old=codec.csvrows(index['10009701']) if '10009701' in index else []
    rows=[r for r in old if r[:5] not in [r[:5] for r in refs]]+refs
    index['10009701']=codec.packcsv(rows);put('common',SEARCH,codec.packmap(index))
    raw=get('common',RUSH)
    def water(data):
        row=leaf(data);assert row[0]=='700100030'
        if WATER_NOTE not in row[3]:row[3]+='\n'+WATER_NOTE
        return codec.packcsv([row])
    put('common',RUSH,edit_path(raw,['700100','30'],water))
    # Remove category97 entries from native shop navigation as well as products.
    closed_boss_products=[]
    for logical in [BOSS_SHOP,BOSS_CATEGORY]:
        raw=get('common',logical)
        if logical==BOSS_SHOP:
            new=rewrite_table(raw,lambda key,row:None if row[0]=='97' else row)
            new,closed_boss_products=remove_closed_boss_products(new,closed_boss_content)
        else:
            mp=codec.rawmap(raw);mp.pop('97',None);new=codec.packmap(mp)
        put('common',logical,new)
    odds=patch_boss_odds(get,put,shop_contract)
    changed=[]
    for (root,logical),raw in sorted(after.items()):
        if raw==before.get((root,logical)):continue
        set_terminal(root,logical,raw)
        changed.append({'root':root,'logical':logical,'before_sha256':codec.sha(before[root,logical]),'after_sha256':codec.sha(raw),'bytes':len(raw)})
    rollout=[]
    if scoped_client_display_contract is not None:rollout=[scoped_client_display_contract['nativeFlow']]
    pending=[] if degree_encoding is not None or scoped_client_display_contract is not None else ['native degree reward parser/ID carrier must be verified before final closure']
    return {'resources':changed,'closedRewardRows':closed,'removedSearch':removed_search,'bossOdds':odds,'closedBossProducts':closed_boss_products,'degreeEncodingVerified':degree_encoding is not None,'scopedClientDisplayCarrier':scoped_client_display_contract is not None,'rolloutLimitations':rollout,'pending':pending,'waterDisplay':'quest detail notice; actual native character acquisition comes from successful server settlement','runtime':False,'device':False}
