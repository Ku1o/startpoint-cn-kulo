"use strict"

const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const test = require("node:test")

const ROOT = path.join(__dirname, "..")
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "mode15-history-"))
process.env.DATA_DIR = tempRoot

const { getDb } = require(path.join(ROOT, "out", "data", "db.js"))
const mode15 = require(path.join(ROOT, "out", "lib", "mode15.js"))
const completion = require(path.join(
    ROOT,
    "out",
    "lib",
    "gauntlet-completion-classification.js",
))
const db = getDb()
db.pragma("foreign_keys = OFF")

test.after(() => {
    db.close()
    const resolvedTemp = path.resolve(tempRoot)
    assert.equal(resolvedTemp.startsWith(path.resolve(os.tmpdir()) + path.sep), true)
    fs.rmSync(resolvedTemp, { recursive: true, force: true })
})

function insertQuestProgress(section, questId, playerId = 1) {
    db.prepare(`
        INSERT INTO players_quest_progress (
            section, quest_id, finished, host_finished, unlocked,
            high_score, clear_rank, best_elapsed_time_ms,
            leader_character_id, multi_clear_count,
            s_plus_reward_received, player_id
        ) VALUES (?, ?, 1, 1, 1, NULL, 5, NULL, NULL, 0, 0, ?)
    `).run(section, questId, playerId)
}

function insertRunMarker(stage) {
    db.prepare(`
        INSERT INTO players_rush_events_played_parties (
            character_id_1, character_id_2, character_id_3,
            unison_character_id_1, unison_character_id_2, unison_character_id_3,
            equipment_id_1, equipment_id_2, equipment_id_3,
            ability_soul_id_1, ability_soul_id_2, ability_soul_id_3,
            evolution_img_level_1, evolution_img_level_2, evolution_img_level_3,
            unison_evolution_img_level_1, unison_evolution_img_level_2,
            unison_evolution_img_level_3,
            player_id, event_id, round, battle_type
        ) VALUES (
            NULL, NULL, NULL, NULL, NULL, NULL,
            NULL, NULL, NULL, NULL, NULL, NULL,
            NULL, NULL, NULL, NULL, NULL, NULL,
            1, 700098, ?, 0
        )
    `).run(700098000 + stage)
}

test("permanent clear history does not advance a fresh run", () => {
    for (let stage = 1; stage <= 15; stage += 1) {
        insertQuestProgress(24, 700098000 + stage)
    }
    insertQuestProgress(24, 700098016)

    assert.equal(mode15.getExpectedMode15StageSync(1), 1)
    assert.equal(mode15.canStartMode15QuestSync(1, 24, 700098001).allowed, true)
    assert.equal(mode15.canStartMode15QuestSync(1, 24, 700098002).allowed, false)

    insertRunMarker(1)
    assert.equal(mode15.getExpectedMode15StageSync(1), 2)
    assert.equal(mode15.canStartMode15QuestSync(1, 24, 700098002).allowed, true)
})

test("reset clears only current-run state and keeps completion history", () => {
    for (let stage = 2; stage <= 14; stage += 1) insertRunMarker(stage)
    insertQuestProgress(7, 300098001)
    insertQuestProgress(8, 300098002)

    assert.equal(mode15.getExpectedMode15StageSync(1), 15)
    mode15.resetMode15RunSync(1)

    assert.equal(mode15.getExpectedMode15StageSync(1), 1)
    assert.equal(db.prepare(`
        SELECT COUNT(*) AS count
        FROM players_rush_events_played_parties
        WHERE player_id = 1 AND event_id = 700098
    `).get().count, 0)
    assert.equal(db.prepare(`
        SELECT COUNT(*) AS count
        FROM players_quest_progress
        WHERE player_id = 1 AND section = 24
          AND quest_id BETWEEN 700098001 AND 700098016
    `).get().count, 16)
    assert.equal(db.prepare(`
        SELECT COUNT(*) AS count
        FROM players_quest_progress
        WHERE player_id = 1 AND quest_id BETWEEN 300098001 AND 300098003
    `).get().count, 0)
})

test("finite Gauntlet clears synthesize only the optional classification row", () => {
    for (let stage = 1; stage <= 15; stage += 1) {
        insertQuestProgress(24, 700098000 + stage, 2)
    }
    assert.equal(
        completion.repairGauntletCompletionClassificationSync(2, 700098),
        true,
    )
    assert.equal(db.prepare(`
        SELECT finished
        FROM players_quest_progress
        WHERE player_id = 2 AND section = 24 AND quest_id = 700098016
    `).get().finished, 1)
    assert.equal(
        completion.repairGauntletCompletionClassificationSync(2, 700098),
        false,
    )

    for (let stage = 1; stage <= 29; stage += 1) {
        insertQuestProgress(24, 700099000 + stage, 3)
    }
    assert.equal(
        completion.repairGauntletCompletionClassificationSync(3, 700099),
        false,
    )
    insertQuestProgress(24, 700099030, 3)
    assert.equal(
        completion.repairGauntletCompletionClassificationSync(3, 700099),
        true,
    )
    assert.equal(db.prepare(`
        SELECT finished
        FROM players_quest_progress
        WHERE player_id = 3 AND section = 24 AND quest_id = 700099099
    `).get().finished, 1)
    assert.equal(db.prepare(`
        SELECT COUNT(*) AS count
        FROM players_rush_events_played_parties
        WHERE player_id IN (2, 3)
    `).get().count, 0)
    assert.equal(db.prepare(`
        SELECT COUNT(*) AS count
        FROM players_rush_events
        WHERE player_id IN (2, 3)
    `).get().count, 0)
})
