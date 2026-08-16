const assert = require("node:assert/strict")
const fs = require("fs")
const os = require("os")
const path = require("path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-party-code-test-"))
process.env.DATA_DIR = temporaryDataDir

async function main() {
    const { getDb } = require("../out/data/db")
    const { insertAccountSync } = require("../out/data/domains/account")
    const { insertDefaultPlayerSync } = require("../out/data/domains/player")
    const {
        getPublishedPartySync,
        MAX_PUBLISHED_PARTIES_PER_PLAYER,
        publishPartySync,
    } = require("../out/data/domains/publishedParty")

    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "leiting",
        idpId: "",
        status: "normal",
    })
    const player = insertDefaultPlayerSync(account.id)
    const publishedCodes = []

    assert.equal(MAX_PUBLISHED_PARTIES_PER_PLAYER, 50)
    for (let index = 0; index <= MAX_PUBLISHED_PARTIES_PER_PLAYER; index++) {
        publishedCodes.push(publishPartySync(player.id, `Party ${index}`, {
            characters: [{ id: 101001 + index }],
        }))
    }

    const retained = getDb().prepare(`
        SELECT COUNT(*) AS count
        FROM published_parties
        WHERE owner_player_id = ?
    `).get(player.id).count

    assert.equal(retained, MAX_PUBLISHED_PARTIES_PER_PLAYER)
    assert.equal(getPublishedPartySync(publishedCodes[0]), null)
    assert.equal(
        getPublishedPartySync(publishedCodes[MAX_PUBLISHED_PARTIES_PER_PLAYER]).partyName,
        `Party ${MAX_PUBLISHED_PARTIES_PER_PLAYER}`,
    )

    console.log("published party retention limit tests passed")
}

main()
    .finally(() => {
        try { require("../out/data/db").getDb().close() } catch {}
        const resolved = path.resolve(temporaryDataDir)
        if (resolved.startsWith(path.resolve(os.tmpdir()) + path.sep)) {
            fs.rmSync(resolved, { recursive: true, force: true })
        }
    })
    .catch(error => {
        console.error(error)
        process.exitCode = 1
    })
