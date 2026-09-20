const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
process.env.DATA_DIR=fs.mkdtempSync(path.join(os.tmpdir(),'fantasy-abyss-shop-'));
const assets=require('../out/lib/assets');
const {getDb}=require('../out/data/db');
const {getShopPurchaseKey}=require('../out/lib/shop-sales');
const {givePlayerItemSync,getPlayerItemSync}=require('../out/data/domains/item');
const db=getDb();test.after(()=>db.close());
test('Fantasy material purchases, shared limits and acquisition routes use the winning catalog',async()=>{
 const account=require('../out/data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'leiting',idpId:'',status:'normal'});
 const player=require('../out/data/domains/player').insertDefaultPlayerSync(account.id);
 require('../out/data/activeAccount').saveAccountDefaultPlayer(account.id,player.id);
 const viewer=88001998;
 await require('../out/data/domains/session').insertSessionWithToken({token:String(viewer),accountId:account.id,expires:new Date(Date.now()+86400000),type:2});
 const app=require('fastify')({logger:false});
 app.addHook('onSend',(_req,reply,payload,done)=>done(null,String(reply.getHeader('content-type')||'').startsWith('application/x-msgpack')&&typeof payload==='object'?JSON.stringify(payload):payload));
 await app.register(require('../out/routes/api/shop').default,{prefix:'/shop'});
 await app.register(require('../out/routes/api/howToGet').default,{prefix:'/how_to_get'});
 const post=async(url,data,status=200)=>{const r=await app.inject({method:'POST',url,payload:{viewer_id:viewer,api_count:1,...data}});assert.equal(r.statusCode,status,r.payload);return r.json();};
 const list=async()=> (await post('/shop/get_sales_list',{shop_types:[],boss_coin_shop_category_ids:[],event_list:[{event_type:11,event_ids:[700098]},{event_type:0,event_ids:[300098]}]})).data.sales_list;
 const count=i=>getPlayerItemSync(player.id,i)||0;
 try {
  for(const [index,item,price] of [[13,2370101,100],[14,2370100,500]]){
   const productIds=[9700200+index,9700300+index];
   for(const id of productIds){
    const product=assets.getShopItemSync(4,id);assert.equal(product.stock,999);
    assert.deepEqual(product.costs,[{id:2370098,amount:price}]);assert.deepEqual(product.rewards,[{type:0,id:item,count:1}]);
    assert.equal(getShopPurchaseKey(4,id),-9702000-index);
    const how=(await post('/how_to_get/get_list',{item_id:item})).data.shop_sales_list;
    assert.equal(how.find(x=>x.shop_item_id===id).stock_quantity,999);
   }
   const initial=count(item),coins=count(2370098);
   // Zero balance fails without awarding stock or items.
   await post('/shop/buy',{shop_type:4,shop_item_id:productIds[0],number:1},400);
   assert.equal(count(item),initial);assert.equal(count(2370098),coins);
   givePlayerItemSync(player.id,2370098,price*999);
   await post('/shop/buy',{shop_type:4,shop_item_id:productIds[0],number:1});
   assert.equal(count(item),initial+1);assert.equal(count(2370098),price*998);
   let sales=await list();productIds.forEach(id=>assert.equal(sales.find(x=>x.shop_item_id===id).stock_quantity,998));
   await post('/shop/buy',{shop_type:4,shop_item_id:productIds[1],number:998});
   assert.equal(count(item),initial+999);assert.equal(count(2370098),0);
   const how=(await post('/how_to_get/get_list',{item_id:item})).data.shop_sales_list;
   productIds.forEach(id=>assert.equal(how.find(x=>x.shop_item_id===id).stock_quantity,0));
   givePlayerItemSync(player.id,2370098,price);
   await post('/shop/buy',{shop_type:4,shop_item_id:productIds[0],number:1},400);
   assert.equal(count(item),initial+999);assert.equal(count(2370098),price);
   require('../out/data/domains/item').givePlayerItemSync(player.id,2370098,-price);
  }
  // The prior twelve persisted shared keys stay exactly the same.
  for(let i=0;i<12;i++)for(const id of [9700201+i,9700301+i])assert.equal(getShopPurchaseKey(4,id),-9702001-i);
 }finally{await app.close();}
});
