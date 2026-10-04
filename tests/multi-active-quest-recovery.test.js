const test = require('node:test')
const assert = require('node:assert/strict')
const { classifyMultiActiveQuestRecovery } = require('../out/lib/multi-active-quest-recovery')

function quest(overrides = {}) {
    return {
        isMulti: true,
        roomNumber: '123456',
        category: 2,
        questId: 1001,
        ...overrides,
    }
}

function room(overrides = {}) {
    return {
        room_number: '123456',
        category: 2,
        quest_id: 1001,
        expected_real_viewer_ids: [901],
        lifecycle: { phase: 'BATTLE' },
        ...overrides,
    }
}

test('only an exact live multiplayer battle is published for login recovery', () => {
    assert.deepEqual(
        classifyMultiActiveQuestRecovery(quest(), room(), 901),
        { recoverable: true, reason: 'recoverable' },
    )
    assert.deepEqual(
        classifyMultiActiveQuestRecovery(quest({ isMulti: false }), undefined, 901),
        { recoverable: true, reason: 'single' },
    )
    assert.equal(
        classifyMultiActiveQuestRecovery(quest({ roomNumber: null }), undefined, 901).reason,
        'missing_room_number',
    )
    assert.equal(
        classifyMultiActiveQuestRecovery(quest(), undefined, 901).reason,
        'room_missing',
    )
    assert.equal(
        classifyMultiActiveQuestRecovery(quest(), room({
            lifecycle: { phase: 'RETURNING' },
        }), 901).reason,
        'room_not_in_battle',
    )
    assert.equal(
        classifyMultiActiveQuestRecovery(quest(), room({ quest_id: 1002 }), 901).reason,
        'quest_mismatch',
    )
    assert.equal(
        classifyMultiActiveQuestRecovery(quest(), room(), 902).reason,
        'member_not_in_battle',
    )
    assert.equal(
        classifyMultiActiveQuestRecovery(quest(), room(), 901, true).reason,
        'member_not_in_battle',
    )
    assert.equal(
        classifyMultiActiveQuestRecovery(quest(), room({
            expected_real_viewer_ids: [],
            member_viewer_ids: [901],
        }), 901).recoverable,
        true,
    )
})

test('viewer identity is used instead of account or player identity', () => {
    const value = room({ expected_real_viewer_ids: [700000123] })
    assert.equal(
        classifyMultiActiveQuestRecovery(quest(), value, 700000123).recoverable,
        true,
    )
    assert.equal(
        classifyMultiActiveQuestRecovery(quest(), value, 42).recoverable,
        false,
    )
})
