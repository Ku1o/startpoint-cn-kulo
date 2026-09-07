const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

process.env.DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-rush-rounds-test-"))

const rushEventQuests = require("../assets/rush_event_quest.json")
const { getRushEventFolderMaxRounds } = require("../out/routes/api/rushEvent")
const { handleRushEventFinish } = require("../out/lib/quest/finish/rush-handler")
const { QuestCategory } = require("../out/lib/types")

const OFFICIAL_RUSH_EVENT_IDS = [
    700001, 700002, 700003, 700004, 700005, 700006, 700007,
    700011, 700012, 700013, 700014, 700015, 700016, 700017,
]

function getAssetMaxRound(eventId, folderId) {
    return Object.values(rushEventQuests)
        .filter(quest => quest.rushEventId === eventId && quest.rushEventFolderId === folderId)
        .reduce((maxRound, quest) => Math.max(maxRound, quest.rushEventRound), 0)
}

test("官方狂热激战文件夹最大回战数以关卡资产为准", () => {
    for (const eventId of OFFICIAL_RUSH_EVENT_IDS) {
        for (const folderId of [1, 2, 3]) {
            assert.equal(
                getRushEventFolderMaxRounds(eventId, folderId),
                getAssetMaxRound(eventId, folderId),
                `event=${eventId} folder=${folderId}`,
            )
        }
    }
})

test("后六期原版和复刻最高难度保留第三回战", () => {
    for (const eventId of [
        700002, 700003, 700004, 700005, 700006, 700007,
        700012, 700013, 700014, 700015, 700016, 700017,
    ]) {
        assert.equal(getRushEventFolderMaxRounds(eventId, 3), 3, `event=${eventId}`)
    }
})

test("三回战文件夹只在第三战结算通关和文件夹奖励", () => {
    const settle = round => {
        const calls = { cleared: 0, insertedParty: 0, deletedParties: 0, rewarded: 0 }
        const result = handleRushEventFinish({
            questCategory: QuestCategory.RUSH_EVENT,
            questAccomplished: true,
            questData: { rushEventId: 700002, rushEventFolderId: 3, rushEventRound: round },
            clearTime: 10_000,
            party: {
                characters: [],
                unison_characters: [],
                equipments: [],
                ability_soul_ids: [],
            },
            playerId: 1,
            questId: 700002004 + round,
            getEvoLevels: () => [],
            getFolderMaxRounds: getRushEventFolderMaxRounds,
            getRushEvent: () => null,
            updateRushEvent: () => {},
            insertParty: () => { calls.insertedParty++ },
            insertClearedFolder: () => { calls.cleared++ },
            deletePartyList: () => { calls.deletedParties++ },
            getSerializedParties: () => ({ folderParties: null, endlessParties: null }),
            getFolderRewards: () => [{ type: 0, id: 2370002, count: 1 }],
            giveRewards: () => {
                calls.rewarded++
                return { items: { 2370002: 1 } }
            },
        })
        return { calls, result }
    }

    const secondRound = settle(2)
    assert.deepEqual(secondRound.calls, {
        cleared: 0,
        insertedParty: 1,
        deletedParties: 0,
        rewarded: 0,
    })
    assert.deepEqual(secondRound.result.rushEventData.rush_battle_reward_list, [])

    const thirdRound = settle(3)
    assert.deepEqual(thirdRound.calls, {
        cleared: 1,
        insertedParty: 0,
        deletedParties: 1,
        rewarded: 1,
    })
    assert.deepEqual(thirdRound.result.rushEventData.rush_battle_reward_list, [
        { kind: 1, kind_id: 2370002, number: 1 },
    ])
})
