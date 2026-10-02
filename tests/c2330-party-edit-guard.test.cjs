const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const { test, after } = require("node:test")

const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "c2330-party-edit-"))
process.env.DATA_DIR = dataDir
require("ts-node/register/transpile-only")

const Fastify = require("fastify")
const { SessionType, PartyCategory } = require("../src/data/types")
const { insertAccountSync } = require("../src/data/domains/account")
const { insertDefaultPlayerSync, updatePlayerSync } = require("../src/data/domains/player")
const { insertSessionWithTokenSync } = require("../src/data/domains/session")
const { updatePlayerPartySync } = require("../src/data/domains/party")
const { getDb } = require("../src/data/db")
const routes = require("../src/routes/api/party").default

const account = insertAccountSync({
    appId: "c2330-party-edit-test",
    idpAlias: "test",
    idpCode: "c2330-party-edit-test",
    idpId: "c2330-party-edit-test",
    status: "active",
})
const player = insertDefaultPlayerSync(account.id)
const viewerId = 710000101
insertSessionWithTokenSync({
    token: String(viewerId),
    accountId: account.id,
    expires: new Date(Date.now() + 600_000),
    type: SessionType.VIEWER,
})

const app = Fastify()
app.addHook("onSend", (_request, reply, payload, done) => {
    done(null, reply.getHeader("content-type") === "application/x-msgpack"
        ? JSON.stringify(payload)
        : payload)
})
app.register(routes, { prefix: "/party" })

function edit(partyId, characterIds, category = PartyCategory.NORMAL) {
    return {
        party_edited: true,
        party_category: category,
        party_name: "C2330 test",
        party_id: partyId,
        character_ids: characterIds,
        unison_character_ids: [null, null, null],
        equipment_ids: [null, null, null],
        ability_soul_ids: [null, null, null],
        options: { allow_other_players_to_heal_me: true },
    }
}

after(async () => {
    await app.close()
    getDb().close()
    fs.rmSync(dataDir, { recursive: true, force: true })
})

test("empty battle character array is rejected without writing the party", async () => {
    const db = getDb()
    const before = db.prepare(`SELECT character_id_1, character_id_2, character_id_3
        FROM players_parties WHERE player_id = ? AND category = ? AND group_id = 1 AND slot = 1`)
        .get(player.id, PartyCategory.NORMAL)
    const response = await app.inject({
        method: "POST",
        url: "/party/edit",
        payload: { viewer_id: viewerId, main_party_id: 1, party_info_list: [edit(1, [])] },
    })
    assert.equal(response.statusCode, 200)
    assert.equal(response.json().data_headers.result_code, 2330)
    assert.deepEqual(db.prepare(`SELECT character_id_1, character_id_2, character_id_3
        FROM players_parties WHERE player_id = ? AND category = ? AND group_id = 1 AND slot = 1`)
        .get(player.id, PartyCategory.NORMAL), before)
})

test("repairing and selecting an empty normal SET in one request keeps that SET selected", async () => {
    const db = getDb()
    updatePlayerPartySync(player.id, 4, {
        name: "broken",
        characterIds: [null, null, null],
        unisonCharacterIds: [null, null, null],
        equipmentIds: [null, null, null],
        abilitySoulIds: [null, null, null],
        edited: false,
        options: { allowOtherPlayersToHealMe: true },
        category: PartyCategory.NORMAL,
    }, 1)
    updatePlayerSync({ id: player.id, partySlot: 1 })

    const response = await app.inject({
        method: "POST",
        url: "/party/edit",
        payload: { viewer_id: viewerId, main_party_id: 4, party_info_list: [edit(4, [1, null, null])] },
    })
    assert.equal(response.statusCode, 200)
    assert.equal(response.json().data_headers.result_code, 1)
    assert.equal(db.prepare("SELECT party_slot FROM players WHERE id = ?").get(player.id).party_slot, 4)
    assert.equal(db.prepare(`SELECT character_id_1 FROM players_parties
        WHERE player_id = ? AND category = ? AND group_id = 1 AND slot = 4`)
        .get(player.id, PartyCategory.NORMAL).character_id_1, 1)
})

test("empty favorites remain writable without changing the normal selection", async () => {
    const db = getDb()
    updatePlayerSync({ id: player.id, partySlot: 4 })
    const response = await app.inject({
        method: "POST",
        url: "/party/edit",
        payload: { viewer_id: viewerId, main_party_id: 999, party_info_list: [edit(1, [], 99)] },
    })
    assert.equal(response.statusCode, 200)
    assert.equal(response.json().data_headers.result_code, 1)
    assert.equal(db.prepare("SELECT party_slot FROM players WHERE id = ?").get(player.id).party_slot, 4)
    assert.equal(db.prepare(`SELECT character_id_1 FROM players_parties
        WHERE player_id = ? AND category = 99 AND group_id = 1 AND slot = 1`)
        .get(player.id).character_id_1, null)
})

test("leader ownership is rechecked after the write queue boundary", async () => {
    const db = getDb()
    const persistence = require("../src/lib/persistence-coordinator")
    const original = persistence.runPersistenceTransaction
    persistence.runPersistenceTransaction = (context, operation) => original(context, () => {
        db.prepare("DELETE FROM players_characters WHERE player_id = ? AND id = 1").run(player.id)
        return operation()
    })
    try {
        const response = await app.inject({
            method: "POST",
            url: "/party/edit",
            payload: { viewer_id: viewerId, main_party_id: 4, party_info_list: [edit(4, [1, null, null])] },
        })
        assert.equal(response.statusCode, 200)
        assert.equal(response.json().data_headers.result_code, 2330)
        assert.equal(db.prepare(`SELECT character_id_1 FROM players_parties
            WHERE player_id = ? AND category = ? AND group_id = 1 AND slot = 4`)
            .get(player.id, PartyCategory.NORMAL).character_id_1, 1)
    } finally {
        persistence.runPersistenceTransaction = original
    }
})
