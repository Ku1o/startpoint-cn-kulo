'use strict'
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),vm=require('node:vm'),ts=require('typescript')
const {createHash}=require('node:crypto'),root=path.resolve(__dirname,'..'),sha=b=>createHash('sha256').update(b).digest('hex'),plain=v=>JSON.parse(JSON.stringify(v))
const oracleRoot=path.join(__dirname,'fixtures/content-original-oracles')
const oracleFile=process.env.STARPOINT_DISCOVERY_ORACLE||path.join(oracleRoot,'discovery/src/lib/content-discovery.ts')
if(!process.env.STARPOINT_DISCOVERY_ORACLE){const identity=JSON.parse(fs.readFileSync(path.join(oracleRoot,'manifest.json'))).files['discovery/src/lib/content-discovery.ts'];assert.equal(sha(fs.readFileSync(oracleFile)),identity.sha256);assert.equal(fs.statSync(oracleFile).size,identity.bytes)}
function moduleApi(file,directory){const counter={calls:0,identities:0},json=Object.create(JSON)
 json.stringify=(value,...args)=>{counter.calls++;if(Array.isArray(value)&&value.length===5&&typeof value[0]==='string'&&value[4]&&typeof value[4]==='object')counter.identities++;return JSON.stringify(value,...args)}
 const module={exports:{}},compiled=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText
 vm.runInNewContext(compiled,{require,module,exports:module.exports,__dirname:path.join(directory,'out/lib'),JSON:json})
 return {api:module.exports,counter}}
function fixture(t,runtime=false){const base=path.resolve(process.env.STARPOINT_TEST_TMP_ROOT||os.tmpdir()),directory=fs.mkdtempSync(path.join(base,'prepared-discovery-'))
 t.after(()=>{assert.equal(path.dirname(path.resolve(directory)),base);assert.ok(path.basename(directory).startsWith('prepared-discovery-'));fs.rmSync(directory,{recursive:true})})
 const write=(relative,value)=>{const file=path.join(directory,relative);fs.mkdirSync(path.dirname(file),{recursive:true});const body=JSON.stringify(value);fs.writeFileSync(file,body);return sha(body)}
 const source={manifestSha256:write('assets/asset-patch/manifest.json',{chain:'synthetic'}),presentationSha256:write('assets/content_presentation.json',{rows:{'gacha:7':{},'story_event:8':{}}}),catalogSha256:write('assets/content_catalog.json',{fixture:'catalog'})}
 const record={characters:[{id:1,name:'阿尔克',relation:'up',aliases:['勇者阿尔克']}],rewards:[{kind:'equipment',id:8,name:'勇气之剑',relation:'exchange'}],aliases:['星光庆典'],editionLabel:'第一期',notes:[],publicNotes:[],status:'verified'}
 const index={schemaVersion:1,source,sourceInputs:{'assets/terms.json':write('assets/terms.json',{term:'original'})},rows:{'gacha:7':record,'story_event:8':{...record,characters:[],rewards:[],aliases:[]}}}
 function persist(){const canonicalSha256=write('assets/content_discovery.json',index)
  if(runtime){const norm=value=>value.normalize('NFKC').toLocaleLowerCase().replace(/[\p{P}\p{S}\s]/gu,'')
   const c=record.characters[0],r=record.rewards[0]
   const projected={schemaVersion:2,canonicalSha256,source,sourceInputs:index.sourceInputs,
    characters:[{entity:c,fields:[c.name,...c.aliases].map(name=>({text:norm(name),reason:'UP角色：'+c.name,weight:80}))}],
    rewards:[{entity:r,fields:[{text:norm(r.name),reason:'兑换奖励：'+r.name,weight:55}]}],rows:{}}
   for(const [key,row]of Object.entries(index.rows))projected.rows[key]={characters:row.characters.length?[0]:[],rewards:row.rewards.length?[0]:[],aliases:row.aliases,editionLabel:row.editionLabel,publicNotes:row.publicNotes,status:row.status,
    highlights:row.characters.length?[{label:'UP角色',names:[c.name],total:1},{label:'兑换奖励',names:[r.name],total:1}]:[]}
   write('assets/content_discovery_runtime.json',projected)} }
 persist()
 const candidate=moduleApi(path.join(root,'src/lib/content-discovery.ts'),directory),oracle=moduleApi(oracleFile,directory)
 const parent={key:'gacha:7',type:'gacha',name:'流星原始名称',originalStartMs:Date.UTC(2025,6,19,16),originalEndMs:Date.UTC(2025,6,30),
  presentation:{title:'流星节扭蛋',originalTitle:'原版流星节',subtitle:'可靠活动说明',group:'gacha',typeLabel:'角色扭蛋'}}
 return {directory,write,index,record,persist,parent,candidate,oracle}}
