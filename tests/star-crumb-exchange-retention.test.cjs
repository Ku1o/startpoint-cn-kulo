'use strict'
const {test,before,after}=require('node:test')
const assert=require('node:assert/strict')
const fs=require('node:fs'),os=require('node:os'),path=require('node:path')
const ts=require('typescript')
// Exercise current sources without compiling or modifying a runtime directory.
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true},fileName:filename,
}).outputText,filename)
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'star-crumb-retention-'))
process.env.DATA_DIR=directory;process.env.GACHA_SEED_DIR=path.join(directory,'seeds')
process.env.CN_WRITER_THREAD='0';process.env.GAME_ROUTINE_LOGS='off';process.env.GAME_VERBOSE_LOGS='false'
const Fastify=require('fastify'),{pack,unpack}=require('msgpackr')
const rules=require('../src/lib/star-crumb-exchange-rules.ts')
const master=require('../assets/star_crumb_exchange.json')
const costs=require('../assets/star_crumb_exchange_cost.json')
const players=require('../src/data/domains/player.ts')
const characters=require('../src/data/domains/character.ts')
const equipment=require('../src/data/domains/equipment.ts')
const items=require('../src/data/domains/item.ts')
const coordinator=require('../src/lib/persistence-coordinator.ts')
const originalTransaction=coordinator.runPersistenceTransaction
const db=require('../src/data/db.ts').getDb()
let app,nextViewer=87680000
const now=Date.parse('2026-10-22T12:00:00+08:00')
const personal=row=>row[6]!=='(None)'||row[7]!=='(None)'
function costFor(id) {const row=master[id][0];return Number(costs[row[0]][0][row[8]==='5'?1:0])}
function state(playerId) {
    return Object.fromEntries(['players','players_characters','players_equipment','players_items'].map(table=>[
        table,db.prepare(`SELECT * FROM ${table} WHERE ${table==='players'?'id':'player_id'}=? ORDER BY rowid`).all(playerId),
    ]))
}
function player(balance=20000) {
    const account=require('../src/data/domains/account.ts').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'star-crumb-fixture',idpId:String(nextViewer),status:'normal'})
    const id=players.insertDefaultPlayerSync(account.id).id,viewer=nextViewer++
    require('../src/data/activeAccount.ts').saveAccountDefaultPlayer(account.id,id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer),account.id,'2099-01-01T00:00:00Z')
    players.updatePlayerSync({id,starCrumb:balance})
    return {id,viewer}
}
const post=(p,id)=>app.inject({method:'POST',url:'/exchange/star_crumb',payload:{viewer_id:p.viewer,exchange_id:id}})
function decode(response) {assert.equal(response.statusCode,200,response.body);return unpack(Buffer.from(response.body,'base64')).data}
before(async()=>{
    assert.ok(fs.realpathSync(db.name).startsWith(fs.realpathSync(directory)+path.sep))
    app=Fastify({logger:false})
    app.addHook('onSend',(_request,reply,body,done)=>done(null,String(reply.getHeader('content-type')).startsWith('application/x-msgpack')?pack(body).toString('base64'):body))
    await app.register(require('../src/routes/api/exchange.ts').default,{prefix:'/exchange'})
    await app.register(require('../src/routes/cn/load.ts').default,{prefix:'/cn'})
    await app.ready()
})
after(async()=>{
    coordinator.runPersistenceTransaction=originalTransaction
    if(app)await app.close()
    await require('../src/lib/seed-validator.ts').default.close()
    if(db.open)db.close()
    assert.equal(path.dirname(fs.realpathSync(directory)),fs.realpathSync(os.tmpdir()))
    fs.rmSync(directory,{recursive:true})
})

