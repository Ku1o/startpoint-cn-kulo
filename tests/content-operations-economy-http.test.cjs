'use strict'
const {test,before,after}=require('node:test')
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path')
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'content-economy-'))
process.env.DATA_DIR=directory;process.env.GACHA_SEED_DIR=path.join(directory,'seeds')
process.env.CN_WRITER_THREAD='0';process.env.GAME_ROUTINE_LOGS='off';process.env.GAME_VERBOSE_LOGS='false'
const Fastify=require('fastify'),{pack,unpack}=require('msgpackr')
const db=require('../out/data/db').getDb()
const players=require('../out/data/domains/player'),operations=require('../out/lib/content-operations')
const coordinator=require('../out/lib/persistence-coordinator'),transaction=coordinator.runPersistenceTransaction
const passes=require('../out/data/domains/pass-card'),passDefinitions=require('../out/lib/pass-card')
const assets=require('../out/lib/assets'),items=require('../out/data/domains/item')
let app,playerId,viewerId,passId,rewards
const open={readiness:'verified',evidence:'synthetic fixture, no device acceptance',flags:{visible:true,enter:true,claim:true},endsAtMs:null}
function control(key,input={}) {const store=operations.contentOperations();return store.update(key,{expectedRevision:store.revision(),catalogDigest:store.digest,reason:'isolated fixture',...input},Date.now())}
function post(url,body={}) {return app.inject({method:'POST',url,payload:{viewer_id:viewerId,...body}})}
function decode(response) {assert.equal(response.statusCode,200,response.body);return unpack(Buffer.from(response.body,'base64')).data}
function resultCode(response) {assert.equal(response.statusCode,200,response.body);return unpack(Buffer.from(response.body,'base64')).data_headers.result_code}
function passRows() {return {state:passes.getPlayerPassCardStateSync(playerId,passId),records:passes.getPlayerPassCardRewardRecordsSync(playerId,passId)}}
function playerTables() {
    return Object.fromEntries(['players','players_pass_cards','players_pass_card_rewards','players_items','players_receive_history','players_shop_purchases','players_shop_quotas','players_equipment','players_box_gacha','players_box_gacha_drawn_rewards','players_multi_special_exchange_campaigns','players_start_dash_exchange_campaigns','players_characters'].map(table=>[
        table,db.prepare(`SELECT * FROM ${table} WHERE ${table==='players'?'id':'player_id'}=? ORDER BY rowid`).all(playerId),
    ]))
}
before(async()=>{
    assert.ok(fs.realpathSync(db.name).startsWith(fs.realpathSync(directory)+path.sep))
    const account=require('../out/data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'economy-ops',idpId:'fixture',status:'normal'})
    playerId=players.insertDefaultPlayerSync(account.id).id;viewerId=850000000+playerId
    require('../out/data/activeAccount').saveAccountDefaultPlayer(account.id,playerId)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewerId),account.id,'2099-01-01T00:00:00Z')
    const row=operations.contentCatalog.rows.find(row=>row.type==='pass_card_event'&&row.definitionEvidence?.status==='matched'
        &&operations.contentCapabilities(row).includes('claim')&&passDefinitions.getPassCardEventDefinition(row.id))
    assert.ok(row,'matched pass fixture')
    passId=row.id
    rewards=Object.keys(require('../assets/pass_card_reward.json')).map(Number).map(passDefinitions.getPassCardRewardDefinition)
        .filter(reward=>reward?.eventId===passId&&reward.level>=1).sort((a,b)=>a.level-b.level).slice(0,3)
    assert.equal(rewards.length,3)
    passes.addPlayerPassCardPointSync(playerId,passId,10000)
    players.updatePlayerSync({id:playerId,freeMana:100000000,paidMana:100000000,freeVmoney:100000000,vmoney:100000000,bondToken:100000000})
    app=Fastify({logger:false})
    app.addHook('onSend',(_request,reply,body,done)=>done(null,String(reply.getHeader('content-type')).startsWith('application/x-msgpack')?pack(body).toString('base64'):body))
    await app.register(require('../out/routes/api/passCard').default,{prefix:'/pass'})
    await app.register(require('../out/routes/api/shop').default,{prefix:'/shop'})
    await app.register(require('../out/routes/api/boxGacha').default,{prefix:'/box'})
    await app.register(require('../out/routes/api/multiSpecialExchange').default,{prefix:'/multi-exchange'})
    await app.ready()
})
after(async()=>{
    coordinator.runPersistenceTransaction=transaction
    if(app)await app.close()
    await require('../out/lib/seed-validator').default.close()
    if(db.open)db.close()
    assert.ok(path.resolve(directory).startsWith(path.resolve(os.tmpdir())+path.sep))
    fs.rmSync(directory,{recursive:true})
})
test('historical pass opens by operations and enter closure retains independently earned free claims',async()=>{
    control(`pass_card_event:${passId}`,open)
    const initial=decode(await post('/pass/get_pass_card',{pass_card_id:passId}))
    assert.equal(initial.point,10000);assert.equal(initial.is_buy,false)
    control(`pass_card_event:${passId}`,{flags:{enter:false}})
    const body={pass_card_id:passId,reward1_receive:[rewards[0].rewardId]}
    decode(await post('/pass/receive_all',body))
    assert.equal(passes.getPlayerPassCardRewardRecordsSync(playerId,passId).find(row=>row.rewardId===rewards[0].rewardId).isReceived1,1)
    control(`pass_card_event:${passId}`,{flags:{claim:false}})
    const saved=playerTables()
    decode(await post('/pass/receive_all',body))
    assert.deepEqual(playerTables(),saved,'committed received tracks replay without granting again')
    assert.equal((await post('/pass/receive_all',{pass_card_id:passId,reward1_receive:[rewards[1].rewardId]})).statusCode,400)
    assert.deepEqual(playerTables(),saved,'new claim after closure preserves balances/points/received tracks')
})
test('pass claim closes at final transaction and paid tracks retain the purchase requirement',async()=>{
    control(`pass_card_event:${passId}`,open)
    const saved=playerTables()
    let queued=false
    coordinator.runPersistenceTransaction=async(context,fn,options)=>{
        if(context.operation==='receive_pass_card'){queued=true;control(`pass_card_event:${passId}`,{flags:{claim:false}})}
        return transaction(context,fn,options)
    }
    try {
        assert.equal((await post('/pass/receive_all',{pass_card_id:passId,reward1_receive:[rewards[1].rewardId]})).statusCode,400)
        assert.equal(queued,true);assert.deepEqual(playerTables(),saved)
    } finally {coordinator.runPersistenceTransaction=transaction}
    control(`pass_card_event:${passId}`,open)
    assert.equal((await post('/pass/receive_all',{pass_card_id:passId,reward2_receive:[rewards[1].rewardId]})).statusCode,400)
    assert.deepEqual(playerTables(),saved,'global opening cannot grant the paid track entitlement')
})
test('pass grant failure rolls back reward and received marker, then same claim succeeds',async()=>{
    control(`pass_card_event:${passId}`,open)
    const saved=playerTables(),grants=require('../out/lib/mission/grants')
    const persist=grants.MissionRewardGranter.prototype.persistPlayer
    grants.MissionRewardGranter.prototype.persistPlayer=function(){persist.call(this);throw Error('fixture grant persistence failure')}
    const body={pass_card_id:passId,reward1_receive:[rewards[2].rewardId]}
    try {assert.equal((await post('/pass/receive_all',body)).statusCode,500);assert.deepEqual(playerTables(),saved)}
    finally {grants.MissionRewardGranter.prototype.persistPlayer=persist}
    decode(await post('/pass/receive_all',body))
    assert.equal(passes.getPlayerPassCardRewardRecordsSync(playerId,passId).find(row=>row.rewardId===rewards[2].rewardId).isReceived1,1)
})
test('close and reopen plus V2 import preserve pass points/claims and global operations state',()=>{
    const before=passRows(),key=`pass_card_event:${passId}`
    control(key,{flags:{visible:false,enter:false,claim:false}})
    control(key,open)
    assert.deepEqual(passRows(),before)
    const snapshots=require('../out/data/snapshots/player-snapshot'),archive=snapshots.createPlayerSaveSnapshotV2Sync(playerId,db)
    const state=operations.contentOperations().snapshot(Date.now())
    snapshots.restorePlayerSaveSnapshotV2Sync(archive,playerId,{},db)
    assert.deepEqual(passRows(),before)
    assert.deepEqual(operations.contentOperations().snapshot(state.server_time_ms),state)
    assert.equal(snapshots.createPlayerSaveSnapshotV2Sync(playerId,db).schemaFingerprint,archive.schemaFingerprint)
})
test('ordinary and event products preserve stock, budgets and progress through closure and transaction rollback',async t=>{
    for(const [type,shopType] of [['general_shop',8],['star_grain_shop',9],['treasure_shop',2],['boss_coin_shop',7],['event_item_shop',4]]) {
        await t.test(type,async()=>{
            const candidates=operations.contentCatalog.rows.filter(row=>row.type===type)
            assert.ok(candidates.length,`${type} catalog inventory`)
            const row=candidates.find(row=>{
                const item=assets.getShopItemSync(shopType,row.id)
                return row.definitionEvidence?.status==='matched'&&operations.contentOperations().runtimeDefinitions.get(row.key)?.matchesCatalog&&operations.contentCapabilities(row).includes('exchange')
                    &&Number.isSafeInteger(item?.stock)&&item.stock>0&&item.stock<=1000&&(!item.dailyStock||item.dailyStock===item.stock)&&!item.monthlyStock&&!item.maxFrequency
                    &&require('../out/data/domains/shopPurchase').getPlayerShopPurchaseCountSync(playerId,
                        require('../out/lib/shop-sales').getShopPurchaseKey(shopType,row.id))<item.stock
                    &&item.rewards.length&&item.rewards.every(reward=>reward.type!==3&&reward.type!==5)
            })
            if(!row) {
                // Missing complete frequency/availability evidence does not create a
                // synthetic success case or permit unsupported manual activation.
                const unsupported=candidates.find(row=>!operations.contentCapabilities(row).includes('exchange')||!operations.contentOperations().runtimeDefinitions.get(row.key)?.matchesCatalog)
                assert.ok(unsupported,`${type} needs a complete guarded product or explicit unsupported rows`)
                const saved=playerTables()
                assert.throws(()=>control(unsupported.key,{...open,flags:{visible:true,exchange:true}}))
                assert.deepEqual(playerTables(),saved)
                if(!operations.contentOperations().runtimeDefinitions.get(unsupported.key)?.matchesCatalog)t.diagnostic(`${type}: source identity drift is correctly refused; positive operation awaits reviewed current row evidence`)
                return
            }
            const item=assets.getShopItemSync(shopType,row.id)
            for(const cost of item.costs)items.setPlayerItemSync(playerId,cost.id,10000000)
            const enabled={...open,flags:{visible:true,exchange:true}}
            const purchased=require('../out/data/domains/shopPurchase').getPlayerShopPurchaseCountSync(playerId,
                require('../out/lib/shop-sales').getShopPurchaseKey(shopType,row.id))
            const body={shop_type:shopType,shop_item_id:row.id,number:item.stock-purchased,api_count:1}
            const eventMap=require('../out/lib/content-master').serverEventShopIdMap[row.id]
            const salesBody={shop_types:[shopType],boss_coin_shop_category_ids:shopType===7
                ?[require('../assets/boss_coin_shop_item_category_map.json')[row.id]]:[],equipment_enhancement_category_ids:[],
                event_list:shopType===4?[{event_type:eventMap.eventType,event_ids:[eventMap.eventId]}]:[]}
            if(row.parentKey)control(row.parentKey,{...open,flags:{visible:true,exchange:true}})
            control(row.key,enabled)
            assert.ok(decode(await post('/shop/get_sales_list',salesBody)).sales_list.some(product=>product.shop_item_id===row.id))
            control(row.key,{flags:{visible:false,exchange:false}})
            assert.ok(!decode(await post('/shop/get_sales_list',salesBody)).sales_list.some(product=>product.shop_item_id===row.id))
            let saved=playerTables(),queued=false
            coordinator.runPersistenceTransaction=async(context,fn,options)=>{
                if(context.operation==='purchase')queued=true
                return transaction(context,fn,options)
            }
            try {assert.equal((await post('/shop/buy',body)).statusCode,400);assert.equal(queued,false);assert.deepEqual(playerTables(),saved)}
            finally {coordinator.runPersistenceTransaction=transaction}
            decode(await post('/shop/bulk_buy',{shop_type:shopType,buy_item_list:{[row.id]:1},api_count:2}))
            assert.deepEqual(playerTables(),saved,'bulk skips an explicitly closed product without costs or stock changes')
            control(row.key,enabled)
            coordinator.runPersistenceTransaction=async(context,fn,options)=>{
                if(context.operation==='purchase'){queued=true;control(row.key,{flags:{exchange:false}})}
                return transaction(context,fn,options)
            }
            try {assert.equal((await post('/shop/buy',body)).statusCode,400);assert.equal(queued,true);assert.deepEqual(playerTables(),saved)}
            finally {coordinator.runPersistenceTransaction=transaction}
            control(row.key,enabled)
            coordinator.runPersistenceTransaction=async(context,fn,options)=>transaction(context,context.operation==='purchase'?()=>{
                const result=fn();if(result.ok)throw Error('fixture purchase failure after reward');return result
            }:fn,options)
            try {assert.equal((await post('/shop/buy',body)).statusCode,500);assert.deepEqual(playerTables(),saved)}
            finally {coordinator.runPersistenceTransaction=transaction}
            decode(await post('/shop/buy',body))
            saved=playerTables()
            assert.equal((await post('/shop/buy',body)).statusCode,400,'duplicate cannot exceed stock')
            assert.deepEqual(playerTables(),saved)
            control(row.key,{flags:{visible:false,exchange:false}});control(row.key,enabled)
            assert.deepEqual(playerTables(),saved,'reopen never resets stock or balances')
            const snapshots=require('../out/data/snapshots/player-snapshot'),archive=snapshots.createPlayerSaveSnapshotV2Sync(playerId,db)
            const state=operations.contentOperations().snapshot(Date.now())
            snapshots.restorePlayerSaveSnapshotV2Sync(archive,playerId,{},db)
            assert.deepEqual(require('../out/data/domains/shopPurchase').getPlayerShopPurchasesMapSync(playerId),
                Object.fromEntries(saved.players_shop_purchases.map(row=>[row.shop_item_id,row.count])))
            assert.deepEqual(operations.contentOperations().snapshot(state.server_time_ms),state)
        })
    }
})
test('an open parent does not approve an unowned expired or unsupported quota product',async()=>{
    const economy=require('../out/lib/content-economy-operations'),sales=require('../out/lib/shop-sales')
    const mapping=require('../out/lib/content-master').serverEventShopIdMap
    const parentTypes={0:'advent_event',2:'story_event',4:'challenge_dungeon_event',6:'world_story_event',9:'collect_item_event',10:'carnival_event',11:'rush_event',12:'score_attack_event'}
    const row=operations.contentCatalog.rows.find(row=>{
        if(row.type!=='event_item_shop'||row.definitionEvidence?.status!=='matched'
            ||!operations.contentCapabilities(row).includes('exchange')||operations.contentOperations().state(row.key))return false
        const item=assets.getShopItemSync(4,row.id),map=mapping[row.id]
        const parent=map&&operations.contentCatalog.rows.find(candidate=>candidate.key===`${parentTypes[map.eventType]}:${map.eventId}`)
        return item&&map&&parent?.definitionEvidence?.status==='matched'
            &&operations.contentCapabilities(parent).includes('exchange')
            &&!sales.isShopItemAvailable(item,require('../out/utils').getServerDate())
    })
    assert.ok(row,'actual expired unowned event product with a verified parent')
    const map=mapping[row.id],parentKey=`${parentTypes[map.eventType]}:${map.eventId}`
    const item=assets.getShopItemSync(4,row.id)
    control(parentKey,{...open,flags:{visible:true,exchange:true}})
    assert.equal(economy.shopContentDecision(4,row.id,'exchange'),false,'parent open never grants an unapproved timed product')
    const saved=playerTables()
    assert.equal((await post('/shop/buy',{shop_type:4,shop_item_id:row.id,number:1,api_count:1})).statusCode,400)
    assert.deepEqual(playerTables(),saved,'expired unowned product consumes no funds or stock')
    const listing=decode(await post('/shop/get_sales_list',{shop_types:[4],boss_coin_shop_category_ids:[],equipment_enhancement_category_ids:[],event_list:[{event_type:map.eventType,event_ids:[map.eventId]}]}))
    assert.ok(!listing.sales_list.some(product=>product.shop_item_id===row.id))
    // Baseline event products currently have no per-day quotas. Inject only
    // a supported quota field into this synthetic runtime fixture, never
    // into the catalog or source data, and verify parent approval still cannot approve a product.
    const previous=item.dailyStock
    try {
        item.dailyStock=1
        assert.deepEqual(economy.contentEconomyCapabilities(row),['visible','exchange'],'periodic products now have persistent quotas; parent opening still does not approve this product')
        assert.equal(economy.shopContentDecision(4,row.id,'exchange'),false)
        assert.equal((await post('/shop/buy',{shop_type:4,shop_item_id:row.id,number:1,api_count:1})).statusCode,400)
        assert.deepEqual(playerTables(),saved)
    } finally {if(previous===undefined)delete item.dailyStock;else item.dailyStock=previous}
    if(!operations.contentOperations().runtimeDefinitions.get(row.key)?.matchesCatalog) {
        const revision=operations.contentOperations().revision()
        assert.throws(()=>control(row.key,{...open,flags:{visible:true,exchange:true}}),/目录已过时/)
        assert.equal(operations.contentOperations().revision(),revision)
        assert.deepEqual(playerTables(),saved,'stale current source identities cannot be approved by old catalog')
        control(parentKey,{flags:{exchange:false}})
        assert.equal(economy.shopContentDecision(4,row.id,'exchange'),false)
        return
    }
    control(row.key,{...open,flags:{visible:true,exchange:true}})
    assert.equal(economy.shopContentDecision(4,row.id,'exchange'),true,'explicit product approval may override its old date')
    control(parentKey,{flags:{exchange:false}})
    assert.equal(economy.shopContentDecision(4,row.id,'exchange'),false,'parent closure remains a total gate')
    assert.equal((await post('/shop/buy',{shop_type:4,shop_item_id:row.id,number:1,api_count:1})).statusCode,400)
    assert.deepEqual(playerTables(),saved)
})