function compare(a,b,parent,queries=['','流星节','原版流星节','阿尔克','勇气之剑','第一期','2025-07-20','不存在','流星节 阿尔克']){
 assert.deepEqual(plain(a.meta(parent)),plain(b.meta(parent)));assert.deepEqual(plain(a.view(parent)),plain(b.view(parent)))
 assert.deepEqual(plain(a.details(parent.key)),plain(b.details(parent.key)))
 for(const query of queries){const terms=query.split(' ').map(value=>value.normalize('NFKC').toLocaleLowerCase().replace(/[\p{P}\p{S}\s]/gu,'')).filter(Boolean);assert.deepEqual(plain(a.match(parent,terms)),plain(b.match(parent,terms)),query)}
 assert.equal(a.verificationNotice,b.verificationNotice)
}
for(const runtime of [false,true])test('prepared '+(runtime?'runtime':'legacy')+' complete views/meta/matches equal original source oracle',t=>{
 const f=fixture(t,runtime),a=f.candidate.api.contentDiscoveryReader(),b=f.oracle.api.contentDiscoveryReader()
 assert.equal(a.verificationNotice,undefined);compare(a,b,f.parent)
 const second={...f.parent,key:'story_event:8',type:'story_event',presentation:{...f.parent.presentation,title:'勇气之剑'}};compare(a,b,second)
})
for(const [name,mutate,query] of [
 ['type',p=>{p.type='story_event'},'流星节'],['name',p=>{p.name='新原始名字'},'新原始名字'],
 ['start date',p=>{p.originalStartMs=Date.UTC(2027,1,2)},'2027-02-02'],['end date',p=>{p.originalEndMs=Date.UTC(2028,2,3)},'2028-03-03'],
 ['title',p=>{p.presentation.title='新活动标题'},'新活动标题'],['originalTitle',p=>{p.presentation.originalTitle='新原版名称'},'新原版名称'],
 ['subtitle',p=>{p.presentation.subtitle='新副标题'},'新副标题'],['group',p=>{p.presentation.group='events'},'流星节'],
 ['typeLabel',p=>{p.presentation.typeLabel='新玩法类别'},'新玩法类别'],
])test('in-place mutable '+name+' invalidates the prepared card with original-oracle behavior',t=>{
 const f=fixture(t,true),a=f.candidate.api.contentDiscoveryReader(),b=f.oracle.api.contentDiscoveryReader(),before=a.view(f.parent)
 compare(a,b,f.parent);mutate(f.parent);compare(a,b,f.parent,[query,'阿尔克','勇气之剑','不存在'])
 assert.equal(a.match(f.parent,[query.normalize('NFKC').toLocaleLowerCase().replace(/[\p{P}\p{S}\s]/gu,'')]).matched,true)
 assert.notEqual(a.view(f.parent),before,'changed actual identity scalar rebuilds even on the same parent/presentation objects')
})
test('old/new index captures and degraded readers never exchange prepared relations',t=>{
 const f=fixture(t,true),a1=f.candidate.api.contentDiscoveryReader(),b1=f.oracle.api.contentDiscoveryReader();compare(a1,b1,f.parent)
 f.record.characters[0].name='全新长角色名字';f.record.characters[0].aliases=['全新长别号'];f.record.editionLabel='更新后的第二期';f.record.aliases=['另一个别称'];f.persist()
 const a2=f.candidate.api.contentDiscoveryReader(),b2=f.oracle.api.contentDiscoveryReader();compare(a2,b2,f.parent,['全新长角色名字','阿尔克','另一个别称'])
 assert.equal(a1.match(f.parent,['阿尔克']).matched,true);assert.equal(a2.match(f.parent,['阿尔克']).matched,false)
 compare(a1,b1,f.parent,['阿尔克','全新长角色名字'])
 f.write('assets/terms.json',{term:'source identity is deliberately changed'})
 const degraded=f.candidate.api.contentDiscoveryReader(),oldDegraded=f.oracle.api.contentDiscoveryReader()
 assert.ok(degraded.verificationNotice);compare(degraded,oldDegraded,f.parent,['阿尔克','全新长角色名字','流星节','2025-07-20'])
 compare(a1,b1,f.parent);compare(a2,b2,f.parent,['全新长角色名字','阿尔克'])
 assert.equal(degraded.match(f.parent,['全新长角色名字']).matched,false)
})
test('hot prepared cache hits do not allocate the old serialized presentation identity',t=>{
 const f=fixture(t,true),a=f.candidate.api.contentDiscoveryReader(),b=f.oracle.api.contentDiscoveryReader();compare(a,b,f.parent)
 f.candidate.counter.calls=0;f.candidate.counter.identities=0;f.oracle.counter.calls=0;f.oracle.counter.identities=0
 const view=a.view(f.parent)
 for(let i=0;i<80;i++){a.meta(f.parent);assert.equal(a.view(f.parent),view);a.match(f.parent,['阿尔克']);b.meta(f.parent);b.view(f.parent);b.match(f.parent,['阿尔克'])}
 assert.equal(f.candidate.counter.identities,0);assert.equal(f.candidate.counter.calls,0)
 assert.ok(f.oracle.counter.identities>=240,'instrumentation detects the original hot identity allocation')
})