test('the fixed Beijing reference restores exactly 339 characters, 40 equipment and two items',()=>{
    const reference=Date.parse('2025-07-20T12:00:00+08:00')
    const expected=Object.entries(master).filter(([,rows])=>{
        const row=rows[0]
        return !personal(row)&&Date.parse(row[3].replace(' ','T')+'+08:00')<=reference
            &&reference<=Date.parse(row[4].replace(' ','T')+'+08:00')
    }).map(([id])=>Number(id)).sort((a,b)=>a-b)
    const ids=rules.getRetainedStarCrumbExchangeIds()
    assert.deepEqual(ids,expected);assert.equal(ids.length,381);assert.equal(new Set(ids).size,381)
    assert.deepEqual(ids.reduce((counts,id)=>(counts[master[id][0][0]]++,counts),[0,0,0]),[339,2,40])
    assert.ok(ids.includes(307));assert.ok(ids.includes(9000001));assert.ok(ids.includes(9000002))
    ids.length=0;assert.equal(rules.getRetainedStarCrumbExchangeIds().length,381,'response arrays cannot mutate the shared rule')
})
test('all other ordinary products keep their original inclusive China Standard Time boundaries',()=>{
    const retained=new Set(rules.getRetainedStarCrumbExchangeIds())
    for(const [id,rows] of Object.entries(master)) {
        const row=rows[0]
        if(personal(row)||retained.has(Number(id)))continue
        const start=Date.parse(row[3].replace(' ','T')+'+08:00'),end=Date.parse(row[4].replace(' ','T')+'+08:00')
        assert.equal(rules.isStarCrumbExchangeAvailable(Number(id),start-1),false,id)
        assert.equal(rules.isStarCrumbExchangeAvailable(Number(id),start),true,id)
        assert.equal(rules.isStarCrumbExchangeAvailable(Number(id),end),true,id)
        assert.equal(rules.isStarCrumbExchangeAvailable(Number(id),end+1),false,id)
        assert.equal(rules.isStarCrumbExchangeAvailable(Number(id),now),false,id)
    }
    for(const id of [0,-1,1.5,NaN,Infinity,99999999,'307'])assert.equal(rules.isStarCrumbExchangeAvailable(id,now),false)
})
test('the 604 personal products gain no retained client qualification and keep existing server behavior',()=>{
    const ids=new Set(rules.getRetainedStarCrumbExchangeIds())
    const rows=Object.entries(master).filter(([,rows])=>personal(rows[0]))
    assert.equal(rows.length,604)
    for(const [id] of rows) {
        assert.equal(ids.has(Number(id)),false)
        assert.equal(rules.isStarCrumbExchangeAvailable(Number(id),now),true,'legacy personal product IDs remain compatible')
    }
})

