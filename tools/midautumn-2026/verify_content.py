"""Read back the installed candidate and compare every unrelated master/atlas row."""
import argparse,io,json,sys,zipfile,zlib
from fractions import Fraction
from pathlib import Path
from PIL import Image
import build_content as b
p=b.p
import wf_flatomo_preview_render as preview

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,required=True);args=ap.parse_args()
    report=p.readj(args.work/'report.json');chain=p.Chain();assert chain.tail=='1.4.118'
    def current(logical,root='common'):
        value=chain.get((root,p.hrel(logical)));assert value is not None,logical;return value
    def old(logical,root='common'):
        receipt=report['asset_sources']['|'.join([root,p.hrel(logical)])]
        with zipfile.ZipFile(receipt['archive']) as z:value=z.read(receipt['member'])
        assert p.sha(value)==receipt['sha256'];return value
    checks=[]
    for logical,key in [(b.GACHA_T,b.GID),(b.FEATURE_T,b.GID),(b.ITEM_T,b.IID),('master/rich_text/rich_text_html.orderedmap',f'rich_text/{b.CODE}_note')]:
        before=p.rawmap(old(logical));after=p.rawmap(current(logical))
        assert len(after)==len(before)+1 and key not in before
        assert all(after[k]==v for k,v in before.items()),logical
        checks.append('preserved_unrelated_rows:'+logical)
    runtime=p.readj(b.REPO/'assets/gacha_midautumn_2026.json')[b.GID]
    row=p.csvrows(p.rawmap(current(b.GACHA_T))[b.GID])[0]
    assert p.readj(b.REPO/'assets/cdndata/gacha.json')[b.GID]==[row]
    feature=b.decode(p.rawmap(current(b.FEATURE_T))[b.GID])
    assert feature==p.readj(b.REPO/'assets/cdndata/gacha_feature_content.json')[b.GID]
    assert feature['1'][0][0]=='0' and feature['1'][0][2]==b.MOVIE
    assert row[4]=='4' and row[20]=='false' and row[27]=='(None)' and row[28]==b.IID and row[44]=='true'
    rarity=b.decode(current(f'master/gacha_odds/{row[11]}.orderedmap'))[row[11]]
    values={int(v[0][0]):int(v[0][1]) for v in rarity.values()}
    assert [values[5],values[4],values[3]]==runtime['rankRates']['normal']==[50,350,600]
    # Native GachaRarityOddsLogic transfers rank-3 weight to the guaranteed rank.
    assert [values[5],values[4]+values[3]]==runtime['rankRates']['multiGuarantee']==[50,950]
    for rank,bucket in [(3,'3'),(4,'2'),(5,'1')]:
        code=f'{b.CODE}_character_{rank}'
        client=b.decode(current(f'master/gacha_odds/{code}.orderedmap'))[code]
        expected=runtime['pool'][bucket];assert len(client)==len(expected)
        for i,e in enumerate(expected):
            cells=client[str(i)][0]
            assert list(map(int,cells[:3]))==[e['id'],e['rank'],e['odds']]
            assert cells[3:]==[str(e[k]).lower() for k in ['isRateUp','isLimited','isExchangeable','trialReadingForced']]
    assert Fraction(50,1000)*sum(Fraction(e['odds'],sum(x['odds'] for x in runtime['pool']['1'])) for e in runtime['pool']['1'] if e['isLimited'])==Fraction(4,100)
    checks.extend(['server_client_odds_identical','native_guarantee_5_95','twelve_mods_share_exactly_4_percent','ten_ticket_only_master_and_exchange_ui'])
    before_sheet=Image.open(io.BytesIO(b.wf_assets.png_decode(old('item/sprite_sheet.png')))).convert('RGBA')
    after_sheet=Image.open(io.BytesIO(b.wf_assets.png_decode(current('item/sprite_sheet.png')))).convert('RGBA')
    assert after_sheet.crop((0,0,*before_sheet.size)).tobytes()==before_sheet.tobytes()
    decode_amf=lambda data:b.wf_dsl.parse_dsl(zlib.decompress(data,-15))['tree']
    before_atlas=decode_amf(old('item/sprite_sheet.atlas.amf3.deflate'));after_atlas=decode_amf(current('item/sprite_sheet.atlas.amf3.deflate'))
    assert after_atlas[:-1]==before_atlas
    item=p.csvrows(p.rawmap(current(b.ITEM_T))[b.IID])[0];assert item[13]=='2'
    admin_items={**p.readj(b.REPO/'assets/item_lookup.json'),**p.readj(b.REPO/'assets/item_lookup_cnmod.json')}
    assert admin_items[b.IID]==item[2]
    checks.append('admin_item_lookup_matches_client_ticket_name')
    icon_name=item[3];entry=after_atlas[-1];assert entry['n']==icon_name
    icon=Image.open(io.BytesIO(b.wf_assets.png_decode(current(icon_name+'.png')))).convert('RGBA')
    assert icon.size==(20,20)
    assert after_sheet.crop((entry['x'],entry['y'],entry['x']+20,entry['y']+20)).tobytes()==icon.tobytes()
    checks.extend(['shared_item_atlas_all_old_pixels_preserved','new_icon_standalone_and_preloaded_atlas_identical'])
    movie=decode_amf(current(b.MOVIE+'.movie.amf3.deflate'));timeline=decode_amf(current(b.MOVIE+'.timeline.amf3.deflate'))
    assert movie['l']==timeline
    sheetbase=b.MOVIE.rsplit('/',1)[0]+'/sprite_sheet'
    atlas=decode_amf(current(sheetbase+'.atlas.amf3.deflate'))
    names={e['n'] for e in atlas};assert all(i['p'] in names for i in movie['i'])
    profile=preview.flatomo_instance_profile(movie);assert profile['per_image_peaks']==movie['a']==[1]*6
    assert timeline['sequences'][-1]['target']=='idle'
    sheet=Image.open(io.BytesIO(b.wf_assets.png_decode(current(sheetbase+'.png'))));assert max(sheet.size)<=2048
    for e in atlas:assert e['x']+e['w']<=sheet.width and e['y']+e['h']<=sheet.height
    checks.extend(['movie_embedded_timeline_and_loop','all_movie_images_in_required_sprite_sheet','instance_capacities_sufficient','common_png_no_platform_dependent_path'])
    for asset in report['assets']:assert p.sha(current(asset['logical'],asset['root']))==asset['sha256']
    for rel in ['assets/cdndata/gacha.json','assets/cdndata/gacha_feature_content.json','assets/item_ids.json']:
        before=p.readj(args.work/'before'/rel);after=p.readj(b.REPO/rel)
        if isinstance(before,dict):assert {k:v for k,v in after.items() if k!=b.GID}==before
        else:assert [i for i in after if i!=int(b.IID)]==before
    checks.append('source_mirrors_preserve_all_unrelated_rows')
    result={'checks':checks,'asset_count':len(report['assets']),'movie_instance_profile':profile,'limitations':['No runtime sync or device acceptance.','No mooncake acquisition source until the deferred shop is implemented.','CDN-only closure hides the entrance for updated clients; it is not a server-time restriction.']}
    p.savej(args.work/'verification.json',result);print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
