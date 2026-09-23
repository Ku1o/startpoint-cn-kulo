const test = require('node:test')
const assert = require('node:assert/strict')

const { PartyCategory } = require('../out/data/types')
const { partyCategoryForRushEvent } = require('../out/lib/rush-party-categories')
const { isPartyCategory, mergePartyGroupsForCategory } = require('../out/lib/special-event-parties')

test('Rush events resolve to independent persisted party categories', () => {
  assert.equal(partyCategoryForRushEvent(700099), PartyCategory.ABYSS_NORMAL)
  assert.equal(partyCategoryForRushEvent(700100), PartyCategory.ABYSS_EX)
  assert.equal(partyCategoryForRushEvent(700098), PartyCategory.FANTASY)
  assert.equal(partyCategoryForRushEvent(undefined), PartyCategory.RUSH)
  assert.equal(isPartyCategory(PartyCategory.FANTASY), true)
  assert.equal(isPartyCategory(8), false)
})

test('independent category copies legacy Rush groups without sharing writes', () => {
  const legacy = {
    '1': {
      category: PartyCategory.RUSH,
      colorId: 2,
      list: {
        '1': {
          category: PartyCategory.RUSH,
          name: 'legacy',
          characterIds: [101, null, null],
          unisonCharacterIds: [null, null, null],
          equipmentIds: [null, null, null],
          abilitySoulIds: [null, null, null],
          options: { allowOtherPlayersToHealMe: false },
          edited: false,
        },
      },
    },
  }
  const copied = mergePartyGroupsForCategory({}, legacy, {}, PartyCategory.ABYSS_EX)
  assert.equal(copied['1'].category, PartyCategory.ABYSS_EX)
  assert.equal(copied['1'].list['1'].category, PartyCategory.ABYSS_EX)
  copied['1'].list['1'].characterIds[0] = 202
  assert.equal(legacy['1'].list['1'].characterIds[0], 101)
})
