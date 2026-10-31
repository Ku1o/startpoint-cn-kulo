'use strict'
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os')
const Module=require('node:module'),ts=require('typescript'),{createHash}=require('node:crypto'),{Open}=require('unzipper')
const root=path.resolve(__dirname,'..'),sha=body=>createHash('sha256').update(body).digest('hex')
const manifestPath='assets/asset-patch/manifest.json',archivePath='assets/asset-patch/active/pinball-1.4.350-1.4.351-1-ios-resource-closure.zip'
function load(name){const file=path.join(root,'src/lib',name+'.ts'),m=new Module(file,module)
 m.filename=file;m.paths=Module._nodeModulePaths(path.dirname(file))
 m.require=name=>name.startsWith('.')&&fs.existsSync(path.resolve(path.dirname(file),name)+'.ts')
  ?load(path.relative(path.join(root,'src/lib'),path.resolve(path.dirname(file),name))):Module.prototype.require.call(m,name)
 m._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText,file)
 return m.exports}
const {readContentResourceSourceSync:read}=load('content-resource-source')
const source={assetVersion:'1.4.350',manifestSha256:'4cb3dd337ac062af6845591b85cf27d3bc203160923f74c2cf1c7a2883b76843'}
const canonical=v=>Array.isArray(v)?'['+v.map(canonical).join(',')+']':v&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}':JSON.stringify(v)
function fixture(t){const base=path.resolve(process.env.STARPOINT_TEST_TMP_ROOT||os.tmpdir()),directory=fs.mkdtempSync(path.join(base,'content-resource-source-'))
 t.after(()=>{assert.equal(path.dirname(directory),base);fs.rmSync(directory,{recursive:true})})
 for(const name of [manifestPath,archivePath]){fs.mkdirSync(path.dirname(path.join(directory,name)),{recursive:true});fs.copyFileSync(path.join(root,name),path.join(directory,name))}
 return directory}

test('351 adds exactly five reviewed iOS members and leaves the complete 350 chain unchanged',async()=>{
 const manifest=JSON.parse(fs.readFileSync(path.join(root,manifestPath))),last=manifest.patches.pop()
 assert.equal(manifest.cdn_version,'1.4.351');assert.equal(manifest.patches.length,134);manifest.cdn_version='1.4.350'
 // Canonical hash captured independently from the original 350 manifest;
 // object key formatting is not part of this structural preservation proof.
 assert.equal(sha(canonical(manifest)),'27a56c0d1bf12e6443be22542fcf03d3964d8155839738e15821e4d68e00242f')
 const zip=await Open.file(path.join(root,archivePath))
 const expected=['17/b9a5dfae0310f093f659d31b801770a0fba7a7','31/94c5d899390a197ed6bb9a7b06206df8ca689e',
  '53/e1857d76f211e567f6c775a194db62738e039c','96/b97133a2b5c5bc58a4f234d531960136f0729f','ce/d720392bdd8eeb25b339c2e3943f327fea27ba'].map(n=>'production/ios_upload/'+n).sort()
 assert.deepEqual(zip.files.map(f=>f.path).sort(),expected);assert.deepEqual([...last.files].sort(),expected)
 assert.deepEqual(read(),source)
})
test('real native index regenerates deterministically and the production loader accepts every source',()=>{
 const {generate}=require('../tools/build-content-native-identities.cjs'),result=generate({root,check:true})
 assert.deepEqual(result.counts,{quests:268,shops:8771})
 const maps=load('content-native-identities-runtime').loadContentNativeIdentities({root})
 assert.equal(maps.quests.size,268);assert.equal(maps.shops.size,8771)
 assert.deepEqual(load('content-release-supplement').readContentReleaseSourceSync(),source)
})
test('unknown manifests keep their own source and cannot inherit the 350 deployment receipt',t=>{
 const directory=fixture(t),file=path.join(directory,manifestPath),manifest=JSON.parse(fs.readFileSync(file))
 manifest.patches[0].enabled=!manifest.patches[0].enabled
 const raw=JSON.stringify(manifest);fs.writeFileSync(file,raw)
 assert.deepEqual(read(directory),{assetVersion:'1.4.351',manifestSha256:sha(raw)})
 assert.notDeepEqual(read(directory),source)
})
for(const change of ['corrupt','missing'])test('exact manifest with '+change+' iOS archive fails closed',t=>{
 const directory=fixture(t),file=path.join(directory,archivePath)
 if(change==='missing')fs.unlinkSync(file);else{const bytes=fs.readFileSync(file);bytes[bytes.length-1]^=1;fs.writeFileSync(file,bytes)}
 assert.throws(()=>read(directory),change==='missing'?/ENOENT/:/archive identity mismatch/)
})
test('a manifest without a reviewed extension uses its actual version and hash',t=>{
 const directory=fixture(t),raw=JSON.stringify({cdn_version:'1.4.352',patches:[]})
 fs.writeFileSync(path.join(directory,manifestPath),raw);fs.unlinkSync(path.join(directory,archivePath))
 assert.deepEqual(read(directory),{assetVersion:'1.4.352',manifestSha256:sha(raw)})
})
