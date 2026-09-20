// Read-only resource handler verification; no listener or player database.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'..');
const manifest=JSON.parse(fs.readFileSync(path.join(root,'assets/asset-patch/manifest.json')));
const patch=manifest.patches.find(p=>p.enabled&&p.version==='1.4.110');
const expected=['pinball-1.4.109-1.4.110-1-seasonal-characters-degrees.zip','pinball-1.4.109-1.4.110-2-abyss-normal-ex-art.zip'];
assert.deepEqual(patch.chain,expected);
assert.equal(patch.depends_on,'1.4.109');
let bytes=0;
for(const item of patch.archive_integrity){
 const data=fs.readFileSync(path.join(root,'assets/asset-patch/active',item.name));
 assert.equal(data.length,item.size);assert.equal(crypto.createHash('sha256').update(data).digest('hex'),item.sha256);bytes+=data.length;
}
assert.equal(bytes,patch.archive_size);
assert.deepEqual(patch.rush_tower_resets,patch.quest_time_revisions);
const asset=require('../out/routes/cn/asset.js');
(async()=>{
 const handlers=new Map();await asset.default({post:(name,handler)=>handlers.set(name,handler)});
 async function call(name,device,res_ver){let status,body;await handlers.get(name)({headers:{host:'127.0.0.1:8001',device,res_ver}},
  {type(){return this},status(x){status=x;return this},send(x){body=x;return this}});assert.equal(status,200);return body;}
 const platforms={};
 for(const device of ['android','ios']){
  const update=(await call('/get_path',device,'1.4.109')).data;
  assert.equal(update.info.target_asset_version,manifest.cdn_version);
  const edge=update.diff.find(group=>group.version==='1.4.110');assert.ok(edge);
  assert.deepEqual(edge.archive.map(a=>path.posix.basename(a.location)),expected);
  assert.equal(edge.archive.reduce((a,b)=>a+b.size,0),bytes);
  const archives=update.diff.flatMap(group=>group.archive);
  for(const archive of archives){
   const name=path.posix.basename(archive.location);
   const integrity=manifest.patches.flatMap(p=>p.archive_integrity||[]).find(p=>p.name===name);assert.ok(integrity);
   const data=fs.readFileSync(path.join(root,'assets/asset-patch/active',name));
   assert.equal(data.length,archive.size);assert.equal(data.length,integrity.size);
   assert.equal(crypto.createHash('sha256').update(data).digest('hex'),integrity.sha256);
  }
  const total=archives.reduce((sum,archive)=>sum+archive.size,0);
  assert.equal((await call('/version_info',device,'1.4.109')).data.total_size,total);
  const current=await call('/get_path',device,manifest.cdn_version);assert.equal(current.data.diff,null);assert.equal(current.data.full,null);
  platforms[device]={parts:archives.map(a=>path.posix.basename(a.location)),bytes:total,already_current_has_no_update:true};
 }
 const report={status:'passed',platforms,actual_asset_handlers:true,listener_started:false,player_database_accessed:false,runtime_synced:false,device_tested:false};
 // Historical .110 receipts remain immutable; optionally write a new local report.
 if(process.argv[2])fs.writeFileSync(path.resolve(process.argv[2]),JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify(report));
})().catch(e=>{console.error(e);process.exitCode=1});
