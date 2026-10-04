const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'active-quest-conditional-delete-'))
process.env.DATA_DIR = dataDir

const { getDb } = require('../out/data/db')
const account = require('../out/data/domains/account')
const player = require('../out/data/domains/player')
const active = require('../out/data/domains/quest_active')

test('conditional active-quest cleanup cannot delete a newer play id', () => {
    const owner = account.insertAccountSync({
        appId: 'wf_cn',
        idpAlias: '',
        idpCode: 'test',
        idpId: 'conditional-active-delete',
        status: 'normal',
    })
    const selected = player.insertDefaultPlayerSync(owner.id)
    active.insertPlayerActiveQuestSync(selected.id, {
        playerId: selected.id,
        playId: 'new-play',
        questId: 1000101,
        category: 2,
        useBossBoostPoint: false,
        useBoostPoint: false,
        isAutoStartMode: false,
        isMulti: true,
        isMultiHost: true,
        roomNumber: '123456',
        continueCount: 0,
        startedAtMs: Date.now(),
    })

    assert.equal(
        active.deletePlayerActiveQuestIfPlayIdSync(selected.id, 'old-play'),
        false,
    )
    assert.equal(active.getPlayerActiveQuestSync(selected.id).playId, 'new-play')
    assert.equal(
        active.deletePlayerActiveQuestIfPlayIdSync(selected.id, 'new-play'),
        true,
    )
    assert.equal(active.getPlayerActiveQuestSync(selected.id), null)
})

test.after(() => {
    const db = getDb()
    if (db.open) db.close()
    fs.rmSync(dataDir, { recursive: true, force: true })
})
