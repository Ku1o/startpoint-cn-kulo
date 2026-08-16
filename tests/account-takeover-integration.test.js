const assert = require("assert")
const fs = require("fs")
const os = require("os")
const path = require("path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-takeover-test-"))
process.env.DATA_DIR = temporaryDataDir
let runningApp = null

async function main() {
    const Fastify = require("fastify")
    const takeoverRoutes = require("../out/routes/cn/takeOver").default
    const { clearRecoveryFailuresForViewer } = require("../out/routes/cn/takeOver")
    const { installTakeoverUdidGuard } = require("../out/lib/takeover-access")
    const { getDb } = require("../out/data/db")
    const { insertAccountSync, updateAccountSync, deleteAccountSync } = require("../out/data/domains/account")
    const { insertDefaultPlayerSync } = require("../out/data/domains/player")
    const { insertDeviceBindingSync, insertSessionWithToken } = require("../out/data/domains/session")
    const { saveAccountDefaultPlayer } = require("../out/data/activeAccount")
    const { stopQuestNpcPartyPoolWorker } = require("../out/multi/npc/player-party-pool")
    const initWdfpData = require("../out/data/initializers/wdfpData").default

    async function createAccount(viewerId, deviceId, note) {
        const account = insertAccountSync({
            appId: "wf_cn",
            idpAlias: "",
            idpCode: "leiting",
            idpId: "",
            status: "normal",
        })
        const player = insertDefaultPlayerSync(account.id)
        saveAccountDefaultPlayer(account.id, player.id)
        insertDeviceBindingSync(deviceId, account.id)
        updateAccountSync({ id: account.id, adminNote: note })
        await insertSessionWithToken({
            token: String(viewerId),
            accountId: account.id,
            type: 2,
            expires: new Date(Date.now() + 86_400_000),
        })
        return { account, player }
    }

    const legacyAccount = insertAccountSync({
        appId: "wf_cn", idpAlias: "", idpCode: "leiting", idpId: "", status: "normal",
    })
    insertDeviceBindingSync(999, legacyAccount.id, "旧版设备备注")
    initWdfpData(getDb(), true)
    assert.deepEqual(
        getDb().prepare(`SELECT admin_note FROM accounts WHERE id = ?`).get(legacyAccount.id),
        { admin_note: "旧版设备备注" },
    )
    assert.deepEqual(
        getDb().prepare(`SELECT name FROM device_bindings WHERE account_id = ?`).get(legacyAccount.id),
        { name: null },
    )
    deleteAccountSync(legacyAccount.id)

    const target = await createAccount(123456789, 111, "老玩家-保留备注")
    const temporary = await createAccount(223456789, 222, null)
    const app = Fastify({ logger: false })
    runningApp = app
    app.addHook("onSend", (_request, reply, payload, done) => {
        if (reply.getHeader("content-type") === "application/x-msgpack" && typeof payload === "object") {
            done(null, JSON.stringify(payload))
            return
        }
        done(null, payload)
    })
    installTakeoverUdidGuard(app)
    await app.register(takeoverRoutes, { prefix: "/api/index.php" })
    await app.ready()

    const request = (url, body, udid) => app.inject({
        method: "POST",
        url: `/api/index.php/${url}`,
        headers: { "content-type": "application/json", udid },
        payload: body,
    })
    const data = response => JSON.parse(response.payload)

    let response = await request("take_over_register/register_take_over_data", {
        viewer_id: 123456789,
        input_password: "Abcdefg1",
    }, "old-target-udid")
    assert.strictEqual(data(response).data_headers.result_code, 1)
    assert.strictEqual(data(response).data.registered_viewer_id, 123456789)

    // One native button press can generate a burst of identical lookup
    // requests. They must count as one failed attempt rather than immediately
    // locking a legitimate player out of a following correct password.
    for (let attempt = 0; attempt < 6; attempt += 1) {
        response = await request("take_over/get_user_data_by_take_over_data", {
            viewer_id: 223456789,
            input_viewer_id: "123456789",
            input_password: "WrongPwd1",
        }, "temporary-udid")
        assert.strictEqual(data(response).data_headers.result_code, 3204)
    }

    response = await request("take_over/get_user_data_by_take_over_data", {
        viewer_id: 223456789,
        input_viewer_id: "123456789",
        input_password: "Abcdefg1",
    }, "temporary-udid")
    assert.strictEqual(data(response).data_headers.result_code, 1)
    assert.strictEqual(data(response).data.current_user.viewer_id, 223456789)
    assert.strictEqual(data(response).data.linked_user.viewer_id, 123456789)

    // Five distinct failures do lock the IP/viewer pair. An administrator
    // password reset must clear every IP-scoped lock for that viewer.
    for (let attempt = 0; attempt < 5; attempt += 1) {
        response = await request("take_over/get_user_data_by_take_over_data", {
            viewer_id: 223456789,
            input_viewer_id: "123456789",
            input_password: `Wrong${attempt}PwdA1`,
        }, "temporary-udid")
        assert.strictEqual(data(response).data_headers.result_code, 3204)
    }
    response = await request("take_over/get_user_data_by_take_over_data", {
        viewer_id: 223456789,
        input_viewer_id: "123456789",
        input_password: "Abcdefg1",
    }, "temporary-udid")
    assert.strictEqual(data(response).data_headers.result_code, 3204)
    assert.strictEqual(clearRecoveryFailuresForViewer(123456789), 1)
    response = await request("take_over/get_user_data_by_take_over_data", {
        viewer_id: 223456789,
        input_viewer_id: "123456789",
        input_password: "Abcdefg1",
    }, "temporary-udid")
    assert.strictEqual(data(response).data_headers.result_code, 1)

    // Replacing an already configured password in-game overwrites the old
    // password and clears the current IP/viewer lock. The native client uses
    // this path for its reset-password presentation.
    for (let attempt = 0; attempt < 5; attempt += 1) {
        response = await request("take_over/get_user_data_by_take_over_data", {
            viewer_id: 223456789,
            input_viewer_id: "123456789",
            input_password: `ResetLock${attempt}A1`,
        }, "temporary-udid")
        assert.strictEqual(data(response).data_headers.result_code, 3204)
    }
    response = await request("take_over_register/register_take_over_data", {
        viewer_id: 123456789,
        input_password: "ResetPwd2",
    }, "old-target-udid")
    assert.strictEqual(data(response).data_headers.result_code, 1)
    response = await request("take_over/get_user_data_by_take_over_data", {
        viewer_id: 223456789,
        input_viewer_id: "123456789",
        input_password: "Abcdefg1",
    }, "temporary-udid")
    assert.strictEqual(data(response).data_headers.result_code, 3204)
    response = await request("take_over/get_user_data_by_take_over_data", {
        viewer_id: 223456789,
        input_viewer_id: "123456789",
        input_password: "ResetPwd2",
    }, "temporary-udid")
    assert.strictEqual(data(response).data_headers.result_code, 1)

    response = await request("take_over/take_over_by_take_over_data", {
        viewer_id: 223456789,
        input_viewer_id: "123456789",
        input_password: "wrongPass1A",
        device_id: 222,
    }, "temporary-udid")
    assert.strictEqual(data(response).data_headers.result_code, 3204)
    assert.ok(getDb().prepare(`SELECT 1 FROM accounts WHERE id = ?`).get(target.account.id))
    assert.ok(getDb().prepare(`SELECT 1 FROM accounts WHERE id = ?`).get(temporary.account.id))

    response = await request("take_over/take_over_by_take_over_data", {
        viewer_id: 223456789,
        input_viewer_id: "123456789",
        input_password: "ResetPwd2",
        device_id: 222,
    }, "new-target-udid")
    const transferred = data(response)
    assert.strictEqual(transferred.data_headers.result_code, 1)
    assert.strictEqual(transferred.data.abolished_viewer_id, 223456789)
    assert.strictEqual(transferred.data.linked_viewer_id, 123456789)

    const targetRow = getDb().prepare(`
        SELECT admin_note, takeover_password, takeover_udid FROM accounts WHERE id = ?
    `).get(target.account.id)
    assert.deepEqual(targetRow, {
        admin_note: "老玩家-保留备注",
        takeover_password: "ResetPwd2",
        takeover_udid: "new-target-udid",
    })
    assert.strictEqual(getDb().prepare(`SELECT 1 FROM accounts WHERE id = ?`).get(temporary.account.id), undefined)
    assert.strictEqual(getDb().prepare(`SELECT 1 FROM players WHERE id = ?`).get(temporary.player.id), undefined)
    assert.deepEqual(
        getDb().prepare(`SELECT device_id, account_id FROM device_bindings`).all(),
        [{ device_id: 222, account_id: target.account.id }],
    )
    const audit = getDb().prepare(`
        SELECT source_viewer_id, source_player_count, target_note, source
        FROM account_transfer_audit ORDER BY id DESC LIMIT 1
    `).get()
    assert.deepEqual(audit, {
        source_viewer_id: "223456789",
        source_player_count: 1,
        target_note: "老玩家-保留备注",
        source: "in_game",
    })

    response = await request("take_over_register/get_take_over_setting", {
        viewer_id: 123456789,
    }, "old-target-udid")
    assert.strictEqual(data(response).data_headers.result_code, 516)

    response = await request("take_over_register/get_take_over_setting", {
        viewer_id: 123456789,
    }, "new-target-udid")
    assert.strictEqual(data(response).data_headers.result_code, 1)
    assert.strictEqual(data(response).data.exists_user_take_over_data, true)

    // Title-menu recovery has no current viewer and must not create a throwaway
    // account. It moves the same account and reports abolished_viewer_id = 0.
    response = await request("take_over/take_over_by_take_over_data", {
        input_viewer_id: "123456789",
        input_password: "ResetPwd2",
        device_id: 444,
    }, "title-recovery-udid")
    assert.strictEqual(data(response).data_headers.result_code, 1)
    assert.strictEqual(data(response).data.abolished_viewer_id, 0)
    assert.deepEqual(
        getDb().prepare(`SELECT device_id, account_id FROM device_bindings`).all(),
        [{ device_id: 444, account_id: target.account.id }],
    )
    assert.strictEqual(getDb().prepare(`SELECT COUNT(*) AS count FROM accounts`).get().count, 1)

    response = await request("take_over_register/get_take_over_setting", {
        viewer_id: 123456789,
    }, "new-target-udid")
    assert.strictEqual(data(response).data_headers.result_code, 516)

    response = await request("take_over_register/get_take_over_setting", {
        viewer_id: 123456789,
    }, "title-recovery-udid")
    assert.strictEqual(data(response).data_headers.result_code, 1)

    await app.close()
    await stopQuestNpcPartyPoolWorker()
    console.log("account takeover integration tests passed")
}

main()
    .finally(async () => {
        try { await runningApp?.close() } catch {}
        try { await require("../out/multi/npc/player-party-pool").stopQuestNpcPartyPoolWorker() } catch {}
        try { require("../out/data/db").getDb().close() } catch {}
        const resolved = path.resolve(temporaryDataDir)
        if (resolved.startsWith(path.resolve(os.tmpdir()) + path.sep)) {
            fs.rmSync(resolved, { recursive: true, force: true })
        }
        setImmediate(() => process.exit(process.exitCode ?? 0))
    })
    .catch(error => {
        console.error(error)
        process.exitCode = 1
    })
