'use strict'
const fs=require('node:fs'),path=require('node:path')
const root=path.resolve(__dirname,'..'),assets=require('../out/lib/assets'),master=require('../out/lib/content-master')
const output=process.argv[2]
if(!output)throw Error('explicit output path required')
const types={general_shop:8,star_grain_shop:9,treasure_shop:1,boss_coin_shop:7,event_item_shop:4}
const result={schemaVersion:1,items:{},eventMap:master.serverEventShopIdMap}
for(const row of require('../assets/content_catalog.json').rows)if(Object.hasOwn(types,row.type))
 result.items[row.key]={shopType:types[row.type],item:assets.getShopItemSync(types[row.type],row.id)}
fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n')
console.log(JSON.stringify({items:Object.keys(result.items).length}))
