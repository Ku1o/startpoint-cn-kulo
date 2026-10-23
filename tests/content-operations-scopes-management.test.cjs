'use strict'
const {test,before,after}=require('node:test'),assert=require('node:assert/strict')
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm')
const out=process.env.STARPOINT_TEST_OUT_DIR
if(!out)throw Error('Use the current isolated build via STARPOINT_TEST_OUT_DIR')
const load=name=>require(path.join(out,name))
process.env.CN_WRITER_THREAD='0'
const Sqlite=require('better-sqlite3'),db=new Sqlite(':memory:')
const {ContentOperationsStore,initializeContentOperationsSchema}=load('lib/content-operations-store')
initializeContentOperationsSchema(db)
db.exec('CREATE TABLE retained_progress(id INTEGER PRIMARY KEY,value INTEGER); INSERT INTO retained_progress VALUES(1,777)')
load('data/db').setDbOverride(db)
const parent='tower_dungeon_event:1'
const catalog={schemaVersion:1,source:{assetVersion:'scope-fixture',manifestSha256:'fixture'},baselineTimeMs:0,
    baselineEvidence:'synthetic scope contract, not playable evidence',missing:[],resources:{},
    questMap:{'20:1001':parent,'20:1002':parent,'20:9999':'other:2'},missionMap:{'6:60':parent,'7:70':parent,'0:100':'other:2'},
    rows:[{key:parent,type:'tower_dungeon_event',id:1,name:'scope fixture',source:'fixture',definitionDigest:'scope1',
        originalStartMs:null,originalEndMs:null,originalExchangeEndMs:null,windowCandidate:false,browseCandidate:false,
        missionKeys:['6:60','7:70']},
        {key:'other:2',type:'other',id:2,name:'foreign scope',source:'fixture',definitionDigest:'scope2',
            originalStartMs:null,originalEndMs:null,originalExchangeEndMs:null,windowCandidate:false,browseCandidate:false}],}
const store=new ContentOperationsStore(db,catalog,row=>row.key===parent?['visible','enter','claim']:[])
const operations=load('lib/content-operations'),originalStore=operations.contentOperations
operations.contentOperations=()=>store
const previousPassword=process.env.ADMIN_PANEL_PASSWORD
process.env.ADMIN_PANEL_PASSWORD='scope-management-synthetic-password'
let app,cookie
const get=url=>app.inject({url,headers:{cookie}})
function body(input={}) {return {expectedRevision:store.revision(),catalogDigest:store.digest,readiness:'verified',
    evidence:'synthetic selected-member verification',reason:'scope fixture',flags:{visible:true,enter:true,claim:true},...input}}
