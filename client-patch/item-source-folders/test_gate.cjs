// Execute the actual helper's Boolean/control-flow body with AS type annotations
// removed. SWF compilation, AVM2 stack checks and independent FFDec readback are
// separate build gates; this does not pretend to be a device or AVM2 execution.
const {readFileSync} = require('node:fs');
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const source = readFileSync(__dirname + '/src/cn/ui/ItemSourceFolderGate.as', 'utf8');
const body = source.slice(source.indexOf('            if (listed)'), source.lastIndexOf('        }'))
    .replace(/var (\w+):Object/g, 'let $1').replace(/\bint\(/g, 'Math.trunc(');
const allow = vm.runInNewContext('(function(listed, repository, eventId, now){' + body + '})');
function repository({member=true, unlocked=true, start=100, end=null}={}) {
    const id = {kind:'hardMulti',id:1001};
    return {id, getFolderIdFromEventId(event) {assert.equal(event,id);return member?{index:0,params:[1]}:{index:1};},
        getEventFolder(folder) {assert.equal(folder,1);return {isUnlocked:()=>unlocked};},
        getEvent(event) {assert.equal(event,id);return {isWithinPeriod:now=>now>=start && (end===null || now<end)};}};
}
test('ordinary/side-story success is preserved without consulting folder data',()=>{
    assert.equal(allow(true,null,null,0),true);
});
test('permanent folder source survives the former empty ordinary-event list',()=>{
    const r=repository();assert.equal(allow(false,r,r.id,200),true);
});
test('unregistered and locked events cannot bypass the native acquisition gate',()=>{
    for(const config of [{member:false},{unlocked:false}]) {
        const r=repository(config);assert.equal(allow(false,r,r.id,200),false);
    }
});
test('folder event start and expiry remain enforced',()=>{
    const r=repository({end:300});
    assert.equal(allow(false,r,r.id,99),false);
    assert.equal(allow(false,r,r.id,100),true);
    assert.equal(allow(false,r,r.id,299),true);
    assert.equal(allow(false,r,r.id,300),false);
});
