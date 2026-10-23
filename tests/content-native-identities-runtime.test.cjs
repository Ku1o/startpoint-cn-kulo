'use strict'
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os')
const crypto=require('node:crypto'),Module=require('node:module'),ts=require('typescript')
const root=path.resolve(__dirname,'..'),{sourceNames}=require('../tools/build-content-native-identities.cjs')
const sha=value=>crypto.createHash('sha256').update(value).digest('hex'),hash=digit=>digit.repeat(64)
function sourceModule(name,fsApi=fs){const file=path.join(root,'src/lib',name+'.ts'),instance=new Module(file,module)
 instance.filename=file;instance.paths=Module._nodeModulePaths(path.dirname(file))
 instance.require=name=>name==='node:fs'?fsApi:name==='./content-native-identities-identity'?sourceModule('content-native-identities-identity'):require(name)
 instance._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText,file)
 return instance.exports}
const {loadContentNativeIdentities:load,CONTENT_NATIVE_IDENTITY_SOURCES}=sourceModule('content-native-identities-runtime')
function fixture(t){const base=path.resolve(process.env.STARPOINT_TEST_TMP_ROOT||os.tmpdir()),directory=fs.mkdtempSync(path.join(base,'native-identities-'))
 t.after(()=>{assert.equal(path.dirname(path.resolve(directory)),base);assert.ok(path.basename(directory).startsWith('native-identities-'));fs.rmSync(directory,{recursive:true})})
 const sources={};for(const relative of sourceNames){const body='frozen fixture bytes: '+relative,file=path.join(directory,relative);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,body);sources[relative]={sha256:sha(body),bytes:Buffer.byteLength(body)}}
 const document={schemaVersion:1,sources,quests:[['story_event:1',hash('1')],['rush_event:2',hash('2')]],shops:[['event_item_shop:1',hash('3')]],counts:{quests:2,shops:1}}
 const identity={schemaVersion:1,sources:structuredClone(sources)},file=path.join(directory,'assets/content_native_identities_runtime.json')
 const save=value=>{const body=typeof value==='string'?value:JSON.stringify(value);fs.writeFileSync(file,body);identity.indexSha256=sha(body)};save(document)
 return {root:directory,sources,document,identity,file,save}}
test('strict index restores original ordered identities and gives every caller independent Maps',t=>{
 const f=fixture(t),first=load(f),second=load(f)
 assert.deepEqual([...CONTENT_NATIVE_IDENTITY_SOURCES],sourceNames)
 assert.deepEqual([...first.quests],f.document.quests);assert.deepEqual([...first.shops],f.document.shops)
 assert.notEqual(first.quests,second.quests);assert.notEqual(first.shops,second.shops)
 first.quests.clear();first.shops.set('event_item_shop:1',hash('9'))
 assert.equal(second.quests.size,2);assert.equal(second.shops.get('event_item_shop:1'),hash('3'))
})
test('only the small index is whole-read; original source bytes use bounded streaming and no JSON require cache',t=>{
 const f=fixture(t),wholeReads=[],fsApi={...fs,readFileSync(file,...args){wholeReads.push(path.basename(file));assert.equal(path.basename(file),'content_native_identities_runtime.json');return fs.readFileSync(file,...args)},
 readSync(fd,buffer,offset,length,position){assert.ok(length<=65536);return fs.readSync(fd,buffer,offset,length,position)}}
 sourceModule('content-native-identities-runtime',fsApi).loadContentNativeIdentities(f)
 assert.deepEqual(wholeReads,['content_native_identities_runtime.json']);assert.equal(require.cache[f.file],undefined)
})
for(const [name,mutate,expected] of [
 ['schema',d=>{d.schemaVersion=2},/schema/],['extra field',d=>{d.extra=[]},/fields/],
 ['missing source',d=>{delete d.sources[sourceNames[0]]},/source scope/],
 ['source record extra',d=>{d.sources[sourceNames[0]].extra=1},/record fields/],
 ['source identity',d=>{d.sources[sourceNames[0]].sha256=hash('9')},/source anchor mismatch/],
 ['source byte count',d=>{d.sources[sourceNames[0]].bytes++},/source anchor mismatch/],
 ['duplicate quest',d=>{d.quests.push(d.quests[0])},/duplicate quests/],
 ['duplicate shop',d=>{d.shops.push(d.shops[0])},/duplicate shops/],
 ['invalid key',d=>{d.quests[0][0]='__proto__'},/quests entry/],
 ['invalid digest',d=>{d.shops[0][1]='bad'},/shops entry/],
 ['count mismatch',d=>{d.counts.quests++},/count mismatch/],
 ['extra count',d=>{d.counts.extra=0},/count scope/],
 ['empty map',d=>{d.quests=[];d.counts.quests=0},/quests table/],
])test('rehashing an offline fixture does not bypass malformed '+name,t=>{
 const f=fixture(t);mutate(f.document);f.save(f.document);assert.throws(()=>load(f),expected)
})
test('valid-looking index tampering is rejected by the independently generated SHA anchor',t=>{
 const f=fixture(t),fixed=structuredClone(f.identity);f.document.shops[0][1]=hash('8');f.save(f.document)
 assert.throws(()=>load({root:f.root,identity:fixed}),/index SHA mismatch/)
})
test('invalid JSON is explicit even when the fixture anchor matches',t=>{
 const f=fixture(t);f.save('{invalid');assert.throws(()=>load(f),/invalid index JSON/)
})
test('missing index has no old-rule parse fallback',t=>{const f=fixture(t);fs.unlinkSync(f.file);assert.throws(()=>load(f),/ENOENT/)})
for(const relative of sourceNames)test('changed original source rejects the index: '+relative,t=>{
 const f=fixture(t);fs.appendFileSync(path.join(f.root,relative),'\nchanged');assert.throws(()=>load(f),/source identity mismatch/)
})
test('source mutation during streaming is rejected without returning partial identity Maps',t=>{
 const f=fixture(t);let changed=false
 const fsApi={...fs,readSync(fd,buffer,offset,length,position){const count=fs.readSync(fd,buffer,offset,length,position)
  if(!changed){changed=true;fs.appendFileSync(path.join(f.root,sourceNames[0]),'\nchanged while reading')};return count}}
 assert.throws(()=>sourceModule('content-native-identities-runtime',fsApi).loadContentNativeIdentities(f),/source changed during verification/)
})
