"""Prepare the remaining 0909 graphics from the effective CN chain (sparse only)."""
from __future__ import annotations
import argparse, copy, json, zipfile, zlib
from pathlib import Path
import prepare_content as p
import optimize_battle_atlases as opt
import wf_battle_atlas_repack as a
import wf_dsl

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--donor',type=Path,required=True);args=parser.parse_args();w=args.work.resolve()
    assert not w.is_relative_to((p.REPO/'.cdn').resolve());w.mkdir(parents=True,exist_ok=True)
    c=p.Chain();assert c.tail=='1.4.103';assets={};inventory=[];receipts=[]
    decisions=p.readj(p.REPO/'assets/asset-patch/audit/lens0909-1.4.103/resource-decisions.json')
    def get(n):return c.get(('common',p.hrel(n)))
    def put(n,raw,kind):
        old=get(n);assert old is not None
        key=('common',p.hrel(n));assets[n]=raw
        path=w/'resources'/p.ROOTS['common']/key[1];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        before=w/'before'/p.ROOTS['common']/key[1];before.parent.mkdir(parents=True,exist_ok=True);before.write_bytes(old)
        inventory.append({'root':'common','logical':n,'rel':key[1],'member':p.member(key),
            'before_sha256':p.sha(old),'sha256':p.sha(raw),'kind':kind})
    for n in sorted(x for x in decisions['deferred'] if x.endswith('.atlas.amf3.deflate')):
        png_name=n.replace('.atlas.amf3.deflate','.png')
        kind='cn-lossless-atlas'
        if '/wave_arc120_' in n:
            # The unchanged animation loader still requests each own sheet.
            # Keep a valid small texture; all actual images now come from the
            # preloaded fast family. Never publish the author's 1x1 input.
            old_im=a.decode_png(get(png_name));old_frames=a.decode_atlas(get(n))
            png=a.encode_png(p.Image.new('RGBA',(8,8)));atlas=a.encode_atlas([])
            kind='shared-wave-empty-sheet'
            receipt={'before_size':list(old_im.size),'after_size':[8,8],'frames':len(old_frames),
                'before_area':old_im.width*old_im.height,'after_area':64,'changed':True,
                'verification':'all old rendered frames are matched against the shared fast atlas; no own frame is consumed'}
        else:png,atlas,receipt=opt.optimize(get(png_name),get(n))
        put(n,atlas,kind);put(png_name,png,kind)
        receipts.append({'logical':n,**receipt})
        print(json.dumps({'atlas':n,**receipt}),flush=True)
    donor={};sources=[]
    for path in sorted(args.donor.glob('archive-*-diff/*.zip')):
        sources.append({'path':str(path),'sha256':p.sha(path.read_bytes())})
        with zipfile.ZipFile(path) as z:
            for member in z.namelist():donor[member]=z.read(member)
    parts_reports=[]
    for n in [x for x in decisions['deferred'] if x.endswith('.parts.amf3.deflate')]:
        key=('common',p.hrel(n));raw=donor[p.member(key)]
        old=wf_dsl.parse_dsl(zlib.decompress(get(n),-15))['tree']
        new=wf_dsl.parse_dsl(zlib.decompress(raw,-15))['tree']
        p.savej(w/'parts'/Path(n).name.replace('.amf3.deflate','-before.json'),old)
        p.savej(w/'parts'/Path(n).name.replace('.amf3.deflate','-after.json'),new)
        if '/wave_arc120_' in n:
            # Author only redirects image paths; all timing/transform data stay CN-identical.
            redirected=copy.deepcopy(old)
            for image in redirected['i']:
                image['p']=image['p'].replace('wave_arc120_middle','wave_arc120_fast').replace('wave_arc120_slow','wave_arc120_fast')
            assert redirected==new,n
        else:
            assert new['i']==old['i'], 'particle optimization must not change image identities'
        image_paths=[entry['p'] for entry in new['i']]
        families={path.split('/.gen/')[0] for path in image_paths}
        names=set()
        for family in families:
            atlas_path=family+'/'+family.rsplit('/',1)[1]+'.atlas.amf3.deflate'
            png_path=atlas_path.replace('.atlas.amf3.deflate','.png')
            atlas=assets.get(atlas_path) or get(atlas_path);png=assets.get(png_path) or get(png_path)
            assert atlas and png,(n,atlas_path)
            frames=a.decode_atlas(atlas);im=a.decode_png(png)
            for f in frames:opt.crop_frame(im,f)
            names.update(f['n'] for f in frames)
        assert set(image_paths)<=names,(n,set(image_paths)-names)
        put(n,raw,'author-shared-wave' if '/wave_arc120_' in n else 'author-particle-reduction')
        parts_reports.append({'logical':n,'image_references':len(image_paths),'families':sorted(families),
                              'top_keys_before':list(old),'top_keys_after':list(new)})
    item_name='master/item/item.orderedmap';items=p.rawmap(get(item_name))
    original_item=items['10000143'];row=p.csvrows(original_item)[0]
    assert row[0]=='mod_five_boss_coop_v1_ticket' and row[1]=='10000143'
    row[5]='五重决战入场凭证。\n单人出战消耗1张；多人仅房主消耗1张，客人无需持有或消耗。\n每轮开始时扣除，换阶段及同局重试不重复扣除；缺票无法开局。\n可在五重决战交换所用10个深界结晶兑换1张。'
    items['10000143']=p.packcsv([row]);put(item_name,p.packmap(items),'ticket-description')
    ui_name='master/string/ui_string.orderedmap';strings=p.rawmap(get(ui_name))
    ui_key='quest_start_out_of_period_error';original_message=strings[ui_key]
    message=p.csvrows(original_message)
    assert len(message)==1 and len(message[0])==1,message
    message[0][0]='当前不满足出战条件。\n请检查关卡开放状态、入场门票和队伍限制后重试。'
    strings[ui_key]=p.packcsv(message);put(ui_name,p.packmap(strings),'native-entry-condition-message')
    p.savej(w/'ticket-ui-report.json',{'item':10000143,'description':row[5],
        'native_result_code':4050,'ui_key':ui_key,'message':message[0][0],
        'old_message':p.csvrows(original_message),
        'scope':'同一原生返回分支已用于关卡关闭、过期资源和装备限制，因此提示覆盖这些原因；不改变其他字符串。',
        'native_ticket_dialog_not_enabled':'c55 会拦住免票客人，且 BossBattleAsSingle 强化点展示与票数展示冲突 C2086；保留 c55=None。'})
    p.savej(w/'resources.json',inventory);p.savej(w/'atlas-report.json',receipts)
    p.savej(w/'parts-report.json',parts_reports);p.savej(w/'source-reads.json',c.reads)
    p.savej(w/'prepare-report.json',{'baseline':c.tail,'manifest_sha256':p.sha(c.manifest_bytes),'sources':sources})
    print('PREPARED',len(inventory),flush=True)

if __name__=='__main__':main()
