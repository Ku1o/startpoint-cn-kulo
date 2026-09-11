// Read the game's actual public accessors with only the six candidate JSON
// inputs redirected in this isolated process. No database or server writes.
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict'),Module=require('module');
const repo=path.resolve(__dirname,'../..'),work=path.resolve(process.argv[2]);
const prepared=JSON.parse(fs.readFileSync(path.join(work,'prepared.json'),'utf8'));
const useInstalled=process.argv.includes('--installed');
const sourceJson=Module._extensions['.json'];
const overrides=new Map(prepared.server_files.map(rel=>[path.resolve(repo,'assets',rel),path.resolve(work,'server-after/assets',rel)]));
if(!useInstalled)Module._extensions['.json']=(module,filename)=>sourceJson(module,overrides.get(filename)||filename);
const {serverGachas,cdnCharacters,cdnCharacterTexts}=require(path.join(repo,'out/lib/content-master.js'));
const {getGachaSync}=require(path.join(repo,'out/lib/assets.js'));
const load=rel=>JSON.parse(fs.readFileSync(path.join(work,'server-after/assets',rel),'utf8'));
const checks=[];
for(const [id,rel,count,total] of [['990001','gacha_cnmod.json',256,1500000],['990002','gacha_rank_p5b.json',286,950000]]){
 const expected=load(rel)[id];assert.deepEqual(serverGachas[id],expected);assert.deepEqual(getGachaSync(id),expected);
 const rows=expected.pool['1'];assert.equal(rows.length,count);assert.equal(rows.reduce((v,r)=>v+r.odds,0),total);
 if(id==='990001'){
  assert.equal(rows[0].id,149990);assert.equal(rows[0].odds,0);assert.equal(rows[0].isExchangeable,false);assert.equal(rows[0].trialReadingForced,false);
  assert.equal(rows.find(r=>r.id===131182).isExchangeable,true);
 }else assert.equal(rows.some(r=>r.id===149990),false);
 checks.push({id,count,total,accessor:'getGachaSync',winner:rel});
}
assert.deepEqual(cdnCharacters['129992'],load('cdndata/character.json')['129992']);
for(const id of ['129992','149990','169994'])assert.deepEqual(cdnCharacterTexts[id],load('cdndata/character_text.json')[id]);
assert.deepEqual(cdnCharacterTexts['169994'],load('cdndata/character_text_rank_p5b.json')['169994']);
const result={status:'passed',source:useInstalled?'installed_source_public_accessor':'candidate_public_accessor',checks,mirrored_text_ids:[129992,149990,169994],player_data_modified:false};
fs.writeFileSync(path.join(work,useInstalled?'installed-accessor-verification.json':'candidate-accessor-verification.json'),JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result));
