// Run the actual AS formatter after erasing its scalar type annotations.
// AVM2 compilation/readback is checked separately by the APK builder.
const fs=require('node:fs'),vm=require('node:vm');
const {test}=require('node:test'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/../abyss-records/src/cn/ui/AbyssRecordDetails.as','utf8');
let code=source.slice(source.indexOf('        public static function formatTime'),source.indexOf('        public static function open('))
    .replace(/public static function/g,'function')
    .replace(/\b(var \w+|\w+):(?:String|Number|Object|int)\b/g,'$1')
    .replace(/\):String/g,')');
const {responseText}=vm.runInNewContext(code+';({responseText})');
const good={status:'ok',quest_id:700099001,revision:'a'.repeat(64),best_time_ms:83456,holder_name:'星海旅人'};
test('record time plus current player nickname',()=>{
    assert.equal(responseText(good,good.quest_id),'01:23.456<br/>纪录保持者：星海旅人');
});
test('nickname markup and newlines render as text',()=>{
    const result=responseText({...good,holder_name:'<b>A&B</b>\n"\''},good.quest_id);
    assert.equal(result,'01:23.456<br/>纪录保持者：&lt;b&gt;A&amp;B&lt;/b&gt; &quot;&#39;');
});
test('missing/removed holder and old server do not hide a valid time',()=>{
    for(const holder_name of [null,undefined,'  ',42])
        assert.equal(responseText({...good,holder_name},good.quest_id),'01:23.456<br/>纪录保持者：未知玩家');
});
test('no record, stale resources and invalid response preserve fallback messages',()=>{
    assert.equal(responseText({...good,best_time_ms:null},good.quest_id),'本期暂无通关纪录');
    assert.equal(responseText({...good,status:'update_required'},good.quest_id),'请更新资源后查看');
    for(const data of [null,{...good,best_time_ms:0},{...good,best_time_ms:'5'}, {...good,revision:'bad'}, {...good,quest_id:700099002}])
        assert.equal(responseText(data,good.quest_id),'暂时无法获取');
});
