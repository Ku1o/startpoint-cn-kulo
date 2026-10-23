'use strict'
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path')
const Module=require('node:module'),ts=require('typescript'),{createHash}=require('node:crypto')
// In-memory transpilation checks the source without writing out/ or starting an application/database.
const filename=path.resolve(__dirname,'../src/lib/content-presentation.ts'),instance=new Module(filename,module)
instance.filename=filename;instance.paths=Module._nodeModulePaths(path.dirname(filename))
const compiled=ts.transpileModule(fs.readFileSync(filename,'utf8'),{reportDiagnostics:true,
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}})
assert.equal(compiled.diagnostics?.length??0,0)
instance._compile(compiled.outputText,filename)
const {getContentPresentation,readContentPresentationImage,CONTENT_PRESENTATION_GROUPS,CONTENT_PRESENTATION_TYPE_LABELS}=instance.exports
const manifest=require('../assets/content_presentation.json'),catalog=require('../assets/content_catalog.json')
const thumbnails=require('../assets/content_thumbnails/index.json')
const types=new Set(['gacha','advent_event','ranking_event','story_event','daily_week_event','challenge_dungeon_event',
    'daily_exp_mana_event','world_story_event','tower_dungeon_event','expert_single_event','carnival_event','raid_event','rush_event',
    'solo_time_attack_event','hard_multi_event','score_attack_event','active_mission_event','collect_item_event','pass_card_event',
    'box_gacha','multi_special_exchange_campaign','special_exchange_campaign','start_dash_exchange_campaign'])

test('all historical/native parents have original names and Chinese display categories without date filtering',()=>{
    const expected=catalog.rows.filter(row=>types.has(row.type))
    assert.equal(expected.length,1020)
    assert.deepEqual(Object.keys(manifest.rows).sort(),expected.map(row=>row.key).sort())
    assert.deepEqual(CONTENT_PRESENTATION_GROUPS.map(group=>group.key),['events','gacha','missions','exchange'])
    for(const row of expected) {
        const result=getContentPresentation(row)
        assert.ok(result.title,row.key);assert.ok(!/[a-zA-Z]/.test(result.groupLabel),row.key)
        assert.ok(!/[\u3040-\u30ff]/.test(result.title),row.key)
        assert.ok(!/[a-zA-Z]/.test(result.typeLabel),row.key)
        if(row.type!=='gacha')assert.equal(result.typeLabel,CONTENT_PRESENTATION_TYPE_LABELS[row.type],row.key)
        assert.ok(result.imageStatus==='available'||result.imageStatus==='missing')
        if(result.imageUrl) {
            assert.equal(result.imageUrl,`/api/content/thumbnail/${thumbnails.rows[row.key].image}.webp`)
            assert.equal(result.imageFallbackUrl,`/api/content/${encodeURIComponent(row.key)}/image`)
        }
        else assert.ok(result.imageMissingReason,row.key)
    }
    assert.equal(getContentPresentation('gacha:1704').title,'流星节扭蛋')
    assert.equal(getContentPresentation('gacha:25043').typeLabel,'装备扭蛋')
    assert.equal(getContentPresentation('world_story_event:400001').title,'幻彩摩天楼')
    assert.equal(getContentPresentation('box_gacha:28').title,'团本活动 战阵之宴 · 奖励箱')
    assert.equal(manifest.rows['box_gacha:28'].titleSource.parentKey,'raid_event:7')
    assert.ok(manifest.rows['gacha:1'],'ended history is retained even when its original image is unavailable')
})

