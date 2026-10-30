"""Portable recipes for the adopted 346 portraits/motion and 347 visual FX.

This module returns sparse logical resources; it never writes an archive or
manifest. Supply an explicit effective 345 baseline for phase 346, and 346 for
phase 347. The original author archives and the separately maintained offline
Character Studio compiler are explicit, hash-locked external inputs. No project
code from an author archive is executed.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import importlib
import io
import json
import math
from pathlib import Path
import sys
import zipfile
import zlib

sys.dont_write_bytecode = True


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _tools(context, spec):
    global core, assets, dsl, atf, R, Image, ImageChops
    global transformed_cell, compile_channels, make_channels, compose_frames, AO
    tools = (Path(context.repo) / "tools/fantasy-gauntlet-mod-tools").resolve()
    studio = Path(context.external("character_studio")).resolve()
    studio_contract = next(row for row in spec["externalInputs"] if row["alias"] == "character_studio")
    for record in studio_contract["files"]:
        name, expected = record["path"], record["sha256"]
        require(sha((studio / name).read_bytes()) == expected, "Studio input changed: " + name)
    sys.path[:0] = [str(tools), str(studio)]
    # Load repository codecs before Studio's compatibility bridge can resolve them.
    for name in ("wf_mod_tool", "wf_assets", "wf_dsl", "wf_atf", "wf_flatomo_preview_render"):
        loaded = importlib.import_module(name)
        require(Path(loaded.__file__).resolve().is_relative_to(tools), "Codec origin mismatch: " + name)
    core = importlib.import_module("wf_mod_tool")
    assets = importlib.import_module("wf_assets")
    dsl = importlib.import_module("wf_dsl")
    atf = importlib.import_module("wf_atf")
    R = importlib.import_module("wf_flatomo_preview_render")
    for record in studio_contract["files"]:
        name = record["path"]
        modname = Path(name).stem
        if modname in sys.modules:
            require(Path(sys.modules[modname].__file__).resolve() == studio / name,
                    "Studio module origin mismatch: " + modname)
    sc = importlib.import_module("studio_compile")
    ec = importlib.import_module("effect_channels")
    AO = importlib.import_module("atlas_optimizer")
    transformed_cell = sc.transformed_cell
    compile_channels, make_channels, compose_frames = ec.compile_channels, ec.make_channels, ec.compose_frames
    from PIL import Image as pil_image, ImageChops as pil_chops
    Image, ImageChops = pil_image, pil_chops


def dec(data):
    obj = zlib.decompressobj(-15)
    raw = obj.decompress(data) + obj.flush()
    require(obj.eof and not obj.unused_data and not obj.unconsumed_tail, "Invalid raw DEFLATE")
    reader = core.AMF3Reader(raw)
    result = reader.read_value()
    require(reader.pos == len(raw), "Trailing AMF data")
    return result


def enc(value):
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return compressor.compress(dsl.encode_amf3(value)) + compressor.flush()


def png(image):
    output = io.BytesIO()
    image.save(output, "PNG", compress_level=6)
    return output.getvalue()


def image(data):
    return Image.open(io.BytesIO(assets.png_decode_stored(data))).convert("RGBA")


def raw_rows(data):
    rows = core.read_orderedmap_raw_rows_from_bytes(data)
    return dict(zip(rows.keys, rows.rows))


def pack(rows):
    return core.build_orderedmap_raw_rows(core.OrderedMap("[art]", list(rows), list(rows.values()), Path("[memory]")))


class AuthorStore:
    def __init__(self, archive):
        self.archive, self.cache = archive, {}

    def asset_bytes(self, project, aid):
        if aid not in self.cache:
            record = project["assets"][aid]
            data = self.archive.read("assets/" + record["file"])
            require(not record.get("sha256") or sha(data) == record["sha256"], "Author asset hash mismatch: " + aid)
            self.cache[aid] = data
        return self.cache[aid]


def _open_authors(context, spec):
    opened = {}
    try:
        for source in spec["authors"]:
            path = Path(context.external(source["alias"]))
            data = path.read_bytes()
            require(len(data) == source["bytes"] and sha(data) == source["sha256"], "Original author archive mismatch")
            archive = zipfile.ZipFile(io.BytesIO(data))
            opened[str(source["id"])] = (json.loads(archive.read("project.json")), AuthorStore(archive))
        return opened
    except Exception:
        for _, store in opened.values():
            store.archive.close()
        raise


def _crop(source, size, box):
    x0, y0, x1, y1 = box
    pad = max(0, math.ceil(-min(x0, y0)), math.ceil(max(x1-source.width, y1-source.height))) + 4
    canvas = Image.new("RGBA", (source.width+2*pad, source.height+2*pad))
    canvas.paste(source, (pad, pad))
    return canvas.resize(size, Image.Resampling.LANCZOS, box=(x0+pad, y0+pad, x1+pad, y1+pad))


def _ui(context, spec, authors):
    output, portraits = {}, {}
    recipes = {(str(r["characterId"]), r["form"], r["logical"]): r for r in spec["ui"]["crops"]}
    for cid, (project, store) in authors.items():
        prefix = "character/" + spec["characters"][cid] + "/ui/"
        masters = []
        for n, form in enumerate(("base", "evolved")):
            aid = project["uiImages"][form + ":full_shot"]["asset"]
            original = store.asset_bytes(project, aid)
            source = Image.open(io.BytesIO(original)).convert("RGBA")
            masters.append(source)
            portraits[(cid, n)] = source
            logical = prefix + f"full_shot_1440_1920_{n}.png"
            output[("medium", logical)] = assets.png_encode(original)
            small = source.resize((max(1, int(source.width*.7)), max(1, int(source.height*.7))), Image.Resampling.LANCZOS)
            data = assets.png_encode(png(small))
            before = context.get("small", logical)
            if before and image(before).size == small.size and image(before).tobytes() == small.tobytes():
                data = before
            output[("small", logical)] = data
            for (recipe_cid, form_id, logical), recipe in recipes.items():
                if recipe_cid != cid or form_id != n:
                    continue
                result = _crop(source, tuple(recipe["size"]), tuple(recipe["sourceBox"]))
                if recipe["mask"]:
                    record = spec["ui"]["masks"][recipe["mask"]]
                    mask_data = base64.b64decode(record["pngBase64"], validate=True)
                    require(sha(mask_data) == record["sha256"], "Canonical mask changed")
                    mask = Image.open(io.BytesIO(mask_data)).convert("L")
                    require(mask.size == result.size, "Canonical mask dimensions changed")
                    result.putalpha(ImageChops.multiply(result.getchannel("A"), mask))
                cutin = logical.endswith(f"skill_cutin_{n}.png")
                for root in (("common",) if cutin else ("medium", "small")):
                    final = result if root != "small" else result.resize((int(result.width*.7), int(result.height*.7)), Image.Resampling.LANCZOS)
                    output[(root, logical)] = assets.png_encode(png(final))
                if cutin:
                    atflogical = logical[:-4] + ".atf.deflate"
                    android = atf.build_cutin_atf(png(result), atf.inflate(context.get("android", atflogical)))
                    ios = atf.build_cutin_atf_ios(png(result), atf.inflate(context.get("ios", atflogical)))
                    atf.validate_cutin_platform_pair(android, ios, png(result))
                    output[("android", atflogical)] = atf.deflate(android)
                    output[("ios", atflogical)] = atf.deflate(ios)
        logical = prefix + "illustration_setting_sprite_sheet.atlas.amf3.deflate"
        atlas = dec(context.get("common", logical))
        sheetlogical = prefix + "illustration_setting_sprite_sheet.png"
        sheet = Image.new("RGBA", image(context.get("medium", sheetlogical)).size)
        for row in atlas:
            source = masters[int(row["n"][-1])]
            art = source.crop(source.getbbox())
            scale = min(row["w"]/art.width, row["h"]/art.height)
            size = (max(1, round(art.width*scale)), max(1, round(art.height*scale)))
            art = art.resize(size, Image.Resampling.LANCZOS)
            cell = Image.new("RGBA", (row["w"], row["h"]))
            cell.alpha_composite(art, ((row["w"]-size[0])//2, (row["h"]-size[1])//2))
            sheet.alpha_composite(cell, (row["x"], row["y"]))
        output[("medium", sheetlogical)] = assets.png_encode(png(sheet))
        output[("small", sheetlogical)] = assets.png_encode(png(sheet.resize((int(sheet.width*.7), int(sheet.height*.7)), Image.Resampling.LANCZOS)))
    # Preserve every compressed row outside the explicit Lich positioning leaves.
    for table in spec["ui"]["tableEdits"]:
        rows = raw_rows(context.get("common", table["logical"]))
        original_keys = list(rows)
        for change in table["changes"]:
            path = change["path"]
            nested = rows if len(path) == 1 else raw_rows(rows[path[0]])
            before = zlib.decompress(nested[path[-1]]).decode("utf8").strip().split(",")
            require(before == change["before"], "Lich positioning preimage changed")
            nested[path[-1]] = zlib.compress((",".join(change["after"])+"\n").encode())
            if len(path) == 2:
                rows[path[0]] = pack(nested)
        require(list(rows) == original_keys, "Art recipe added a master key")
        output[("common", table["logical"])] = pack(rows)
    return output


def _patch(context, edits):
    output = {}
    for record in edits:
        before = dec(context.get("common", record["logical"]))
        after = copy.deepcopy(before)
        for edit in record["edits"]:
            parent = after
            for index in edit["path"][:-1]:
                parent = parent[index]
            require(type(parent[edit["path"][-1]]) is str and parent[edit["path"][-1]] == edit["before"], "Visual DSL preimage changed")
            parent[edit["path"][-1]] = edit["after"]
        restored = copy.deepcopy(after)
        for edit in reversed(record["edits"]):
            parent = restored
            for index in edit["path"][:-1]:
                parent = parent[index]
            parent[edit["path"][-1]] = edit["before"]
        require(restored == before, "Nonvisual DSL data changed")
        output[("common", record["logical"])] = enc(after)
    return output

def zero_trim(im):
 boxes=[b for ch in im.split() if (b:=ch.getbbox())]
 box=(min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)) if boxes else (0,0,1,1)
 crop=im.crop(box);restored=Image.new('RGBA',im.size);restored.paste(crop,box[:2]);assert restored.tobytes()==im.tobytes()
 return crop,box
def packed_compile(store,p,animations,variant,ns):
 prefix=f'character/{ns}/pixelart/';stem='pixelart' if variant=='normal' else 'special';ss='sprite_sheet' if variant=='normal' else 'special_sprite_sheet';cells={};clips=[];sequences=[];tick=1
 for a in animations:
  begin=tick
  for c in a['clips']:
   im,x,y=transformed_cell(store,p,c);trim,box=zero_trim(im);key=(trim.size,sha(trim.tobytes()));cells.setdefault(key,trim);clips.append({'key':key,'x':x+box[0],'y':y+box[1],'end':tick+c['hold']-1});tick+=c['hold']
  sequences.append({'name':a['slot'],'kind':a['kind'],'begin':begin,'end':tick-1})
 candidates=[]
 for width in [256,384,512,640,768,896,1024]:
  if max(im.width+2 for im in cells.values())>width:continue
  cursorx,cursory,rowh=1,1,0;positions={}
  for key,im in sorted(cells.items(),key=lambda kv:(-kv[1].height,-kv[1].width,kv[0][1])):
   if cursorx+im.width+1>width:cursorx=1;cursory+=rowh+2;rowh=0
   positions[key]=(cursorx,cursory);cursorx+=im.width+2;rowh=max(rowh,im.height)
  height=cursory+rowh+1
  if height<=4094:candidates.append((width*height,width,height,positions))
 assert candidates,'Lossless trimmed source motion does not fit one native texture'
 _,width,height,positions=min(candidates,key=lambda v:(v[0],v[1]));sheet=Image.new('RGBA',(width,height))
 for key,im in cells.items():sheet.paste(im,positions[key])
 atlas=[]
 for c in clips:
  im=cells[c['key']];x,y=positions[c['key']];atlas.append({'n':prefix+stem+f"{c['end']:04}",'w':im.width,'h':im.height,'x':x,'y':y,'fx':-c['x']-128,'fy':-c['y']-128,'fw':256,'fh':256})
 o=io.BytesIO();sheet.save(o,'PNG');stored=b'\x89png\r\n\x1a\n'+o.getvalue()[8:]
 frame={'name':prefix+stem,'x':-128,'y':-128,'scale':6,'smoothing':False}
 return {prefix+ss+'.png':stored,prefix+ss+'.atlas.amf3.deflate':enc(atlas),prefix+stem+'.frame.amf3.deflate':enc(frame),prefix+stem+'.timeline.amf3.deflate':enc({'sequences':sequences,'sounds':[],'points':[],'circles':[]})}
def state(t,f):
 keys=[x for x in t['frames'] if x['begin']<=f];return keys[-1]['data'] if keys else []
def semantic(old,new):
 comparisons=0
 for family in set(old)-{'sequences'}:
  assert family in new
  if family=='sounds':assert new[family]==old[family]==[];continue
  assert [x['path'] for x in old[family]]==[x['path'] for x in new[family]]
  for ot,nt in zip(old[family],new[family]):
   for ns in new['sequences']:
    os=next(s for s in old['sequences'] if s['name']==ns['name'])
    for offset in range(ns['end']-ns['begin']+1):
     a=state(ot,os['begin']+min(offset,os['end']-os['begin']));b=state(nt,ns['begin']+offset)
     assert a==b,(family,ot['path'],ns['name'],offset,a,b);comparisons+=1
 return comparisons
def migrate(old,authored,variant):
 result=copy.deepcopy(old);result['sequences']=copy.deepcopy(authored['sequences']);proof=[]
 if variant=='normal':
  for family in set(old)-{'sequences','sounds'}:
   for track in result[family]:
    for event in track['frames']:
     seq=next(s for s in old['sequences'] if s['begin']<=event['begin']<=s['end'])
     dst=next(s for s in result['sequences'] if s['name']==seq['name']);offset=event['begin']-seq['begin'];assert offset<=dst['end']-dst['begin']
     proof.append({'family':family,'path':track['path'],'slot':seq['name'],'oldBegin':event['begin'],'newBegin':dst['begin']+offset,'relativeOffset':offset,'data':copy.deepcopy(event['data'])})
     event['begin']=dst['begin']+offset
    assert [e['begin'] for e in track['frames']]==sorted(set(e['begin'] for e in track['frames']))
 else:
  assert {k:v for k,v in old.items() if k!='sequences'}=={k:v for k,v in result.items() if k!='sequences'}
  proof=[{'policy':'All original special event tracks retained exactly, including keys outside original selector ranges. Start at original75 retains active state semantics for extended land and shortened pose.'}]
 return result,{'events':proof,'perTickClampedStateComparisons':semantic(old,result),'soundDataExact':old['sounds']==result['sounds'],'nonvisualDataPreserved':True}


def _motion(context, spec, authors):
    output = {}
    for retained in spec["motion"]["retainedResources"]:
        require(sha(context.get(retained["root"], retained["logical"])) == retained["sha256"], "Retained 345 motion changed")
    for cid, (project, store) in authors.items():
        ns = spec["characters"][cid]
        prefix = f"character/{ns}/pixelart/"
        for variant, stem, sheetstem in (("normal", "pixelart", "sprite_sheet"), ("special", "special", "special_sprite_sheet")):
            author = [a for a in project["animations"] if a.get("variant", "normal") == variant and a.get("clips")]
            mappings = [r for r in spec["motion"]["mappings"] if str(r["characterId"]) == cid and r["variant"] == variant]
            require({a["slot"] for a in author} == {m["sourceSlot"] for m in mappings}, "Author motion inventory changed")
            baseline = dec(context.get("common", prefix+stem+".timeline.amf3.deflate"))
            final = {prefix+sheetstem+suffix: context.get("common", prefix+sheetstem+suffix) for suffix in (".png", ".atlas.amf3.deflate")}
            final.update({prefix+stem+suffix: context.get("common", prefix+stem+suffix) for suffix in (".frame.amf3.deflate", ".timeline.amf3.deflate")})
            effective = []
            for seq in baseline["sequences"]:
                animation = copy.deepcopy(next(a for a in author if a["slot"] == seq["name"]))
                if cid == "149985":
                    animation["kind"] = seq["kind"]
                    if variant == "normal" and animation["slot"] == "neutral":
                        require(len(animation["clips"]) == 1, "Lich neutral must remain one static drawing")
                        animation["clips"][0]["hold"] = 2
                effective.append(animation)
            if cid == "149985":
                final = packed_compile(store, project, effective, variant, ns)
                timeline = dec(final[prefix+stem+".timeline.amf3.deflate"])
                if variant == "special":
                    shift = baseline["sequences"][0]["begin"] - 1
                    atlas = dec(final[prefix+sheetstem+".atlas.amf3.deflate"])
                    frame = dec(final[prefix+stem+".frame.amf3.deflate"])
                    for row in atlas:
                        row["n"] = frame["name"] + f"{int(row['n'][len(frame['name']):])+shift:04}"
                    for sequence in timeline["sequences"]:
                        sequence["begin"] += shift
                        sequence["end"] += shift
                    final[prefix+sheetstem+".atlas.amf3.deflate"] = enc(atlas)
                timeline, _ = migrate(baseline, timeline, variant)
                final[prefix+stem+".timeline.amf3.deflate"] = enc(timeline)
                output.update({("common", logical): data for logical, data in final.items()})
            atlas = dec(final[prefix+sheetstem+".atlas.amf3.deflate"])
            frame = dec(final[prefix+stem+".frame.amf3.deflate"])
            timeline = dec(final[prefix+stem+".timeline.amf3.deflate"])
            sheet = image(final[prefix+sheetstem+".png"])
            require(max(sheet.size) <= 4094, "Motion texture exceeds native edge budget")
            require(len(effective) == len(timeline["sequences"]), "Native motion selector count changed")
            index = 0
            for animation, sequence in zip(effective, timeline["sequences"]):
                mapping = next(m for m in mappings if m["sourceSlot"] == animation["slot"])
                require(sequence == mapping["finalSelector"], "Native selector contract changed")
                tick = sequence["begin"]
                for clip in animation["clips"]:
                    row = atlas[index]
                    index += 1
                    expected, x, y = transformed_cell(store, project, clip)
                    if cid == "149985":
                        expected, bounds = zero_trim(expected)
                        x, y = x+bounds[0], y+bounds[1]
                    require(row["n"] == frame["name"]+f"{tick+clip['hold']-1:04}", "Native frame hold changed")
                    actual = sheet.crop((row["x"], row["y"], row["x"]+row["w"], row["y"]+row["h"]))
                    require(actual.size == expected.size and actual.tobytes() == expected.tobytes(), "Authored motion pixels changed")
                    require((frame["x"]-row["fx"], frame["y"]-row["fy"]) == (x, y), "Authored motion anchor changed")
                    tick += clip["hold"]
                require(tick == sequence["end"]+1, "Native selector hold mismatch")
            require(index == len(atlas), "Unmapped native atlas frames")
            for mapping in mappings:
                if mapping["finalSelector"] is None:
                    require(cid == "149985" and mapping["sourceSlot"] == "neutral_back", "Unknown editor-only selector")
    return output


def _command(command):
    packed = int(command.get("color", 0x64000000))
    color = command.get("colorTransform", [(packed >> 24)/100, (packed >> 16)&255, (packed >> 8)&255, packed&255])
    return {**command, "matrix": list(command["matrix"]), "alpha": command.get("alpha", 1),
            "fx": command.get("fx", 0), "fy": command.get("fy", 0), "blend": command.get("blend", 0), "colorTransform": color}


class TrimStore:
    """Lossless transparent trim; pivots are compensated in each draw matrix."""
    def __init__(self, frames, project, author):
        self.raw, self.trim = {}, {}
        for aid in {c["asset"] for frame in frames for c in frame}:
            data = author.asset_bytes(project, aid)
            im = Image.open(io.BytesIO(data)).convert("RGBA")
            bounds = im.getchannel("A").getbbox()
            if bounds is None:
                self.trim[aid] = None
                continue
            cell = im.crop(bounds)
            key = "trim_" + sha(str(cell.size).encode()+cell.tobytes())[:32]
            output = io.BytesIO()
            cell.save(output, "PNG", compress_level=9)
            require(key not in self.raw or self.raw[key] == output.getvalue(), "Trim identity collision")
            self.raw[key], self.trim[aid] = output.getvalue(), (key, bounds)

    def asset_bytes(self, project, aid):
        return self.raw[aid]

    def commands(self, frames):
        result = []
        for frame in frames:
            commands = []
            for index, command in enumerate(frame):
                trimmed = self.trim[command["asset"]]
                if trimmed is None:
                    continue
                cmd = copy.deepcopy(command)
                a, b, c, d, x, y = cmd["matrix"]
                fx, fy = cmd.get("fx", 0), cmd.get("fy", 0)
                aid, bounds = trimmed
                ox, oy = bounds[:2]
                cmd["asset"] = aid
                cmd["matrix"] = [a, b, c, d, x-a*fx-c*fy+a*ox+c*oy, y-b*fx-d*fy+b*ox+d*oy]
                cmd["fx"] = cmd["fy"] = 0
                cmd.setdefault("channel", "layer_"+str(index))
                cmd.setdefault("channelOrder", [index])
                commands.append(cmd)
            result.append(commands)
        return result


def _optimize(files, allow_lich_fixed=False):
    result, report = AO.optimize_files(files, {"enabled": True})
    if report["optimizedBundles"] == 1:
        require(report["skippedBundles"] == 0, "Partial atlas optimization")
        return result
    require(allow_lich_fixed, "FX atlas optimization failed")
    # Adopted bounded fallback: whole RGBA rectangles, no rotation/resampling.
    sheetlogical = "battle/effect/skill_unique/cnmod_halloween_r6/lich/lich"
    options = AO.validate_options({"enabled": True})
    sheet = AO._image(result[sheetlogical+".png"], options["max_pixels"])
    records = AO._amf(result[sheetlogical+".atlas.amf3.deflate"])
    regions = AO._validate_atlas(sheet, records, options, sheetlogical.rsplit("/", 1)[0])
    work = {"packingWork": 0, "packingWorkLimited": False}
    fixed = AO._pack(regions, 2048, 4094, "height", work)
    if fixed is None and work["packingWorkLimited"]:
        old_limit = AO.MAX_PACK_WORK
        AO.MAX_PACK_WORK = 32000000
        try:
            fixed = AO._pack(regions, 2048, 4094, "height", {"packingWork": 0, "packingWorkLimited": False})
        finally:
            AO.MAX_PACK_WORK = old_limit
    require(fixed is not None, "Bounded Lich atlas packing failed")
    places, size = fixed
    repacked = Image.new("RGBA", size)
    for src, dst in places.items():
        repacked.paste(sheet.crop((src.x, src.y, src.x+src.w, src.y+src.h)), (dst.x, dst.y))
    updated = copy.deepcopy(records)
    for record in updated:
        dst = places[AO._rect(record)]
        record.update(x=dst.x, y=dst.y)
    require(AO._canonical(AO._cells(sheet, records)) == AO._canonical(AO._cells(repacked, updated)), "Repack changed RGBA cells")
    before = AO._replay(result, sheetlogical+".png", records, AO._cells(sheet, records), options)
    result[sheetlogical+".png"] = AO._png_bytes(repacked, result[sheetlogical+".png"][:8])
    result[sheetlogical+".atlas.amf3.deflate"] = AO._amf_bytes(updated)
    after = AO._replay(result, sheetlogical+".png", updated, AO._cells(repacked, updated), options)
    require(before == after, "Repack changed stored frame operations")
    return result


def _compile_fx(frames, project, author, code, gid, scale, sequence, timeline=None, blank=False, lich=False):
    store = TrimStore(frames, project, author)
    expected = store.commands(frames)
    effect = {"id": gid, "name": gid, "nativeFrames": expected, "native": {"sequence": sequence},
              "frameScale": scale, "kind": "once", "layers": {}}
    make_channels(effect)
    used = {c["asset"] for frame in expected for c in frame}
    compilation_project = {"id": "halloween-visual-adoption", "assets": {aid: {"mime": "image/png", "name": aid} for aid in used}}
    files, issue = compile_channels(store, compilation_project, effect, code)
    require(issue is None, "FX compiler issue: " + str(issue))
    logical = f"battle/effect/skill_unique/{code}/{gid}/effect"
    parts = dec(files[logical+".parts.amf3.deflate"])
    parts["a"] = R.flatomo_instance_profile(parts)["per_image_peaks"]
    if blank:
        parts["g"][0]["t"] = len(frames)+1
    files[logical+".parts.amf3.deflate"] = enc(parts)
    if timeline is not None:
        files[logical+".timeline.amf3.deflate"] = enc(timeline)
    files = _optimize(files, lich)
    sheetlogical = logical.rsplit("/", 1)[0]+"/"+gid
    parts = dec(files[logical+".parts.amf3.deflate"])
    atlas = dec(files[sheetlogical+".atlas.amf3.deflate"])
    sheet = image(files[sheetlogical+".png"])
    require(max(sheet.size) <= 4094, "FX texture exceeds native edge budget")
    native = R._build_frames(parts)
    cells = R._load_cells(sheet, atlas, parts)
    by_rgba = {}
    for aid in used:
        im = Image.open(io.BytesIO(store.asset_bytes({}, aid))).convert("RGBA")
        by_rgba[(im.size, sha(im.tobytes()))] = aid
    identities = {index: by_rgba[(cell.image.size, sha(cell.image.tobytes()))] for index, cell in enumerate(cells)}
    for tick, wanted in enumerate(expected):
        actual = R._flatten(native, 0, tick, (1, 0, 0, 1, 0, 0), 1)
        require(len(actual) == len(wanted), "FX operation count changed")
        for (index, matrix, alpha), command in zip(actual, wanted):
            require(identities[index] == command["asset"], "FX source RGBA changed")
            require(max(abs(a-b) for a, b in zip(matrix, command["matrix"])) <= .5/4096+1e-8, "FX matrix changed")
            require(abs(alpha-command["alpha"]) <= .5/255+1e-8, "FX alpha changed")
    if blank:
        require(not R._flatten(native, 0, len(frames), (1, 0, 0, 1, 0, 0), 1), "Missing terminal blank")
    return files


def _mech(context, spec, authors):
    project, author = authors["139985"]
    effect = next(e for e in project["effects"] if e["id"] == spec["fx"]["mech"]["sourceEffectId"])
    require(len(effect.get("channels", [])) == 14 and effect.get("frameScale") == 6, "Mech author channel contract changed")
    source = [[_command(c) for c in frame] for frame in compose_frames(effect)]
    require(len(source) == 230, "Mech source duration changed")
    samples = [round(i*229/59) for i in range(60)]
    require(samples == spec["fx"]["mech"]["sampleSourceTicks"], "Mech sampling contract changed")
    frames = [copy.deepcopy(source[t]) for t in samples]
    source_channels = {c["channel"] for f in source for c in f if c.get("alpha", 1) > 0}
    sampled_channels = {c["channel"] for f in frames for c in f if c.get("alpha", 1) > 0}
    require(source_channels == sampled_channels and len(source_channels) == 14, "Mech sampling dropped a channel")
    donor = "battle/effect/skill_unique/lady_android_halloween/concert/sing_android_hw20"
    donor_timeline = dec(context.get("common", donor+".timeline.amf3.deflate"))
    require(not any(s["name"] == "end" for s in donor_timeline["sequences"]), "Mech original direct TTL contract changed")
    sounds = copy.deepcopy(donor_timeline["sounds"])
    for sound in sounds:
        sound["begin"] = min(sound["begin"], 61)
    timeline = {"sequences": [{"begin": 1, "end": 61, "name": "neutral", "kind": "once"}],
                "sounds": sounds, "points": [], "circles": [], "rectangles": [], "matrices": []}
    # Compile under the adopted intermediate namespace, then rename only paths.
    # This reproduces the selected s3 recipe without consuming any draft output.
    files = _compile_fx(frames, project, author, "cnmod_halloween_gacha_v3", "mech_candy", 3, "neutral", timeline, True)
    old = "battle/effect/skill_unique/cnmod_halloween_gacha_v3/mech_candy"
    new = "battle/effect/skill_unique/cnmod_halloween_r6/mech"
    renamed = {}
    for logical, data in files.items():
        final = logical.replace(old, new).replace("/mech_candy.", "/mech.")
        if logical.endswith(".parts.amf3.deflate"):
            parts = dec(data)
            require(parts["s"] == 3, "Mech visual projection changed")
            for item in parts["i"]:
                item["p"] = item["p"].replace(old, new)
            data = enc(parts)
        elif logical.endswith(".atlas.amf3.deflate"):
            atlas = dec(data)
            for row in atlas:
                row["n"] = row["n"].replace(old, new)
            data = enc(atlas)
        renamed[("common", final)] = data
    return renamed


def _lich_clock(sequences, ttl=90):
    byname = {s["name"]: s for s in sequences}
    codes = {}
    for sequence in sequences:
        if sequence["kind"] == "loop":
            codes[sequence["end"]] = ("goto", sequence["begin"])
        elif sequence["kind"] == "once":
            codes[sequence["end"]] = ("stop", None)
        elif sequence["kind"] == "goto":
            codes[sequence["end"]] = ("goto", byname[sequence["target"]]["begin"])
    frame, state, playing = 1, "Normal", True
    rows = [{"tick": 0, "frame": frame, "ttl": ttl, "state": state, "remove": False, "sounds": []}]
    for tick in range(1, 113):
        previous = frame
        if state == "Normal":
            if ttl <= 0:
                state, frame, playing = "Fading", byname["end"]["begin"], True
                ttl = byname["end"]["end"]-byname["end"]["begin"]+1
            else:
                ttl -= 1
        else:
            ttl -= 1
        if playing:
            code = codes.get(frame)
            if code:
                if code[0] == "goto":
                    frame = code[1]
                else:
                    playing = False
            else:
                frame += 1
        sounds = [frame] if frame != previous and frame in (5, 33) else []
        remove = state == "Fading" and ttl <= 0
        rows.append({"tick": tick, "frame": frame, "ttl": ttl, "state": state, "remove": remove, "sounds": sounds})
        if remove:
            break
    return rows


def _lich(context, spec, authors):
    project, author = authors["149985"]
    require([project["previewStage"]["width"], project["previewStage"]["height"]] == [1080, 1920], "Lich fixed author stage changed")
    effects = {e["id"]: e for e in project["effects"]}
    tracks = [t for t in project["scene"]["tracks"] if t["type"] == "effect"]
    require(len(tracks) == 10, "Lich fixed scene must contain 10 FX; actor track is excluded")
    frames = [[] for _ in range(101)]
    for order, track in enumerate(tracks):
        effect = effects[track["ref"]]
        require(effect["frameScale"] == 3.75 and track["scale"] == 1 and track.get("rotation", 0) == 0 and track.get("speed", 1) == 1,
                "Lich author scene track contract changed")
        tick = track["start"]
        for clip in effect["clips"]:
            im = Image.open(io.BytesIO(author.asset_bytes(project, clip["asset"]))).convert("RGBA")
            scale, angle = clip.get("scale", 1), math.radians(clip.get("rotation", 0))
            co, si, flip = math.cos(angle), math.sin(angle), -1 if clip.get("flip") else 1
            matrix = [scale*co*flip, scale*si*flip, -scale*si, scale*co,
                      clip.get("x", 0)+scale*im.width/2-144, clip.get("y", 0)+scale*im.height/2-256]
            command = _command({"asset": clip["asset"], "matrix": matrix, "alpha": clip.get("opacity", 1),
                                "fx": im.width/2, "fy": im.height/2, "channel": effect["id"], "channelOrder": [order]})
            for _ in range(clip.get("hold", 1)):
                require(tick < track["end"] and tick < 101, "Lich scene exceeds fixed duration")
                frames[tick].append(copy.deepcopy(command))
                tick += 1
        require(tick == track["end"], "Lich scene hold mismatch")
    donor = "battle/effect/skill_unique/lich_halloween/vine/psychic_tomboygirl_hw22_wire"
    old = dec(context.get("common", donor+".timeline.amf3.deflate"))
    timeline = copy.deepcopy(old)
    timeline["sequences"] = [{"begin": 1, "end": 31, "name": "start", "kind": "goto", "target": "loop"},
                             copy.deepcopy(next(s for s in old["sequences"] if s["name"] == "end")),
                             {"begin": 51, "end": 110, "name": "loop", "kind": "loop"}]
    require(timeline["sequences"][1] == {"begin": 32, "end": 50, "name": "end", "kind": "once"}, "Lich original fade slot changed")
    before, after = _lich_clock(old["sequences"]), _lich_clock(timeline["sequences"])
    require([(r["ttl"], r["state"], r["remove"]) for r in before] == [(r["ttl"], r["state"], r["remove"]) for r in after], "Lich TTL/fade lifecycle changed")
    require([(r["tick"], r["sounds"]) for r in before if r["sounds"]] == [(r["tick"], r["sounds"]) for r in after if r["sounds"]], "Lich sound schedule changed")
    storage, mapping = [[] for _ in range(110)], {}
    def put(native_frame, source_tick):
        storage[native_frame-1] = copy.deepcopy(frames[source_tick])
        mapping[native_frame] = source_tick
    for tick in range(31):
        put(tick+1, tick)
    put(32, 90)
    for tick in range(91, 101):
        put(33+tick-91, tick)
    for tick in range(31, 91):
        put(51+tick-31, tick)
    require([mapping.get(row["frame"]) for row in after[:101]] == list(range(101)), "Lich scene frame mapping changed")
    require(all(mapping.get(row["frame"]) is None for row in after[101:]), "Lich tail must be blank")
    files = _compile_fx(storage, project, author, "cnmod_halloween_r6", "lich", 3.75, "start", timeline, lich=True)
    return {("common", logical): data for logical, data in files.items()}


def _verify_fx_closure(context, spec, output):
    actual = set()
    for ns in spec["characters"].values():
        for form in (1, 2):
            logical = f"battle/action/skill/action/rare5/{ns}${ns}_{form}.action.dsl.amf3.deflate"
            tree = dec(output.get(("common", logical)) or context.get("common", logical))
            def walk(value):
                if isinstance(value, list):
                    for item in value:
                        walk(item)
                elif isinstance(value, dict):
                    for item in value.values():
                        walk(item)
                elif isinstance(value, str) and value.startswith("battle/effect/"):
                    actual.add(value)
            walk(tree)
    expected = {record["logical"] for record in spec["fx"]["referencedEffects"]}
    require(actual == expected and len(actual) == 17, "Final 17-effect consumer inventory changed")
    for record in spec["fx"]["referencedEffects"]:
        def get(logical):
            return output.get(("common", logical)) or context.get("common", logical)
        parts = dec(get(record["logical"]+".parts.amf3.deflate"))
        dec(get(record["logical"]+".timeline.amf3.deflate"))
        atlas = dec(get(record["sheetLogical"]+".atlas.amf3.deflate"))
        image(get(record["sheetLogical"]+".png"))
        require({row["p"] for row in parts["i"]}.issubset({row["n"] for row in atlas}), "Unresolved effect image binding")


def build(context, spec) -> dict[tuple[str, str], bytes]:
    """Build one explicit phase against context.get's immutable effective base.

    Pass the full spec with phase='346' or '347'; external aliases are declared
    in externalInputs. Identity mismatch fails closed, including output identity.
    Compilation occurs in memory. No candidate files are read from old workdirs.
    """
    phase = str(spec.get("phase", ""))
    require(phase in ("346", "347"), "Explicit phase '346' or '347' required")
    _tools(context, spec)
    expected = spec["phases"][phase]["resources"]
    for row in expected:
        before = context.get(row["root"], row["logical"])
        require((sha(before) if before is not None else None) == row["beforeSha256"], "Effective baseline mismatch: " + row["logical"])
    for row in spec["fx"]["donorIdentities"]:
        require(sha(context.get("common", row["logical"])) == row["sha256"], "FX donor identity changed")
    authors = _open_authors(context, spec)
    try:
        if phase == "346":
            output = _ui(context, spec, authors)
            output.update(_motion(context, spec, authors))
            output.update(_patch(context, spec["phases"][phase]["dslEdits"]))
        else:
            output = _mech(context, spec, authors)
            output.update(_lich(context, spec, authors))
            output.update(_patch(context, spec["phases"][phase]["dslEdits"]))
            _verify_fx_closure(context, spec, output)
        output = {key: data for key, data in output.items() if data != context.get(*key)}
        wanted = {(row["root"], row["logical"]): row for row in expected}
        require(set(output) == set(wanted), "Generated sparse resource set differs from adopted phase")
        for key, data in output.items():
            require(len(data) == wanted[key]["bytes"] and sha(data) == wanted[key]["sha256"], "Generated resource differs from adopted bytes: " + key[1])
        return output
    finally:
        for _, store in authors.values():
            store.archive.close()
