const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),ts=require('typescript')
const root=path.resolve(__dirname,'..'),file=path.join(root,'admin/src/components/LeaderboardRewardEditor.tsx')
const output=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText
const exportsObject={};vm.runInNewContext(`(function(require,exports){${output}\n})`,{Number,JSON,Map})(name=>({react:{},antd:{},'react/jsx-runtime':{},'../api/lookups':{}}[name]??(()=>{throw Error(name)})()),exportsObject)
const validate=exportsObject.rewardDraftError
const server=require('../out/lib/leaderboard/settlement').validateRewardTiers
const item={itemId:1,itemName:'Synthetic item',itemCount:2,degreeId:null,degreeName:null,degreeImage:null},degree={itemId:null,itemName:null,itemCount:0,degreeId:1,degreeName:'Synthetic degree',degreeImage:'dynamic/degree/fixture.png'}
const percent=[{...item,fromPercent:0,toPercent:10},{...degree,fromPercent:10,toPercent:100}],rank=[{...item,fromRank:1,toRank:3},{...degree,fromRank:4,toRank:null}]
test('visual reward validation agrees with existing server contract for mixed prizes and both range types',()=>{
 const fixtures=[[],percent,rank,[{...item,...degree,itemId:1,itemName:item.itemName,itemCount:2,fromRank:1,toRank:null}],
  [{...item,fromPercent:1,toPercent:100}],[{...item,fromPercent:0,toPercent:50}], [{...item,fromPercent:0,toPercent:100.5}],
  [{...item,fromRank:2,toRank:null}],[{...item,fromRank:1,toRank:null},{...degree,fromRank:2,toRank:3}],
  [rank[0],{...degree,fromPercent:3,toPercent:100}], [{...item,itemCount:1.2,fromRank:1,toRank:null}],
  [{...degree,itemCount:2,fromRank:1,toRank:null}], [{...item,itemName:'',fromRank:1,toRank:null}],
  [{...degree,degreeName:'',fromRank:1,toRank:null}], [{...item,itemId:null,itemCount:0,fromRank:1,toRank:null}],
  [{...item,itemId:Number.MAX_SAFE_INTEGER+1,fromRank:1,toRank:null}], [null], [3]]
 for(const fixture of fixtures){let accepted=true;try{server(fixture)}catch{accepted=false};assert.equal(validate(JSON.stringify(fixture))===null,accepted,JSON.stringify(fixture))}
 assert.match(validate('{'),/格式/);assert.match(validate('{}'),/档位/)
})
test('validation does not normalize or discard existing names/images, rows, range and prize fields',()=>{
 for(const rows of [percent,rank]){const text=JSON.stringify(rows);assert.equal(validate(text),null);assert.equal(JSON.stringify(rows),text)}
 const both={...item,degreeId:1,degreeName:'Original title',degreeImage:'dynamic/degree/original.png',fromRank:1,toRank:null};assert.equal(validate(JSON.stringify([both])),null)
})
