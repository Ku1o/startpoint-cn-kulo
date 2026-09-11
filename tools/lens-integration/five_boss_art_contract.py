"""Display contracts for Five Boss thumbnails and synchronous material icons."""
import copy
import io
import re
from PIL import Image
import prepare_content as p
import fix_five_boss_icon_closure as closure

EQUIPMENT='master/item/equipment.orderedmap'
ENHANCEMENT='master/equipment_enhancement/equipment_enhancement.orderedmap'
TRIM='master/generated/trimmed_image.orderedmap'
MATERIALS={'10000145':('新·深界结晶.png','deep_crystal_v2'),
           '10000147':('五王心核.png','five_king_core_v2')}
THUMBNAIL_SCALE=6
THUMBNAIL_FRAME_SIZE=168


def thumbnail(source):
    with Image.open(io.BytesIO(source)) as image:
        image.load()
        assert image.size==(20,20) and image.mode=='RGBA', 'thumbnail source must be 20x20 RGBA'
    raw=p.wf_assets.png_encode(source)
    assert p.wf_assets.png_decode_stored(raw)==source
    return raw


def small_icon(source):
    image=closure.strict_png(thumbnail(source))
    out=image.resize((40,40),Image.Resampling.NEAREST)
    for y in range(40):
        for x in range(40):
            assert out.getpixel((x,y))==image.getpixel((x//2,y//2))
    return closure.codec.encode_png(out)


def validate_manifest(manifest):
    previous='1.4.54'
    patches=sorted((x for x in manifest['patches'] if x.get('enabled') and x['type']=='patch'),
                   key=lambda x:tuple(map(int,x['version'].split('.'))))
    for entry in patches:
        assert re.fullmatch(r'\d+\.\d+\.\d+',entry['depends_on']), ('invalid dependency',entry['id'])
        assert entry['depends_on']==previous, ('noncontiguous dependency',entry['id'])
        previous=entry['version']
    assert previous==manifest['cdn_version']


def validate_display(read):
    tables={n:read(n) for n in (closure.ITEM,closure.SHOP,closure.STAGE,EQUIPMENT,ENHANCEMENT,TRIM)}
    items=p.rawmap(tables[closure.ITEM])
    atlases={name:closure.codec.decode_atlas(read(name+'.atlas.amf3.deflate')) for name in closure.PRELOADED}
    required=closure.requirements(tables)
    closure.validate_closure(required,atlases)
    for item in required:
        row=p.csvrows(items[str(item['id'])])[0]
        matches=[(name,r) for name,records in atlases.items() for r in records if r['n']==row[4]]
        assert len(matches)==1
        atlas_name,frame=matches[0]
        assert (frame['w'],frame['h'])==(40,40), ('material bar needs 40x40',item['id'])
        actual=closure.strict_png(read(atlas_name+'.png')).crop(closure.rect(frame))
        expected=closure.strict_png(read(row[4]+'.png'))
        assert actual.tobytes()==expected.tobytes(), ('atlas differs from small PNG',item['id'])
        assert closure.strict_png(read(row[3]+'.png')).size==(20,20)
    for key in MATERIALS:
        row=p.csvrows(items[key])[0]
        assert row[3]!=row[4] and row[4].startswith('item_icon/')
        expected=small_icon(p.wf_assets.png_decode_stored(read(row[3]+'.png')))
        assert closure.strict_png(expected).tobytes()==closure.strict_png(read(row[4]+'.png')).tobytes()
    equipment=p.csvrows(p.rawmap(tables[EQUIPMENT])['5900101'])[0]
    enhancement=p.csvrows(p.rawmap(tables[ENHANCEMENT])['5900101'])[0]
    shop=p.rawmap(tables[closure.SHOP])
    weapon_product=p.csvrows(shop['990099001'])[0]
    ticket_product=p.csvrows(shop['990099002'])[0]
    assert ticket_product[12]==p.csvrows(items['10000143'])[0][3]
    trim=p.rawmap(tables[TRIM])
    weapon_paths=[equipment[6],enhancement[4],weapon_product[12]]
    for name in weapon_paths:
        image=closure.strict_png(read(name+'.png'))
        assert image.size==(20,20), ('detail thumbnail oversized',name,image.size)
        assert all(n*THUMBNAIL_SCALE<=THUMBNAIL_FRAME_SIZE for n in image.size)
        assert name in trim, ('missing thumbnail frame',name)
        assert p.csvrows(trim[name])==[['0','0','20','20']], ('thumbnail frame mismatch',name)
    assert len({closure.strict_png(read(n+'.png')).tobytes() for n in weapon_paths})==1
    return dict(required_small_icons=required,material_size=[40,40],thumbnail_size=[20,20],
                native_thumbnail_scale=6,rendered_thumbnail_size=[120,120],native_frame_size=168,
                weapon_thumbnail_paths=weapon_paths,full_canvas_trim=True)


def make_resources(read,originals,replace_frames):
    """Keep separate 20px thumbnails and 40px material-bar frames."""
    resources,source_map,atlas_reports={},{},{}
    tables={n:read(n) for n in (closure.ITEM,closure.SHOP,EQUIPMENT,ENHANCEMENT,TRIM)}
    items=p.rawmap(tables[closure.ITEM]);old_items=dict(items)
    icons_by_atlas={'item/sprite_sheet':{},'item_icon/sprite_sheet':{}}
    for item_id,(filename,stem) in MATERIALS.items():
        row=p.csvrows(items[item_id])[0];old=row.copy()
        row[4]='item_icon/materials/mod/five_boss/'+stem
        assert [i for i in range(len(row)) if row[i]!=old[i]] in ([],[4])
        items[item_id]=old_items[item_id] if row==old else p.packcsv([row])
        for image_path,raw in [(row[3],thumbnail(originals[filename])),(row[4],small_icon(originals[filename]))]:
            resources[image_path+'.png']=raw;source_map[image_path+'.png']=filename
            sheet=image_path.split('/')[0]+'/sprite_sheet'
            icons_by_atlas[sheet][image_path]=raw
    resources[closure.ITEM]=tables[closure.ITEM] if items==old_items else p.packmap(items)
    assert all(items[key]==raw for key,raw in old_items.items() if key not in MATERIALS)
    equipment=p.csvrows(p.rawmap(tables[EQUIPMENT])['5900101'])[0]
    enhancement=p.csvrows(p.rawmap(tables[ENHANCEMENT])['5900101'])[0]
    products=p.rawmap(tables[closure.SHOP]);old_products=dict(products)
    weapon_product=p.csvrows(products['990099001'])[0]
    ticket_product=p.csvrows(products['990099002'])[0];old_ticket=ticket_product.copy()
    ticket=p.csvrows(items['10000143'])[0][3]
    assert p.wf_assets.png_decode_stored(read(ticket+'.png'))==originals['新·深界连战凭证.png']
    ticket_product[12]=ticket
    if old_ticket!=ticket_product:
        assert [i for i in range(len(old_ticket)) if old_ticket[i]!=ticket_product[i]]==[12]
        products['990099002']=p.packcsv([ticket_product])
    resources[closure.SHOP]=tables[closure.SHOP] if products==old_products else p.packmap(products)
    trim=p.rawmap(tables[TRIM]);old_trim=dict(trim)
    for image_path in [equipment[6],enhancement[4],weapon_product[12]]:
        resources[image_path+'.png']=thumbnail(originals['死亡使者.png'])
        source_map[image_path+'.png']='死亡使者.png'
        if image_path not in trim or p.csvrows(trim[image_path])!=[['0','0','20','20']]:
            trim[image_path]=p.packcsv([['0','0','20','20']])
    resources[TRIM]=tables[TRIM] if trim==old_trim else p.packmap(trim)
    assert all(trim[key]==raw for key,raw in old_trim.items() if key not in [equipment[6],enhancement[4],weapon_product[12]])
    for atlas_name,icons in icons_by_atlas.items():
        png,atlas=read(atlas_name+'.png'),read(atlas_name+'.atlas.amf3.deflate')
        rows=closure.codec.decode_atlas(atlas);names={r['n'] for r in rows}
        sheet=closure.strict_png(png)
        changed={name:raw for name,raw in icons.items() if name in names and
            sheet.crop(closure.rect(next(r for r in rows if r['n']==name))).tobytes()!=closure.strict_png(raw).tobytes()}
        added={name:raw for name,raw in icons.items() if name not in names}
        proof={}
        if changed:png,proof['replaced']=replace_frames(png,atlas,changed)
        if added:png,atlas,proof['appended']=closure.append_icons(png,atlas,added)
        resources[atlas_name+'.png'],resources[atlas_name+'.atlas.amf3.deflate']=png,atlas
        atlas_reports[atlas_name]=proof or {'unchanged':True}
    resources={name:raw for name,raw in resources.items() if read(name)!=raw}
    def final_read(name):return resources[name] if name in resources else read(name)
    display=validate_display(final_read)
    # A valid standalone PNG must not hide a missing preloaded frame.
    for item in display['required_small_icons']:
        atlas_name=item['icon'].split('/')[0]+'/sprite_sheet.atlas.amf3.deflate'
        broken=closure.codec.encode_atlas([r for r in closure.codec.decode_atlas(final_read(atlas_name)) if r['n']!=item['icon']])
        try:validate_display(lambda n:broken if n==atlas_name else final_read(n))
        except AssertionError:pass
        else:raise AssertionError('missing material frame was accepted')
    return dict(resources=resources,source_map=source_map,atlas=atlas_reports,display=display,ticket=ticket,
                shop_changed_cells={'990099002':[12]} if old_ticket!=ticket_product else {},
                item_changed_cells={key:[4] for key in MATERIALS if old_items[key]!=items[key]},
                trim_updated_keys=[key for key in trim if trim[key]!=old_trim.get(key)])
