const assert = require("node:assert/strict")
const Database = require("better-sqlite3")
const Fastify = require("fastify")
const { pack, unpack } = require("msgpackr")

require("ts-node/register/transpile-only")

function stubModule(relativePath, exports) {
    const modulePath = require.resolve(relativePath)
    require.cache[modulePath] = {
        id: modulePath,
        filename: modulePath,
        loaded: true,
        exports,
    }
}

const db = new Database(":memory:")
db.exec(`
    CREATE TABLE players_active_mission_counters (
        player_id INTEGER PRIMARY KEY,
        total_used_mana_count INTEGER NOT NULL DEFAULT 0,
        total_gacha_character_count INTEGER NOT NULL DEFAULT 0,
        total_equipment_equip_count INTEGER NOT NULL DEFAULT 0,
        total_unison_set_count INTEGER NOT NULL DEFAULT 0,
        total_party_character_set_count INTEGER NOT NULL DEFAULT 0,
        total_injected_exp_count INTEGER NOT NULL DEFAULT 0,
        total_gacha_campaign_count INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE player_state (
        id INTEGER PRIMARY KEY,
        exp_pool INTEGER NOT NULL,
        exp_pooled_time TEXT NOT NULL
    );
    CREATE TABLE character_state (
        player_id INTEGER NOT NULL,
        character_id INTEGER NOT NULL,
        exp INTEGER NOT NULL,
        PRIMARY KEY (player_id, character_id)
    );
    INSERT INTO player_state VALUES (7, 2000, '2026-01-01T00:00:00.000Z');
    INSERT INTO character_state VALUES (7, 100001, 0);
`)

let failExpWrite = false
let pendingPooledExp = 0
stubModule("../src/data/db", { getDb: () => db })
stubModule("../src/data/domains/account", { getAccountPlayers: () => [] })
stubModule("../src/data/domains/session", {
    getSession: async viewerId => viewerId === "123" ? { accountId: 9 } : null,
})
stubModule("../src/data/activeAccount", { resolvePlayerIdSync: () => 7 })
stubModule("../src/data/domains/player", {
    getPlayerSync(playerId) {
        const row = db.prepare("SELECT * FROM player_state WHERE id = ?").get(playerId)
        return row === undefined ? null : {
            id: row.id,
            expPool: row.exp_pool,
            expPooledTime: new Date(row.exp_pooled_time),
        }
    },
    collectPlayerDataPooledExpSync(player, dateNow) {
        if (pendingPooledExp <= 0) return
        db.prepare("UPDATE player_state SET exp_pool = exp_pool + ?, exp_pooled_time = ? WHERE id = ?")
            .run(pendingPooledExp, dateNow.toISOString(), player.id)
        pendingPooledExp = 0
    },
    adjustPlayerExpPoolSync(playerId, delta) {
        const updated = db.prepare(`
            UPDATE player_state
            SET exp_pool = exp_pool + ?
            WHERE id = ? AND exp_pool + ? >= 0
            RETURNING exp_pool
        `).get(delta, playerId, delta)
        return updated?.exp_pool ?? null
    },
})
stubModule("../src/data/domains/character", {
    getPlayerCharacterSync(playerId, characterId) {
        const row = db.prepare(
            "SELECT * FROM character_state WHERE player_id = ? AND character_id = ?",
        ).get(playerId, characterId)
        return row === undefined ? null : { id: row.character_id, exp: row.exp }
    },
    getPlayerCharactersSync: () => ({}),
    updatePlayerCharacterSync() {},
})
stubModule("../src/data/domains/item", {
    getPlayerItemsSync: () => ({}),
    givePlayerItemSync: () => 0,
})
stubModule("../src/routes/api/character", { characterMaxOverLimits: () => 0 })
stubModule("../src/lib/assets", { getCharacterDataSync: () => null })
stubModule("../src/data/utils", { clientSerializeDate: value => value })
stubModule("../src/lib/character-stack", { validateCharacterStackConversion: () => null })
stubModule("../src/lib/mission", { settleDegreeMissionResponse() {} })
stubModule("../src/utils", {
    generateDataHeaders: values => ({ viewer_id: values.viewer_id, result_code: values.result_code ?? 1 }),
    getServerDate: () => new Date("2026-01-01T00:10:00.000Z"),
    getServerTime: value => Math.floor(value.getTime() / 1000),
})
stubModule("../src/lib/character", {
    givePlayerCharactersExpSync(playerId, characterIds, amount) {
        const characterId = characterIds[0]
        db.prepare("UPDATE character_state SET exp = exp + ? WHERE player_id = ? AND character_id = ?")
            .run(amount, playerId, characterId)
        if (failExpWrite) throw new Error("injected character exp failure")
        const expPool = db.prepare("SELECT exp_pool FROM player_state WHERE id = ?").get(playerId).exp_pool
        return {
            add_exp_list: [{ character_id: characterId, add_exp: amount }],
            character_list: [],
            exp_pool: expPool,
        }
    },
})

