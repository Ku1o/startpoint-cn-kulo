'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const shop=require('../assets/event_item_shop.json')['0']['300097'];
const map=require('../assets/event_item_shop_id_map.json');
// Independent release specification: reward kind/id/count, price, lifetime pack limit.
const expected=[
 [3,149985,1,5000,1],
 [1,null,5000,200,100],[1,null,10000,400,50],[1,null,15000,600,30],
 [2,null,20000,100,300],[2,null,100000,200,50],[2,null,300000,400,30],
 [0,11001,1,100,20],[0,11002,1,200,20],[0,10001,1,300,5],[0,10002,1,500,5],
 [0,47,5,25,500],[0,43,5,25,500],[0,48,5,22,500],[0,44,5,22,500],
 [0,49,3,24,100],[0,45,3,24,100],[0,49,1,8,200],[0,45,1,8,200],
 [0,49,5,40,100],[0,45,5,40,100],
 [0,65,5,8,200],[0,62,5,8,200],[0,66,4,13,250],[0,63,4,13,250],[0,67,2,75,500],[0,64,2,75,500],
 [0,2370101,1,200,20],[0,10000145,1,500,100],[0,2370100,1,600,5],[0,999023,1,400,9999],
];
const sort=x=>JSON.stringify(x);
test('all 31 independent Halloween SKU rewards, quantities, prices and lifetime limits match the release specification',()=>{
 assert.equal(Object.keys(shop).length,31);
 const actual=Object.entries(shop).map(([id,s])=>{assert.deepEqual(map[id],{eventType:0,eventId:300097});assert.equal(s.rewards.length,1);assert.equal(s.costs.length,1);assert.equal(s.costs[0].id,10009701);assert.equal(s.dailyStock,undefined);assert.equal(s.monthlyStock,undefined);const r=s.rewards[0];return[r.type,r.id??null,r.count,s.costs[0].amount,s.stock]});
 assert.deepEqual(actual.sort((a,b)=>sort(a).localeCompare(sort(b))),expected.sort((a,b)=>sort(a).localeCompare(sort(b))));
 for(const id of[9730002,9730003,9730004,9730005,9730006,9730009,9730012]){assert.equal(shop[id],undefined);assert.equal(map[id],undefined);}
});
test('existing IDs retain their meaning while the three sizes of each advanced element have separate product IDs',()=>{
 for(const[id,type,reward,count]of[[9730001,3,149985,1],[9730010,2,undefined,20000],[9730011,1,undefined,5000],[9730007,0,49,1],[9730008,0,45,1]])assert.deepEqual(shop[id].rewards,[{type,...(reward?{id:reward}:{}),count}]);
 for(const id of[49,45])assert.equal(Object.values(shop).filter(s=>s.rewards[0].id===id).length,3);
});
test('three purchased nameplates retain all 24 definitions and have no alternate new shop rows',()=>{
 const all=require('../assets/event_item_shop.json'),defs=require('../assets/degree_exclusive.json');
 for(let id=9911401;id<=9911424;id++)assert.ok(defs[id]);
 for(const[id,degree,price]of[[9700130,9911401,44044],[9700131,9911403,33333],[9700132,9911404,6666666]]){const s=all['11']['700099'][id];assert.deepEqual(s.rewards,[{count:1,id:degree,type:5}]);assert.deepEqual(s.costs,[]);assert.deepEqual(s.userCost,{amount:price,type:0});assert.equal(s.stock,1);assert.deepEqual(map[id],{eventType:11,eventId:700099});}
});
test('dedicated ticket ID is registered once, unsellable and never present as a wildcard payment',()=>{
 for(const id of[999023,10009701])assert.equal(require('../assets/item_ids.json').filter(x=>x===id).length,1);
 assert.equal(require('../assets/item_lookup_cnmod.json')['999023'],'万圣惊奇扭蛋券');
 assert.deepEqual(require('../assets/item_sale.json')['999023'],{category:4,sellable:false,sale_price:100});
 const g=require('../assets/gacha_halloween_2026.json')['990005'];assert.equal(g.tenTicketItemId,999023);assert.equal(g.onceTicketItemId,undefined);assert.equal(g.wildcardTicketAvailable,false);assert.equal(g.pageKind,4);assert.equal(g.enforceAvailabilityWindow,true);assert.equal(g.uncontrolledExchangeAllowed,false);
 assert.ok(require('../assets/cdndata/gacha.json')['990005']);assert.deepEqual(Object.keys(require('../assets/cdndata/gacha_feature_content.json')['990005']),['1','2','3','4','5','6','7','8','9']);
});
test('the 25 special bosses leave only the two designated pools, preserving the abyss beast',()=>{
 const removed=new Set([119950,119951,119970,129950,129951,129970,139950,139951,139970,149950,149951,149970,159950,159951,159970,169950,169951,169970,179970,179981,179982,179983,179984,179985,179986]);assert.equal(removed.size,25);
 for(const g of[require('../assets/gacha_cnmod.json')['990001'],require('../assets/gacha_rank_p5b.json')['990002']]){const entries=Object.values(g.pool).flat();assert.equal(entries.some(x=>removed.has(x.id)),false);assert.ok(entries.some(x=>x.id===169980));}
 const defs=require('../assets/character_rank_p5b.json');for(const id of removed)assert.ok(defs[id]);
});
