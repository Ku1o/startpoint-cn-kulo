const assert=require('node:assert/strict'),{merge}=require('../merge-policy.cjs')
const old={enforce:true,updateMessage:'保留既有群提示',builds:[{id:'old-ios',name:'old',platform:'ios',enabled:true,allowUntil:'2026-12-31T00:00:00Z'}]}
const release={enforce:false,updateMessage:'new',builds:[{id:'new-android',name:'new',platform:'android',enabled:true,allowUntil:null}]}
const oldKeys={'old-ios':'1'.repeat(64)},newKeys={'new-android':'2'.repeat(64)}
const before=JSON.stringify([old,oldKeys,release,newKeys]),result=merge(old,oldKeys,release,newKeys)
assert.equal(result.policy.enforce,true);assert.equal(result.policy.updateMessage,old.updateMessage)
assert.deepEqual(result.policy.builds[0],old.builds[0]);assert.deepEqual(result.policy.builds[1],release.builds[0])
assert.deepEqual(result.keys,{...oldKeys,...newKeys});assert.equal(JSON.stringify([old,oldKeys,release,newKeys]),before)
result.policy.builds[1].enabled=false;result.policy.builds[1].allowUntil='2026-09-16T00:00:00Z'
const again=merge(result.policy,result.keys,release,newKeys)
assert.deepEqual(again,result)
assert.throws(()=>merge(old,{},release,newKeys))
assert.throws(()=>merge(result.policy,result.keys,release,{'new-android':'3'.repeat(64)}))
const wrong=structuredClone(release);wrong.builds[0].platform='ios'
assert.throws(()=>merge(result.policy,result.keys,wrong,newKeys))
const duplicate=structuredClone(release);duplicate.builds.push(duplicate.builds[0])
assert.throws(()=>merge(old,oldKeys,duplicate,newKeys))
assert.equal(merge({enforce:false,updateMessage:'transition',builds:[]},{},release,newKeys).policy.enforce,false)
console.log(JSON.stringify({passed:true,checks:12,preservesExistingPolicyAndPrivateKeys:true}))