const patch=input=>app.inject({method:'PATCH',url:`/api/content/${encodeURIComponent(parent)}`,headers:{cookie},payload:body(input)})
before(async()=>{
    app=require('fastify')({logger:false})
    load('lib/management-auth').installManagementAuth(app)
    await app.register(load('routes/web_api/content').default,{prefix:'/api/content'})
    const response=await app.inject({method:'POST',url:'/admin-login',payload:{password:process.env.ADMIN_PANEL_PASSWORD}})
    assert.equal(response.statusCode,200,response.body);cookie=response.headers['set-cookie'].split(';')[0]
})
after(async()=>{
    operations.contentOperations=originalStore
    if(app)await app.close()
    assert.equal(db.prepare('SELECT value FROM retained_progress WHERE id=1').get().value,777)
    load('data/db').setDbOverride(null);db.close()
    if(previousPassword===undefined)delete process.env.ADMIN_PANEL_PASSWORD;else process.env.ADMIN_PANEL_PASSWORD=previousPassword
})
test('selected-content members are authenticated, exact and independent of mutable player progress',async()=>{
    const url=`/api/content/${encodeURIComponent(parent)}/members`
    assert.equal((await app.inject(url)).statusCode,401)
    const response=await get(url);assert.equal(response.statusCode,200,response.body)
    assert.deepEqual(response.json(),{key:parent,revision:store.revision(),catalogDigest:store.digest,
        questKeys:['20:1001','20:1002'],missionKeys:['6:60','7:70']})
    assert.equal((await get('/api/content/missing%3A1/members')).statusCode,404)
    assert.equal((await get(`${url}?all=true`)).statusCode,400)
    assert.equal(store.revision(),0)
})
test('scope edits reject foreign, duplicate and empty participation lists without partial audit',async()=>{
    for(const input of [
        {questKeys:['20:9999'],missionKeys:['6:60']},
        {questKeys:['20:1001','20:1001'],missionKeys:['6:60']},
        {questKeys:['20:1001'],missionKeys:['0:100']},
        {questKeys:[],missionKeys:['6:60']},
        {questKeys:['20:1001'],missionKeys:[]},
    ]) {
        assert.equal((await patch(input)).statusCode,400)
        assert.equal(store.revision(),0);assert.equal(store.state(parent),null)
        assert.equal(store.audit().rows.length,0)
    }
    const response=await patch({questKeys:['20:1002'],missionKeys:['7:70']})
    assert.equal(response.statusCode,200,response.body)
    assert.equal(store.scopedAllowed(parent,'quest','20:1002','enter',Date.now()),true)
    assert.equal(store.scopedAllowed(parent,'quest','20:1001','enter',Date.now()),false)
    assert.equal(store.scopedAllowed(parent,'mission','7:70','claim',Date.now()),true)
    assert.equal(store.scopedAllowed(parent,'mission','6:60','claim',Date.now()),false)
})
test('omitted existing scopes stay unchanged and explicit edits appear in audit and snapshot',async()=>{
    const before=store.state(parent)
    assert.equal((await patch({flags:{visible:true,enter:false,claim:true}})).statusCode,200)
    assert.deepEqual(store.state(parent).questKeys,before.questKeys)
    assert.deepEqual(store.state(parent).missionKeys,before.missionKeys)
    const response=await patch({questKeys:['20:1002','20:1001'],missionKeys:['7:70','6:60']})
    assert.equal(response.statusCode,200,response.body)
    const audit=(await get(`/api/content/audit?key=${encodeURIComponent(parent)}`)).json().rows[0]
    assert.deepEqual(audit.before.questKeys,['20:1002'])
    assert.deepEqual(audit.after.questKeys,['20:1001','20:1002'])
    const state=store.snapshot(Date.now()).states.find(state=>state.key===parent)
    assert.deepEqual(state.quest_keys,['20:1001','20:1002']);assert.deepEqual(state.mission_keys,['6:60','7:70'])
})
test('UI submits selected scope fields only, preserving old omitted/null intent without a select-all default',()=>{
    const ts=require('typescript'),source=fs.readFileSync(path.resolve(__dirname,'../admin/src/pages/ContentOperations.tsx'),'utf8')
    const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022},reportDiagnostics:true})
    assert.ok(!compiled.diagnostics.some(item=>item.category===ts.DiagnosticCategory.Error))
    const module={exports:{}},context={exports:module.exports,module,require:name=>name==='dayjs'?{default:()=>{}}:{}}
    vm.runInNewContext(compiled.outputText,context,{filename:'ContentOperations.transpiled.cjs'})
    const build=module.exports.scopePatchFields
    const plain=value=>JSON.parse(JSON.stringify(value))
    assert.deepEqual(plain(build(false,[],false,[])),{},'untouched old null/omitted fields are not rewritten')
    assert.deepEqual(plain(build(true,[],true,[])),{questKeys:[],missionKeys:[]},'new scope has no approved members by default')
    assert.deepEqual(plain(build(true,['20:1002','20:1001'],false,[])),{questKeys:['20:1001','20:1002']})
    const business=module.exports.businessPatchFields,flags={visible:false,enter:false,claim:false,exchange:false}
    assert.deepEqual(plain(business(false,flags,true,[],true,[])),{},'review-only save sends no business flags or default empty scopes')
    assert.deepEqual(plain(business(true,flags,true,[],false,[])),{flags,questKeys:[]},'explicit takeover includes closed flags and reviewed scope')
})
test('an authenticated evidence-only save does not take over an unowned content record',async()=>{
    assert.equal(store.state('other:2'),null)
    const response=await app.inject({method:'PATCH',url:'/api/content/other%3A2',headers:{cookie},payload:{
        expectedRevision:store.revision(),catalogDigest:store.digest,readiness:'blocked',
        evidence:'synthetic resource review only',reason:'review must not affect legacy availability',
    }})
    assert.equal(response.statusCode,200,response.body)
    assert.equal(store.state('other:2').controlled,false)
    assert.equal(store.allowed('other:2','enter',Date.now()),null)
    assert.equal(store.scopedAllowed('other:2','quest','20:9999','enter',Date.now()),null)
    const saved=store.state('other:2')
    const update=await app.inject({method:'PATCH',url:'/api/content/other%3A2',headers:{cookie},payload:{
        expectedRevision:store.revision(),catalogDigest:store.digest,readiness:'verified',
        evidence:'synthetic follow-up still has no business flags',reason:'review update',
    }})
    assert.equal(update.statusCode,200,update.body)
    assert.equal(store.state('other:2').controlled,false)
    assert.equal(store.state('other:2').instanceId,saved.instanceId)
    assert.equal(store.allowed('other:2','visible',Date.now()),null)
})
