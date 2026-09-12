const test = require('node:test');
const assert = require('node:assert/strict');
const {buildBannerFromRow} = require('../tools/rebuild_gacha_from_odds.cjs');

function entry(id, exchange, weight=1) {
    return {characterId:id,rarity:5,weight,oddsUp:exchange,isLimited:false,isExchangeable:exchange,trialReadingForced:false};
}
function fixture(prefix='black_element_pickup_05') {
    const row=Array(47).fill('');
    row[0]=prefix;row[1]='fixture';row[10]='4';row[11]='normal_rarity';row[13]='0';
    row[14]=`${prefix}_character_3`;row[15]=`${prefix}_character_4`;row[16]=`${prefix}_character_5`;
    row[29]='2025-01-01 00:00:00';row[30]='2199-12-31 23:59:59';
    const intended=Array.from({length:10},(_,i)=>entry(161001+i,true));
    const character={older_unrelated:{entries:intended.map(x=>({...x,weight:900,isExchangeable:false,oddsUp:false}))}};
    character[row[14]]={entries:[]};character[row[15]]={entries:[]};character[row[16]]={entries:intended};
    return {row,odds:{rarity:{normal_rarity:{entries:[{rarity:5,weight:50},{rarity:4,weight:250},{rarity:3,weight:700}]}},character,equipment:{}}};
}

test('属性池使用本池的权重、UP 和兑换标记，不继承另一池先出现的角色记录',()=>{
    const {row,odds}=fixture();
    const result=buildBannerFromRow('219',row,odds,[]);
    assert.equal(result.pool['1'].length,10);
    for(const x of result.pool['1']) {
        assert.equal(x.odds,1);assert.equal(x.isExchangeable,true);assert.equal(x.isRateUp,true);
    }
});

test('缺少节日池 odds 时失败，不用角色模板猜测抽取名单',()=>{
    const {row,odds}=fixture('holiday_character_2025_01');
    delete odds.character[row[16]];
    assert.throws(()=>buildBannerFromRow('1675',row,odds,[{code_number:'161001',rarity:5,source:'常驻卡池'}]),/missing effective odds/);
});

test('升星后的角色仍可保留原 ID，生成器遵循表中星级与兑换属性',()=>{
    const {row,odds}=fixture();
    odds.character[row[16]].entries.push(entry(261089,true));
    const result=buildBannerFromRow('219',row,odds,[]);
    const dragon=result.pool['1'].find(x=>x.id===261089);
    assert.equal(dragon.rank,5);assert.equal(dragon.isExchangeable,true);
    assert.ok(!result.pool['2'].some(x=>x.id===261089));
});
