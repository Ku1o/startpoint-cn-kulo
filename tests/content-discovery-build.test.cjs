'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), os = require('node:os'), { createHash } = require('node:crypto')
const { merge } = require('../tools/build-content-discovery.cjs')
const sha = b => createHash('sha256').update(b).digest('hex')
function fixture(t) {
    const repo = fs.mkdtempSync(path.join(os.tmpdir(), 'discovery-merge-'))
    assert.ok(path.basename(repo).startsWith('discovery-merge-'))
    t.after(() => fs.rmSync(repo, { recursive: true }))
    const write = (relative, value) => { const file = path.join(repo, relative); fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, JSON.stringify(value)); return file }
    write('assets/asset-patch/manifest.json', { chain: 1 }); write('assets/content_presentation.json', { rows: { 'gacha:1': { type:'gacha' }, 'story_event:2': { type:'story_event' } } }); write('assets/content_catalog.json', { catalog: 1 }); write('assets/proven.json', { relation: 'exact' })
    const source = { manifestSha256: sha(fs.readFileSync(path.join(repo,'assets/asset-patch/manifest.json'))), presentationSha256: sha(fs.readFileSync(path.join(repo,'assets/content_presentation.json'))), catalogSha256: sha(fs.readFileSync(path.join(repo,'assets/content_catalog.json'))) }
    const row = { status:'verified',characters:[],rewards:[],aliases:[],notes:[],publicNotes:[] }
    const first = { schemaVersion:1,source:{...source},sourceInputs:{'assets/proven.json':sha(fs.readFileSync(path.join(repo,'assets/proven.json')))},rows:{'gacha:1':{...row,characters:[{id:9,name:'勇者（星之旅人）',relation:'up'}]}} }
    const second = { schemaVersion:1,source:{...source},sourceInputs:first.sourceInputs,rows:{'story_event:2':{...row,rewards:[{kind:'item',id:2,name:'勇者之证',relation:'exchange'}]}} }
    const fragments=[write('first.json',first),write('second.json',second)]
    return {repo,write,first,second,fragments}
}
test('full parent coverage is mandatory and exact duplicate relations retain their original role', t => {
    const f=fixture(t), result=merge(f)
    assert.equal(result.coverage.parents,2);assert.equal(result.coverage.characters,1);assert.equal(result.coverage.rewards,1)
    assert.equal(result.rows['gacha:1'].characters[0].relation,'up')
    f.second.rows['gacha:1']={...f.first.rows['gacha:1'],status:'not_applicable'};f.write('second.json',f.second)
    assert.equal(merge(f).rows['gacha:1'].characters.length,1)
    delete f.second.rows['story_event:2'];f.write('second.json',f.second)
    assert.throws(()=>merge(f),/Missing parent coverage/)
})
test('changed or unsafe input identities, unknown parents and conflicting names are rejected', t=>{
    const f=fixture(t)
    f.first.sourceInputs={'assets/../outside.json':'a'.repeat(64)};f.write('first.json',f.first)
    assert.throws(()=>merge(f),/Unsafe source input/)
    f.first.sourceInputs=f.second.sourceInputs;f.first.source.manifestSha256='b'.repeat(64);f.write('first.json',f.first)
    assert.throws(()=>merge(f),/Fragment source identities/)
    f.first.source=f.second.source;f.first.rows['unknown:1']=f.first.rows['gacha:1'];f.write('first.json',f.first)
    assert.throws(()=>merge(f),/Unknown parent/)
    delete f.first.rows['unknown:1'];f.write('first.json',f.first)
    f.second.rows['gacha:1']={...f.first.rows['gacha:1'],characters:[{id:9,name:'不同角色',relation:'up'}]};f.write('second.json',f.second)
    assert.throws(()=>merge(f),/Conflicting entity name/)
})