test('box controls guard draws and preserve inventory, required-box rules, terminal closes and import progress',async()=>{
    const row=operations.contentCatalog.rows.find(row=>row.key==='box_gacha:1001')
    assert.ok(row)
    const enabled={...open,flags:{visible:true,enter:true,claim:true}}
    if(!operations.contentCapabilities(row).includes('enter')) {
        const saved=playerTables()
        assert.throws(()=>control(row.key,enabled),'no complete policy evidence cannot be opened')
        assert.deepEqual(playerTables(),saved)
        return
    }
    const boxes=require('../out/data/domains/boxGacha'),master=assets.getBoxGachaSync(1001)
    assert.ok(master?.boxes[1])
    items.setPlayerItemSync(playerId,master.redeemItemId,10000000)
    const exec={box_gacha_id:1001,box_id:1,number:1,stop_on_featured_rewards:false,api_count:1}
    control(row.key,enabled);control(row.key,{flags:{enter:false}})
    let saved=playerTables(),queued=false
    coordinator.runPersistenceTransaction=async(context,fn,options)=>{
        if(context.operation==='box_exec')queued=true
        return transaction(context,fn,options)
    }
    try {assert.equal((await post('/box/exec',exec)).statusCode,400);assert.equal(queued,false);assert.deepEqual(playerTables(),saved)}
    finally {coordinator.runPersistenceTransaction=transaction}
    control(row.key,enabled)
    coordinator.runPersistenceTransaction=async(context,fn,options)=>{
        if(context.operation==='box_exec'){queued=true;control(row.key,{flags:{enter:false}})}
        return transaction(context,fn,options)
    }
    try {assert.equal((await post('/box/exec',exec)).statusCode,400);assert.equal(queued,true);assert.deepEqual(playerTables(),saved)}
    finally {coordinator.runPersistenceTransaction=transaction}
    control(row.key,enabled)
    coordinator.runPersistenceTransaction=async(context,fn,options)=>transaction(context,context.operation==='box_exec'?()=>{
        const result=fn();if(!('errorMessage' in result))throw Error('fixture box failure after draw');return result
    }:fn,options)
    try {assert.equal((await post('/box/exec',exec)).statusCode,500);assert.deepEqual(playerTables(),saved)}
    finally {coordinator.runPersistenceTransaction=transaction}
    decode(await post('/box/exec',exec))
    const box=boxes.getPlayerBoxGachaSync(playerId,1001,1)
    assert.equal(box.remainingNumber,Object.values(master.boxes[1]).reduce((sum,reward)=>sum+reward.available,0)-1)
    assert.equal(boxes.getPlayerBoxGachaDrawnRewardsSync(playerId,1001,1).reduce((sum,reward)=>sum+reward.number,0),1)
    saved=playerTables()
    assert.equal((await post('/box/reset',{box_gacha_id:1001,box_id:1})).statusCode,400,'1001 resetKind=never remains enforced')
    assert.equal((await post('/box/close',{box_gacha_id:1001,box_id:1})).statusCode,400,'1001 close requires exhausted rewards')
    assert.equal((await post('/box/exec',{...exec,box_id:2})).statusCode,400,'previous box requirement remains enforced')
    assert.deepEqual(playerTables(),saved)
    for(const [id,reward] of Object.entries(master.boxes[1])) {
        const drawn=boxes.getPlayerBoxGachaDrawnRewardsSync(playerId,1001,1).find(row=>row.id===Number(id))
        if(drawn)boxes.updatePlayerBoxGachaDrawnRewardSync(playerId,1001,1,Number(id),reward.available)
        else boxes.insertPlayerBoxGachaDrawnRewardSync(playerId,1001,1,{id:Number(id),number:reward.available})
    }
    boxes.updatePlayerBoxGachaSync(playerId,1001,{boxId:1,isClosed:false,remainingNumber:0})
    control(row.key,{flags:{enter:false,claim:true}})
    const settled=decode(await post('/box/close',{box_gacha_id:1001,box_id:1}))
    control(row.key,{flags:{claim:false}})
    saved=playerTables()
    assert.deepEqual(decode(await post('/box/close',{box_gacha_id:1001,box_id:1})),settled)
    assert.deepEqual(playerTables(),saved,'closed terminal state replays without resetting or rewriting')
    control(row.key,enabled);assert.deepEqual(playerTables(),saved)
    const snapshots=require('../out/data/snapshots/player-snapshot'),archive=snapshots.createPlayerSaveSnapshotV2Sync(playerId,db)
    const state=operations.contentOperations().snapshot(Date.now())
    snapshots.restorePlayerSaveSnapshotV2Sync(archive,playerId,{},db)
    assert.deepEqual(boxes.getPlayerBoxGachaSync(playerId,1001,1),{boxId:1,isClosed:true,remainingNumber:0,resetTimes:0})
    assert.deepEqual(operations.contentOperations().snapshot(state.server_time_ms),state)
})
test('native unbounded box dates preserve policy validation without accepting malformed dates',()=>{
    const policy=require('../out/lib/box-gacha-policy')
    const row=operations.contentCatalog.rows.find(row=>row.key==='box_gacha:28')
    const master=assets.getBoxGachaSync(28)
    assert.ok(row&&master)
    const rules=policy.getBoxOperationRules(row,master.boxes)
    assert.ok(rules,'the actual July raid box has an explicit native None end')
    assert.equal(rules.get(1).availableUntil,null)
    assert.deepEqual(operations.contentCapabilities(row),['visible','enter','claim'])
    for(const invalid of ['invalid-date','',undefined]) {
        const bad={...row,boxRules:{...row.boxRules,1:{...row.boxRules[1],availableUntil:invalid}}}
        assert.equal(policy.getBoxOperationRules(bad,master.boxes),null)
    }
})

