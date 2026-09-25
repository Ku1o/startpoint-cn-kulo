const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'degree-history-'))
process.env.DATA_DIR = directory
const { getDb } = require('../out/data/db')
const db = getDb()
const quests = require('../out/data/domains/quest')
const { insertAccountSync } = require('../out/data/domains/account')
const { insertDefaultPlayerSync } = require('../out/data/domains/player')
const { DegreeComputer } = require('../out/lib/mission/computer-degree')
const { getMissionMasterDefinitions } = require('../out/lib/mission/master-data')
const { runMeasuredSingleTransaction } = require('../out/lib/sqlite-write-coordinator')
const p = insertDefaultPlayerSync(insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'history',idpId:'history',status:'normal'}).id)
const when = new Date('2025-07-23T12:00:00Z')

function fullHistory() {
    return Object.entries(quests.getPlayerQuestProgressSync(p.id)).flatMap(([section, rows]) =>
        rows.map(row => ({...row, section:Number(section)})))
}
function compareSummary() {
    const rows = fullHistory().filter(row => ![2,8,19,26].includes(row.section))
    const times = rows.filter(row => row.finished).map(row => Number(row.bestElapsedTimeMs))
        .filter(value => Number.isFinite(value) && value > 0)
    assert.deepEqual(quests.getPlayerSingleQuestHistorySummarySync(p.id), {
        bestElapsedTimeMs:times.length ? Math.min(...times) : null,
        highScore:Math.max(0,...rows.map(row => Number(row.highScore) || 0)),
        ssCount:rows.filter(row => row.finished && row.clearRank === 5).length,
    })
}
test.after(() => {
    db.close()
    assert.equal(path.dirname(fs.realpathSync(directory)), fs.realpathSync(os.tmpdir()))
    fs.rmSync(directory, {recursive:true})
})

test('historical summaries retain empty, unfinished-score, mode, invalid-time and rollback behavior', () => {
    compareSummary()
    for (const [index, section] of [1,2,4,8,15,19,26,27].entries()) {
        for (let n=0;n<5;n++) quests.insertPlayerQuestProgressSync(p.id, section, {
            questId:9000000+index*10+n, finished:n!==4, highScore:1000+index*100+n,
            clearRank:n%2 ? 5 : 4, bestElapsedTimeMs:[null,0,-1,500,200][n],
        })
    }
    compareSummary()
    const before = quests.getPlayerSingleQuestHistorySummarySync(p.id)
    assert.throws(() => runMeasuredSingleTransaction(db, () => {
        quests.insertPlayerQuestProgressSync(p.id, 1, {questId:9900001,finished:true,clearRank:5,highScore:999999,bestElapsedTimeMs:10})
        compareSummary()
        assert.notDeepEqual(quests.getPlayerSingleQuestHistorySummarySync(p.id), before)
        throw Error('rollback')
    }), /rollback/)
    assert.deepEqual(quests.getPlayerSingleQuestHistorySummarySync(p.id), before)
})

test('every quest-based degree condition agrees with a full-history evaluation, including exact and EX scopes', () => {
    db.transaction(() => {
        for (const [section, file] of [[1,'main_quest'],[4,'ex_quest'],[2,'boss_battle_quest']]) {
            for (const id of Object.keys(require(`../assets/${file}.json`)).map(Number)) {
                if (!quests.getPlayerSingleQuestProgressSync(p.id, section, id)) quests.insertPlayerQuestProgressSync(p.id, section, {
                    questId:id, finished:true,clearRank:5,highScore:id,bestElapsedTimeMs:3500,
                })
            }
        }
    })()
    const definitions = getMissionMasterDefinitions(5).filter(d => [14,15,16,22,23,25,26].includes(Number(d.row[3])))
    const full = fullHistory()
    const oracle = {
        ...DegreeComputer.buildContext(p.id, 5, when), singleQuestHistory:undefined,
        flatQuestProgress:full, questProgressBySection:new Map(), questProgressByQuestId:new Map(),
        finishedQuestKeys:new Set(full.filter(row => row.finished).map(row => `${row.section}:${row.questId}`)),
        questMetricCache:new Map(),
    }
    for (const row of full) {
        for (const [map,key] of [[oracle.questProgressBySection,row.section],[oracle.questProgressByQuestId,row.questId]]) {
            if (!map.has(key)) map.set(key,[])
            map.get(key).push(row)
        }
    }
    let summaryOnly = 0, narrowed = 0
    for (const d of definitions) {
        const scoped = DegreeComputer.buildContext(p.id, 5, when, [d.missionId])
        for (const persisted of [0,37]) assert.equal(
            DegreeComputer.compute(d.missionId, scoped, persisted),
            DegreeComputer.compute(d.missionId, oracle, persisted), `mission ${d.missionId}`)
        if (scoped.singleQuestHistory && scoped.flatQuestProgress.length === 0) summaryOnly++
        if (scoped.flatQuestProgress.length > 0 && scoped.flatQuestProgress.length < full.length) narrowed++
    }
    assert.ok(definitions.length > 20)
    assert.ok(summaryOnly > 0)
    assert.ok(narrowed > 0)
})
