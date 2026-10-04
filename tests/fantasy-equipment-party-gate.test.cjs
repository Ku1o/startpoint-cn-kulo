const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { spawnSync } = require('node:child_process')

const root = path.resolve(__dirname, '..')
const patcher = path.join(root, 'client-patch/fantasy-equipment-party-gate/patch.py')
const contract = JSON.parse(fs.readFileSync(
    path.join(root, 'client-patch/fantasy-equipment-party-gate/contract.json'),
    'utf8',
))

function python(script) {
    const result = spawnSync('python3', ['-c', script], {
        cwd: root,
        encoding: 'utf8',
        env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
    })
    assert.equal(result.status, 0, result.stderr)
    return JSON.parse(result.stdout)
}

test('client gate contract covers all Fantasy quests and only exclusive item ids', () => {
    const result = python(`
import importlib.util, json
spec=importlib.util.spec_from_file_location("gate", ${JSON.stringify(patcher)})
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
out={}
out["solo_first"]=m.is_party_allowed(0,17,700098001,[100013,None,None],[None,None,None])
out["solo_last"]=m.is_party_allowed(0,17,700098016,[None,None,None],[100023,None,None])
out["multi_first"]=m.is_party_allowed(1,1,300098001,[100013,None,None],[None,None,None])
out["multi_last"]=m.is_party_allowed(1,1,300098003,[None,None,None],[100023,None,None])
out["solo_before"]=m.is_party_allowed(0,17,700098000,[100013,None,None],[None,None,None])
out["solo_after"]=m.is_party_allowed(0,17,700098017,[None,None,None],[100013,None,None])
out["multi_before"]=m.is_party_allowed(1,1,300098000,[100013,None,None],[None,None,None])
out["multi_after"]=m.is_party_allowed(1,1,300098004,[None,None,None],[100013,None,None])
out["normal_low"]=m.is_party_allowed(0,0,1001,[100012,None,None],[None,None,None])
out["normal_high"]=m.is_party_allowed(0,0,1001,[None,None,None],[100024,None,None])
out["normal_weapon"]=m.is_party_allowed(0,0,1001,[None,100013,None],[None,None,None])
out["normal_soul"]=m.is_party_allowed(1,0,1001,[None,None,None],[None,None,100023])
out["official_denial"]=m.is_party_allowed(0,17,700098001,[None,None,None],[None,None,None],False)
print(json.dumps(out))
`)
    assert.deepEqual(result, {
        solo_first: true,
        solo_last: true,
        multi_first: true,
        multi_last: true,
        solo_before: false,
        solo_after: false,
        multi_before: false,
        multi_after: false,
        normal_low: true,
        normal_high: true,
        normal_weapon: false,
        normal_soul: false,
        official_denial: false,
    })
    assert.equal(contract.exclusive_item_id_min, 100013)
    assert.equal(contract.exclusive_item_id_max, 100023)
    const mode15 = require('../out/lib/mode15')
    assert.deepEqual(
        mode15.MODE15_EXCLUSIVE_EQUIPMENT_IDS,
        Array.from(
            { length: contract.exclusive_item_id_max - contract.exclusive_item_id_min + 1 },
            (_, index) => contract.exclusive_item_id_min + index,
        ),
    )
})

test('source patch is idempotent and fails closed when the target shape drifts', () => {
    const result = python(`
import importlib.util, json
spec=importlib.util.spec_from_file_location("gate", ${JSON.stringify(patcher)})
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
source='''package test
{
   public class BattleStartableLogic
   {
      public var questId:QuestIdGroupKind;
      public function isPartyStartable(param1:PartyPeek) : Boolean
      {
         var _loc5_:* = null as QuestPartyStartableCondition;
         var _loc2_:Array = partyConditions;
         var _loc3_:Boolean = true;
         var _loc4_:int = 0;
         while(_loc4_ < int(_loc2_.length))
         {
            _loc5_ = _loc2_[_loc4_];
            _loc4_++;
            if(!_loc5_.satisfied(param1))
            {
               _loc3_ = false;
               break;
            }
         }
         return _loc3_;
      }
      public function isItemStartable(param1:Object) : Boolean
      {
         return true;
      }
   }
}
'''
patched=m.patch_text(source)
again=m.patch_text(patched)
verified=m.validate(patched)
markerless=m.validate(patched.replace('// '+m.BEGIN_MARKER+'\\n','').replace('// '+m.END_MARKER+'\\n',''),False)
drift=False
try:m.patch_text(source.replace('return _loc3_;','return true;'))
except m.PatchError:drift=True
print(json.dumps({"idempotent":patched==again,"drift":drift,"verified":verified,"markerless":markerless}))
`)
    assert.equal(result.idempotent, true)
    assert.equal(result.drift, true)
    assert.equal(result.verified.status, 'verified')
    assert.equal(result.verified.equipment_slots_checked, 3)
    assert.equal(result.verified.ability_soul_slots_checked, 3)
    assert.equal(result.verified.official_conditions_preserved, true)
    assert.equal(result.markerless.status, 'verified')
})

test('server equipment scope matches the client contract including practice', () => {
    const mode15 = require('../out/lib/mode15')
    const optional = require('../out/lib/mode15-optional')
    const checks = [
        [24, 700098001, true],
        [24, 700098015, true],
        [24, 700098016, true],
        [7, 300098001, true],
        [8, 300098003, true],
        [24, 700098000, false],
        [24, 700098017, false],
        [7, 300098000, false],
        [7, 300098004, false],
        [1, 1000101, false],
    ]
    for (const [category, questId, expected] of checks) {
        assert.equal(
            mode15.isMode15EquipmentAllowedQuest(category, questId),
            expected,
            `runtime category=${category} quest=${questId}`,
        )
        assert.equal(
            optional.isMode15EquipmentAllowedQuest(category, questId),
            expected,
            `optional category=${category} quest=${questId}`,
        )
    }
})