test('all 604 personal entries duplicate a retained ordinary character at the same price and reward terms',()=>{
    const retained=rules.getRetainedStarCrumbExchangeIds()
    const entries=Object.entries(master).filter(([,rows])=>personal(rows[0]))
    assert.equal(new Set(entries.map(([,rows])=>rows[0][1])).size,79)
    for(const [id,[row]] of entries) {
        assert.equal(row[0],'0',`personal product ${id} is a character`)
        const equivalent=retained.find(otherId=>{
            const other=master[otherId][0]
            return [0,1,2,5,8].every(index=>other[index]===row[index])&&costFor(otherId)===costFor(id)
        })
        assert.notEqual(equivalent,undefined,`personal product ${id} must not expand the retained shop or discount its price`)
        assert.equal(rules.isStarCrumbExchangeAvailable(equivalent,now),true)
    }
})
test('actual load sends the ordered 381 IDs beside the operations snapshot',async()=>{
    const p=player()
    const response=await app.inject({method:'POST',url:'/cn/load',payload:{viewer_id:p.viewer}})
    const data=decode(response)
    assert.deepEqual(data.star_crumb_exchange_retained_ids,rules.getRetainedStarCrumbExchangeIds())
    assert.ok(data.content_operations);assert.equal(data.user_info.star_crumb,20000)
})
test('independent operations refresh sends the same retained IDs without touching player state',async()=>{
    const p=player(),before=state(p.id)
    const response=await app.inject({method:'POST',url:'/cn/content_operations',payload:{viewer_id:p.viewer}})
    const data=decode(response)
    assert.deepEqual(data.star_crumb_exchange_retained_ids,rules.getRetainedStarCrumbExchangeIds())
    assert.ok(data.content_operations);assert.deepEqual(state(p.id),before)
    const denied=await app.inject({method:'POST',url:'/cn/content_operations',payload:{viewer_id:999999999}})
    assert.equal(denied.statusCode,401);assert.equal(denied.json().star_crumb_exchange_retained_ids,undefined)
})
test('retained 307 grants its original character, charges once and preserves duplicate rejection',async()=>{
    const p=player(),cost=costFor(307),target=Number(master[307][0][1])
    assert.equal(characters.playerOwnsCharacterSync(p.id,target),false)
    const data=decode(await post(p,307))
    assert.equal(players.getPlayerSync(p.id).starCrumb,20000-cost)
    assert.ok(characters.playerOwnsCharacterSync(p.id,target));assert.ok(data.character_list.some(row=>row.character_id===target))
    const before=state(p.id),duplicate=await post(p,307)
    assert.equal(duplicate.statusCode,400);assert.match(duplicate.body,/already owned/);assert.deepEqual(state(p.id),before)
})
test('expired non-retained product is rejected without player, item or equipment changes',async()=>{
    const p=player(),before=state(p.id),response=await post(p,1)
    assert.equal(response.statusCode,400);assert.match(response.body,/not currently available/)
    assert.deepEqual(state(p.id),before)
})
test('both current item products retain their original cost and insufficient funds leave state unchanged',async()=>{
    for(const id of [9000001,9000002]) {
        const p=player(),target=Number(master[id][0][1]),old=items.getPlayerItemSync(p.id,target)||0
        decode(await post(p,id));assert.equal(items.getPlayerItemSync(p.id,target),old+1)
        assert.equal(players.getPlayerSync(p.id).starCrumb,20000-costFor(id))
    }
    const p=player(0),before=state(p.id),response=await post(p,9000001)
    assert.equal(response.statusCode,400);assert.match(response.body,/Not enough/);assert.deepEqual(state(p.id),before)
})
test('retained equipment keeps its existing ownership check and original price',async()=>{
    const id=rules.getRetainedStarCrumbExchangeIds().find(id=>master[id][0][0]==='2')
    const p=player(),target=Number(master[id][0][1])
    decode(await post(p,id));assert.ok(equipment.playerOwnsEquipmentSync(p.id,target))
    assert.equal(players.getPlayerSync(p.id).starCrumb,20000-costFor(id))
    const before=state(p.id);assert.equal((await post(p,id)).statusCode,400);assert.deepEqual(state(p.id),before)
})
test('availability is checked after the transaction queue admits the final write',async()=>{
    const p=player(),originalRule=rules.isStarCrumbExchangeAvailable
    let admitted=false,calls=0,release
    const held=new Promise(resolve=>{release=resolve})
    coordinator.runPersistenceTransaction=async(context,write)=>{
        if(context.operation!=='star_crumb_exchange')return originalTransaction(context,write)
        await held
        return originalTransaction(context,()=>{admitted=true;try{return write()}finally{admitted=false}})
    }
    rules.isStarCrumbExchangeAvailable=(id,time)=>{
        calls++;assert.equal(admitted,true);assert.equal(id,9000001);assert.equal(typeof time,'number')
        return false // Permission removed while this request was waiting.
    }
    try {
        const before=state(p.id),pending=post(p,9000001)
        await new Promise(resolve=>setImmediate(resolve));assert.equal(calls,0);release()
        const response=await pending;assert.equal(response.statusCode,400);assert.equal(calls,1)
        assert.deepEqual(state(p.id),before)
    } finally {release();rules.isStarCrumbExchangeAvailable=originalRule;coordinator.runPersistenceTransaction=originalTransaction}
})
test('existing personal-product transaction behavior remains unchanged without granting new personal windows',async()=>{
    const p=player(),id=Number(Object.keys(master).find(id=>personal(master[id][0])))
    decode(await post(p,id));assert.equal(players.getPlayerSync(p.id).starCrumb,20000-costFor(id))
    assert.equal(rules.getRetainedStarCrumbExchangeIds().includes(id),false)
})

test('ordinary and personal IDs for one character share ownership protection without a second charge',async()=>{
    const personalId=1415,ordinaryId=2231,target=Number(master[personalId][0][1])
    assert.equal(Number(master[ordinaryId][0][1]),target)
    assert.equal(costFor(personalId),costFor(ordinaryId))
    for(const [first,second] of [[ordinaryId,personalId],[personalId,ordinaryId]]) {
        const p=player()
        assert.equal(characters.playerOwnsCharacterSync(p.id,target),false)
        decode(await post(p,first))
        assert.equal(players.getPlayerSync(p.id).starCrumb,20000-costFor(first))
        const before=state(p.id),duplicate=await post(p,second)
        assert.equal(duplicate.statusCode,400)
        assert.match(duplicate.body,/already owned/)
        assert.deepEqual(state(p.id),before,'alternate product ID cannot charge or grant twice')
    }
})