test('July raid box closes only its exact tier and resets only an empty resettable box',async()=>{
    const boxes=require('../out/data/domains/boxGacha')
    const row=operations.contentCatalog.rows.find(row=>{
        if(row.type!=='box_gacha'||row.id!==28||row.definitionEvidence?.status!=='matched'
            ||!operations.contentCapabilities(row).includes('claim'))return false
        const master=assets.getBoxGachaSync(row.id)
        return master&&Object.entries(row.boxRules||{}).some(([boxId,rule])=>rule.resetKind===0&&rule.closeKind===1
            &&rule.requiredBoxId===null&&Object.values(master.boxes[boxId]).some(reward=>reward.tier===2)
            &&Object.values(master.boxes[boxId]).some(reward=>reward.tier===1))
            &&Object.values(row.boxRules||{}).some(rule=>rule.resetKind===2)
    })
    assert.ok(row,'real complete generic policy with exact featured close and empty reset')
    const master=assets.getBoxGachaSync(row.id),rules=row.boxRules
    const [firstId]=Object.entries(rules).find(([boxId,rule])=>rule.resetKind===0&&rule.closeKind===1
        &&rule.requiredBoxId===null&&Object.values(master.boxes[boxId]).some(reward=>reward.tier===2)
        &&Object.values(master.boxes[boxId]).some(reward=>reward.tier===1))
    const first=Number(firstId),all=Object.values(master.boxes[first]).reduce((sum,reward)=>sum+reward.available,0)
    const enabled={...open,flags:{visible:true,enter:true,claim:true}}
    control(row.key,enabled)
    boxes.insertPlayerBoxGachaSync(playerId,row.id,{boxId:first,resetTimes:0,isClosed:false,remainingNumber:all})
    let saved=playerTables()
    assert.equal((await post('/box/close',{box_gacha_id:row.id,box_id:first})).statusCode,400)
    assert.deepEqual(playerTables(),saved)
    let drawn=0
    for(const [id,reward] of Object.entries(master.boxes[first]))if(reward.tier===2){
        boxes.insertPlayerBoxGachaDrawnRewardSync(playerId,row.id,first,{id:Number(id),number:reward.available});drawn+=reward.available
    }
    boxes.updatePlayerBoxGachaSync(playerId,row.id,{boxId:first,isClosed:false,remainingNumber:all-drawn})
    const closed=decode(await post('/box/close',{box_gacha_id:row.id,box_id:first}))
    assert.ok(boxes.getPlayerBoxGachaSync(playerId,row.id,first).remainingNumber>0,'rare and normal rewards remain')
    saved=playerTables()
    decode(await post('/box/close',{box_gacha_id:row.id,box_id:first}))
    assert.deepEqual(playerTables(),saved,'terminal repetition preserves exact drawn tiers')
    const [resetId,resetRule]=Object.entries(rules).find(([,rule])=>rule.resetKind===2)
    const resetBox=Number(resetId)
    if(resetRule.requiredBoxId!==null&&!boxes.getPlayerBoxGachaSync(playerId,row.id,resetRule.requiredBoxId)) {
        boxes.insertPlayerBoxGachaSync(playerId,row.id,{boxId:resetRule.requiredBoxId,resetTimes:0,isClosed:true,remainingNumber:1})
    }
    const total=Object.values(master.boxes[resetBox]).reduce((sum,reward)=>sum+reward.available,0)
    boxes.insertPlayerBoxGachaSync(playerId,row.id,{boxId:resetBox,resetTimes:0,isClosed:false,remainingNumber:total})
    saved=playerTables()
    assert.equal((await post('/box/close',{box_gacha_id:row.id,box_id:resetBox})).statusCode,400,'resettable boxes cannot close manually')
    assert.equal((await post('/box/reset',{box_gacha_id:row.id,box_id:resetBox})).statusCode,400,'nonempty reset is rejected')
    assert.deepEqual(playerTables(),saved)
    for(const [id,reward] of Object.entries(master.boxes[resetBox]))boxes.insertPlayerBoxGachaDrawnRewardSync(playerId,row.id,resetBox,{id:Number(id),number:reward.available})
    boxes.updatePlayerBoxGachaSync(playerId,row.id,{boxId:resetBox,isClosed:true,remainingNumber:0})
    decode(await post('/box/reset',{box_gacha_id:row.id,box_id:resetBox}))
    assert.equal(boxes.getPlayerBoxGachaSync(playerId,row.id,resetBox).resetTimes,1)
    assert.equal(boxes.getPlayerBoxGachaSync(playerId,row.id,resetBox).remainingNumber,total)
    assert.deepEqual(boxes.getPlayerBoxGachaDrawnRewardsSync(playerId,row.id,resetBox),[])
    saved=playerTables()
    assert.equal((await post('/box/reset',{box_gacha_id:row.id,box_id:resetBox})).statusCode,400)
    assert.deepEqual(playerTables(),saved,'repeat cannot reset a refilled box twice')
    control(row.key,{flags:{enter:false}})
    assert.deepEqual(playerTables(),saved)
    assert.equal((await post('/box/reset',{box_gacha_id:row.id,box_id:resetBox})).statusCode,400)
})
test('multi-special ticket acquisition and exchange guard the final transaction while preserving earned and completed rights',async()=>{
    const campaigns=require('../out/data/domains/campaign'),definition=require('../out/lib/multi-special-exchange')
    const row=operations.contentCatalog.rows.find(row=>row.type==='multi_special_exchange_campaign'
        &&row.definitionEvidence?.status==='matched'&&definition.getMultiSpecialExchangeCampaignDefinition(row.id)
        &&operations.contentCapabilities(row).includes('exchange'))
    assert.ok(row,'complete supported multi-special campaign fixture')
    const enabled={...open,flags:{visible:true,enter:true,exchange:true}}
    const campaignId=row.id,drawBody={campaign_id:campaignId},drawRoute='/multi-exchange/single_draw_ticket'
    campaigns.updatePlayerMultiSpecialExchangeCampaignSync(playerId,{campaignId,status:1,ticketItemId:null})
    if(!operations.contentOperations().runtimeDefinitions.get(row.key)?.matchesCatalog) {
        const saved=playerTables(),revision=operations.contentOperations().revision()
        assert.throws(()=>control(row.key,enabled),/目录已过时/)
        assert.equal(operations.contentOperations().revision(),revision)
        assert.deepEqual(playerTables(),saved,'stale campaign proof cannot reset or grant a ticket')
        return
    }
    control(row.key,enabled);control(row.key,{flags:{enter:false}})
    let saved=playerTables(),queued=false
    coordinator.runPersistenceTransaction=async(context,fn,options)=>{
        if(context.operation==='draw_multi_special_ticket')queued=true
        return transaction(context,fn,options)
    }
    try {assert.equal(resultCode(await post(drawRoute,drawBody)),4902);assert.equal(queued,false);assert.deepEqual(playerTables(),saved)}
    finally {coordinator.runPersistenceTransaction=transaction}
    control(row.key,enabled)
    coordinator.runPersistenceTransaction=async(context,fn,options)=>{
        if(context.operation==='draw_multi_special_ticket'){queued=true;control(row.key,{flags:{enter:false}})}
        return transaction(context,fn,options)
    }
    try {assert.equal(resultCode(await post(drawRoute,drawBody)),4902);assert.equal(queued,true);assert.deepEqual(playerTables(),saved)}
    finally {coordinator.runPersistenceTransaction=transaction}
    control(row.key,enabled)
    const drawn=decode(await post(drawRoute,drawBody)),ticket=drawn.multi_special_exchange_campaign_list[0].ticket_item_id
    control(row.key,{flags:{enter:false}})
    saved=playerTables()
    assert.deepEqual(decode(await post(drawRoute,drawBody)),drawn,'a paid-out ticket repeats after acquisition closes')
    assert.deepEqual(playerTables(),saved)
    const character=require('../assets/multi_special_exchange_campaign_character.json')[ticket][0]
    const exchangeBody={campaign_id:campaignId,ticket_item_id:ticket,character_id:character}
    control(row.key,{flags:{exchange:false}})
    assert.equal(resultCode(await post('/multi-exchange/exchange_character',exchangeBody)),4902)
    assert.deepEqual(playerTables(),saved)
    control(row.key,{flags:{exchange:true}})
    coordinator.runPersistenceTransaction=async(context,fn,options)=>{
        if(context.operation==='exchange_character')control(row.key,{flags:{exchange:false}})
        return transaction(context,fn,options)
    }
    try {assert.equal(resultCode(await post('/multi-exchange/exchange_character',exchangeBody)),4902);assert.deepEqual(playerTables(),saved)}
    finally {coordinator.runPersistenceTransaction=transaction}
    control(row.key,{flags:{exchange:true}})
    coordinator.runPersistenceTransaction=async(context,fn,options)=>transaction(context,context.operation==='exchange_character'?()=>{
        const value=fn();if(value?.reward)throw Error('fixture campaign failure after reward');return value
    }:fn,options)
    try {assert.equal((await post('/multi-exchange/exchange_character',exchangeBody)).statusCode,500);assert.deepEqual(playerTables(),saved)}
    finally {coordinator.runPersistenceTransaction=transaction}
    const completed=decode(await post('/multi-exchange/exchange_character',exchangeBody))
    assert.equal(completed.multi_special_exchange_campaign_list[0].status,4)
    assert.equal(items.getPlayerItemSync(playerId,ticket),drawn.item_list[ticket]-1)
    control(row.key,{flags:{exchange:false}})
    saved=playerTables()
    const repeat=decode(await post('/multi-exchange/exchange_character',exchangeBody))
    assert.equal(repeat.multi_special_exchange_campaign_list[0].status,4)
    assert.deepEqual(repeat.character_list,[],'legacy completion never invents a missing choice receipt')
    assert.deepEqual(playerTables(),saved)
    control(row.key,enabled);assert.deepEqual(playerTables(),saved)
    const snapshots=require('../out/data/snapshots/player-snapshot'),archive=snapshots.createPlayerSaveSnapshotV2Sync(playerId,db)
    const state=operations.contentOperations().snapshot(Date.now())
    snapshots.restorePlayerSaveSnapshotV2Sync(archive,playerId,{},db)
    assert.deepEqual(campaigns.getPlayerMultiSpecialExchangeCampaignsSync(playerId).find(value=>value.campaignId===campaignId),
        {campaignId,status:4,ticketItemId:null})
    assert.deepEqual(operations.contentOperations().snapshot(state.server_time_ms),state)
})
test('special and personal StartDash expose exchange-only, reject acquisition, and preserve personal period/progress',()=>{
    const campaigns=require('../out/data/domains/campaign')
    const rows=['special_exchange_campaign','start_dash_exchange_campaign'].map(type=>{
        const row=operations.contentCatalog.rows.find(row=>row.type===type)
        assert.ok(row,`${type} searchable catalog`);return row
    })
    campaigns.insertPlayerStartDashExchangeCampaignsSync(playerId,[{campaignId:rows[1].id,gachaId:1,termIndex:0,status:1,
        periodStartTime:new Date('2024-01-01T00:00:00Z'),periodEndTime:new Date('2024-01-04T00:00:00Z')}])
    const saved=playerTables(),personal=campaigns.getPlayerStartDashExchangeCampaignsSync(playerId)
    for(const row of rows) {
        assert.deepEqual(operations.contentCapabilities(row),['exchange'],'only qualified final exchanges are implemented')
        assert.throws(()=>control(row.key,{...open,flags:{visible:true,exchange:true}}))
        assert.throws(()=>control(row.key,{...open,flags:{enter:true}}))
        control(row.key,{...open,flags:{exchange:true}})
    }
    assert.deepEqual(playerTables(),saved)
    const snapshots=require('../out/data/snapshots/player-snapshot'),archive=snapshots.createPlayerSaveSnapshotV2Sync(playerId,db)
    snapshots.restorePlayerSaveSnapshotV2Sync(archive,playerId,{},db)
    assert.deepEqual(campaigns.getPlayerStartDashExchangeCampaignsSync(playerId),personal)
})