test('Chinese explanations retain Japanese originals and clearly distinguish unconfirmed translations',()=>{
    const expected=Object.fromEntries(Array.from({length:9},(_,i)=>[`gacha:${800000+i}`,['星之英雄扭蛋','スターヒーローズガチャ']]))
    expected['collect_item_event:20001']=['素材兑换活动','マテリアルトレーダー']
    expected['collect_item_event:13001']=['特别任务活动','キャンペーンミッション']
    expected['gacha:900003']=['含限定角色的四星及以上扭蛋','限定込み★4以上扭蛋']
    for(const id of [143,127])expected[`gacha:${id}`]=['新角色精选扭蛋','新キャラピックアップガチャ']
    for(const id of [700001,700000])expected[`gacha:${id}`]=['回归扭蛋','カムバック扭蛋']
    expected['story_event:202013']=['情人节纪念关卡','バレンタイン纪念关卡']
    expected['story_event:200001']=['刷初始千万次纪念关卡','リセマラ1000万回突破纪念关卡']
    expected['story_event:300001']=['斗和奇迹联动活动','斗和キセキ联动Event']
    expected['advent_event:300001']=['永不言弃的魔导士','不諦の魔道士']
    assert.deepEqual(Object.keys(manifest.rows).filter(key=>manifest.rows[key].displayTitleSource).sort(),Object.keys(expected).sort())
    for(const [key,[title,original]] of Object.entries(expected)) {
        const result=getContentPresentation(key),stored=manifest.rows[key]
        assert.equal(result.title,title,key)
        assert.equal(result.originalTitle,original,key)
        assert.equal(stored.nativeName,original,key)
        assert.equal(stored.titleSource.kind,'native_master',key)
        assert.equal(stored.titleSource.originalText,original,key)
        assert.equal(stored.displayTitleSource.kind,'descriptive_chinese',key)
        assert.equal(stored.displayTitleSource.officialTranslationConfirmed,false,key)
        assert.equal(result.subtitle,`中文说明名称，非已确认官方译名；旧资料原名：${original}`,key)
        assert.ok(!/[0-9]|gacha|collect_item_event|story_event|advent_event/.test(result.title),key)
        assert.ok(!result.subtitle.includes(key),key)
    }
    assert.equal(getContentPresentation('gacha:800202').title,'星之英雄扭蛋','existing native Chinese title is retained')
    assert.equal(getContentPresentation('gacha:800202').originalTitle,undefined)
    assert.equal(getContentPresentation('box_gacha:28').originalTitle,undefined,'internal resource codes are not added as search titles')
    assert.equal(CONTENT_PRESENTATION_TYPE_LABELS.gacha,'扭蛋卡池','filter label covers both character and equipment pools')
})

test('seven same-name Rush switches have stable display-only sequence without relabeling other entries',()=>{
    const keys=Array.from({length:7},(_,index)=>`rush_event:${700011+index}`)
    assert.deepEqual(Object.keys(manifest.rows).filter(key=>manifest.rows[key].subtitleSource?.kind==='admin_disambiguation').sort(),keys)
    keys.forEach((key,index)=>{
        const stored=manifest.rows[key],result=getContentPresentation(key)
        assert.equal(stored.nativeName,'狂热激战')
        assert.equal(result.title,stored.nativeName,'official activity name is preserved')
        assert.equal(result.subtitle,`同名活动 ${index+1} / 7（后台区分序号，不代表原版期数或属性）`)
        assert.deepEqual(stored.subtitleSource,{kind:'admin_disambiguation',sequence:index+1,total:7,
            meaning:'仅用于区分后台条目，不代表原版期数或属性'})
        assert.ok(!result.subtitle.includes(key.split(':')[1]),'native IDs are not shown in display text')
        assert.equal(stored.titleSource.kind,'native_master')
        assert.equal(result.originalTitle,undefined)
    })
    for(const [key,row] of Object.entries(manifest.rows)) {
        if(keys.includes(key))continue
        assert.equal(row.subtitleSource,undefined,key)
        assert.ok(!getContentPresentation(key).subtitle?.includes('后台区分序号'),key)
    }
    assert.equal(getContentPresentation('rush_event:700001').title,'狂热激战')
    assert.equal(getContentPresentation('rush_event:700001').subtitle,undefined,'historical Rush parents are not assigned inferred issue numbers')
})

test('every declared original banner is lazily decoded to browser PNG with stable ETags and shared-image caching',async()=>{
    const available=Object.entries(manifest.rows).filter(([,row])=>row.images.length).map(([key])=>key)
    assert.equal(available.length,784)
    for(const key of available) {
        const image=await readContentPresentationImage(key)
        assert.ok(image,key)
        assert.equal(image.contentType,'image/png')
        assert.equal(image.bytes.subarray(0,8).toString('hex'),'89504e470d0a1a0a')
        assert.equal(image.etag,`"${createHash('sha256').update(image.bytes).digest('hex')}"`)
        assert.ok(image.bytes.readUInt32BE(16)>0&&image.bytes.readUInt32BE(20)>0)
        assert.strictEqual(await readContentPresentationImage(key),image,'repeat uses the bounded in-memory cache')
    }
})

test('missing original images and arbitrary resource/file names do not become proxies',async()=>{
    assert.equal(getContentPresentation('gacha:1').imageUrl,null)
    assert.equal(await readContentPresentationImage('gacha:1'),null)
    for(const key of ['__proto__','constructor','../../../config/client-admission.keys.json',
        'gacha:1704?path=../../../config','master/gacha/gacha.orderedmap'])
        assert.equal(await readContentPresentationImage(key),null,key)
})