const counterDomain = require("../src/data/domains/active_mission_counters")
const expodRoutes = require("../src/routes/api/expod.ts").default

function state() {
    return {
        expPool: db.prepare("SELECT exp_pool FROM player_state WHERE id = 7").get().exp_pool,
        characterExp: db.prepare(
            "SELECT exp FROM character_state WHERE player_id = 7 AND character_id = 100001",
        ).get().exp,
        counters: counterDomain.getActiveMissionCountersSync(7),
    }
}

function setExpPool(value) {
    db.prepare("UPDATE player_state SET exp_pool = ? WHERE id = 7").run(value)
}

async function injectExp(fastify, exp) {
    const payload = { viewer_id: 123, character_id: 100001 }
    if (exp !== undefined) payload.exp = exp
    return fastify.inject({ method: "POST", url: "/inject_exp", payload })
}

async function main() {
    const fastify = Fastify()
    fastify.addHook("onSend", (_request, reply, payload, done) => {
        if (String(reply.getHeader("content-type") ?? "").includes("application/x-msgpack")) {
            done(null, pack(payload))
            return
        }
        done(null, payload)
    })
    await fastify.register(expodRoutes)
    await fastify.ready()
    try {
        const success = await injectExp(fastify, 1000)
        assert.equal(success.statusCode, 200, success.body)
        assert.equal(state().expPool, 1000)
        assert.equal(state().characterExp, 1000)
        assert.equal(state().counters.totalInjectedExpCount, 1)

        const beforeFailure = state()
        failExpWrite = true
        const failed = await injectExp(fastify, 500)
        failExpWrite = false
        assert.equal(failed.statusCode, 500)
        assert.deepEqual(state(), beforeFailure, "角色经验写入失败必须回滚经验池和 Active Mission 计数")

        const exact = await injectExp(fastify, 1000)
        assert.equal(exact.statusCode, 200, exact.body)
        assert.equal(unpack(exact.rawPayload).data.user_info.exp_pool, 0)
        assert.equal(state().expPool, 0, "正好花完经验池必须写入 0")

        setExpPool(1000)
        pendingPooledExp = 1
        const refreshed = await injectExp(fastify, 1001)
        assert.equal(refreshed.statusCode, 200, refreshed.body)
        assert.equal(unpack(refreshed.rawPayload).data.add_exp_list[0].add_exp, 1001)
        assert.equal(state().expPool, 0, "强化前应先结算客户端已经显示的被动经验")

        setExpPool(1000)
        const clamped = await injectExp(fastify, 1001)
        assert.equal(clamped.statusCode, 200, clamped.body)
        assert.equal(unpack(clamped.rawPayload).data.add_exp_list[0].add_exp, 1000)
        assert.equal(state().expPool, 0, "客户端余额过期时应使用实际剩余经验，而不是返回 H400")

        const beforeEmpty = state()
        const empty = await injectExp(fastify, 500)
        assert.equal(empty.statusCode, 200, empty.body)
        assert.equal(unpack(empty.rawPayload).data.add_exp_list[0].add_exp, 0)
        assert.equal(state().characterExp, beforeEmpty.characterExp)
        assert.equal(
            state().counters.totalInjectedExpCount,
            beforeEmpty.counters.totalInjectedExpCount,
            "空经验池的正常空操作不应累计 Active Mission 注入次数",
        )

        setExpPool(50)
        const signedDelta = await injectExp(fastify, -20)
        assert.equal(signedDelta.statusCode, 200, signedDelta.body)
        assert.equal(unpack(signedDelta.rawPayload).data.add_exp_list[0].add_exp, 20)
        assert.equal(state().expPool, 30)

        for (const exp of [0, 1.5, Number.MAX_SAFE_INTEGER + 1, undefined]) {
            const beforeInvalid = state()
            const invalid = await injectExp(fastify, exp)
            assert.equal(invalid.statusCode, 400, `exp=${String(exp)} 应被拒绝`)
            assert.deepEqual(state(), beforeInvalid, `exp=${String(exp)} 不得修改存档`)
        }
    } finally {
        await fastify.close()
        db.close()
    }
}

main().then(
    () => console.log("expod inject exp route tests passed"),
    error => {
        console.error(error)
        process.exitCode = 1
    },
)
