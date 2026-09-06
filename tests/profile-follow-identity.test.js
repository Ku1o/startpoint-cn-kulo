const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const Fastify = require("fastify")
const { pack, unpack } = require("msgpackr")

const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "starpoint-profile-identity-"))
process.env.DATA_DIR = dataDir
const { getDb } = require("../out/data/db")
const { insertAccountSync } = require("../out/data/domains/account")
const { insertDefaultPlayerSync, updatePlayerSync } = require("../out/data/domains/player")
const { insertSessionWithToken } = require("../out/data/domains/session")
const { saveAccountDefaultPlayer } = require("../out/data/activeAccount")
const {
    getPlayerIdByViewerIdSync, getViewerIdByPlayerIdSync, getFollowRelationSync,
    addFollowSync, MAX_FOLLOWERS,
} = require("../out/data/domains/follow")
const {
    RUSH_PROFILE_ID_BASE, toProfileTargetId, fromProfileTargetId,
} = require("../out/lib/profile-target")
const { buildTargetProfileSync } = require("../out/lib/follow")
const { nativeRow, buildNativeLeaderboardPayload } = require("../out/lib/leaderboard/presentation")
const { getLeaderboardCompetition } = require("../out/lib/leaderboard/competition")
const profileRoutes = require("../out/routes/api/profile").default
const followRoutes = require("../out/routes/api/follow").default

test.after(() => {
    if (getDb().open) getDb().close()
    const resolved = path.resolve(dataDir)
    assert.equal(path.dirname(resolved), path.resolve(os.tmpdir()))
    assert.ok(path.basename(resolved).startsWith("starpoint-profile-identity-"))
    fs.rmSync(resolved, { recursive: true, force: true })
})

async function player(name, withSession = true) {
    const account = insertAccountSync({
        appId: "wf_cn", idpAlias: "", idpCode: "identity-test", idpId: name, status: "normal",
    })
    const saved = insertDefaultPlayerSync(account.id)
    updatePlayerSync({ id: saved.id, name, rankPoint: 100000 })
    saveAccountDefaultPlayer(account.id, saved.id)
    const viewerId = 720000000 + saved.id
    if (withSession) await insertSessionWithToken({
        token: String(viewerId), accountId: account.id, type: 2,
        expires: new Date("2020-01-01T00:00:00Z"), // VIEWER tokens do not expire.
    })
    return { id: saved.id, accountId: account.id, viewerId, name }
}

async function api(t) {
    const app = Fastify()
    app.addHook("onSend", (_request, reply, payload, done) => {
        done(null, reply.getHeader("content-type") === "application/x-msgpack"
            ? pack(payload) : payload)
    })
    await app.register(profileRoutes, { prefix: "/profile" })
    await app.register(followRoutes, { prefix: "/follow" })
    await app.ready()
    t.after(() => app.close())
    return async (url, payload, expectedCode = 1) => {
        const response = await app.inject({ method: "POST", url, payload })
        assert.equal(response.statusCode, 200, response.payload)
        assert.match(response.headers["content-type"], /^application\/x-msgpack/)
        const body = unpack(response.rawPayload)
        assert.equal(body.data_headers.result_code, expectedCode)
        return body.data
    }
}

function rankRow(target) {
    return nativeRow({
        playerId: target.id, playerExists: true, rankNumber: 1,
        displayName: target.name, rankPoint: 100000, totalRounds: 3, clientBattleMs: 1200,
        characterIds: [1, null, null], evolutionImgLevels: [0, null, null],
    })
}

test("旧编码不截断小数或接受不安全整数", () => {
    assert.equal(toProfileTargetId(123), RUSH_PROFILE_ID_BASE + 123)
    assert.equal(fromProfileTargetId(toProfileTargetId(123)), 123)
    for (const value of [0, -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER]) {
        assert.equal(toProfileTargetId(value), 0)
    }
    for (const value of [0, 720000001, RUSH_PROFILE_ID_BASE, RUSH_PROFILE_ID_BASE + 1.5,
        NaN, Infinity, Number.MAX_SAFE_INTEGER + 1]) {
        assert.equal(fromProfileTargetId(value), null)
    }
})

for (const legacy of [false, true]) {
    test(`${legacy ? "旧编码" : "真实 ID"}的资料和全部关注操作指向同一玩家`, async t => {
        const request = await api(t)
        const owner = await player(`owner-${legacy}`)
        const target = await player(`target-${legacy}`)
        const targetId = legacy ? toProfileTargetId(target.id) : rankRow(target).id
        const ownerId = legacy ? toProfileTargetId(owner.id) : owner.viewerId
        const profile = async state => {
            const data = await request("/profile/get_profile", {
                viewer_id: owner.viewerId, target_viewer_id: targetId,
            })
            assert.equal(data.target_user_info.viewer_id, target.viewerId)
            assert.equal(data.target_user_info.name, target.name)
            assert.equal(data.target_user_info.follow_state, state)
            assert.equal(getFollowRelationSync(owner.id, target.id).state, state)
        }
        await profile(0)
        await request("/follow/add", { viewer_id: owner.viewerId, follow_id: targetId })
        await profile(2)
        // The client's follow button uses the real ID returned by get_profile.
        await request("/follow/delete", { viewer_id: owner.viewerId, follow_id: target.viewerId })
        await profile(0)
        await request("/follow/add", { viewer_id: target.viewerId, follow_id: ownerId })
        await profile(3)
        await request("/follow/bulk_edit", {
            viewer_id: owner.viewerId, add_follow_id_list: [targetId, target.viewerId],
            delete_follow_id_list: [],
        })
        await profile(1)
        const lists = await request("/follow/lists", { viewer_id: owner.viewerId })
        assert.equal(lists.follow_info.length, 1)
        assert.equal(lists.follow_info[0].viewer_id, target.viewerId)
        assert.equal(lists.follow_info[0].follow_state, 1)
        await request("/follow/delete_followed", { viewer_id: owner.viewerId, followed_id: targetId })
        await profile(2)
        await request("/follow/delete", { viewer_id: owner.viewerId, follow_id: targetId })
        await profile(0)
        await request("/follow/add", { viewer_id: owner.viewerId, follow_id: targetId })
        await request("/follow/bulk_edit", {
            viewer_id: owner.viewerId, add_follow_id_list: [], delete_follow_id_list: [targetId],
        })
        await profile(0)
        const result = await request("/follow/search_id", {
            viewer_id: owner.viewerId, search_id: String(target.viewerId),
        })
        assert.equal(result.search_result.viewer_id, target.viewerId)
    })
}

test("没有 viewer 身份的排行榜记录保留成绩但不提供资料链接", async t => {
    const request = await api(t)
    const owner = await player("missing-owner")
    const target = await player("missing-target", false)
    assert.equal(getViewerIdByPlayerIdSync(target.id), null)
    const row = rankRow(target)
    assert.equal(row.id, 0)
    assert.equal(row.rank, "1位")
    assert.equal(row.name, target.name)
    assert.equal(row.visible, true)
    assert.equal(buildTargetProfileSync(owner.id, target.id), null)
    for (const id of [target.viewerId, toProfileTargetId(target.id), toProfileTargetId(999999)]) {
        assert.deepEqual(await request("/profile/get_profile", {
            viewer_id: owner.viewerId, target_viewer_id: id,
        }, 1457), {})
        await request("/follow/add", { viewer_id: owner.viewerId, follow_id: id }, 1457)
    }
    assert.equal(getFollowRelationSync(owner.id, target.id).state, 0)
})

test("同账号切换存档不会把排行榜资料或旧缓存的关注操作指向另一存档", async t => {
    const request = await api(t)
    const owner = await player("archive-owner")
    const target = await player("archive-active")
    const alternate = insertDefaultPlayerSync(target.accountId)
    updatePlayerSync({ id: alternate.id, name: "archive-alternate" })
    assert.equal(getViewerIdByPlayerIdSync(target.id), target.viewerId)
    assert.equal(getViewerIdByPlayerIdSync(alternate.id), null)
    saveAccountDefaultPlayer(target.accountId, alternate.id)
    assert.equal(getPlayerIdByViewerIdSync(target.viewerId), alternate.id)
    assert.equal(getViewerIdByPlayerIdSync(target.id), null)
    assert.equal(rankRow(target).id, 0)
    await request("/profile/get_profile", {
        viewer_id: owner.viewerId, target_viewer_id: toProfileTargetId(target.id),
    }, 1457)
    await request("/follow/add", {
        viewer_id: owner.viewerId, follow_id: toProfileTargetId(target.id),
    }, 1457)
    assert.equal(getFollowRelationSync(owner.id, target.id).state, 0)
    assert.equal(getFollowRelationSync(owner.id, alternate.id).state, 0)
    const data = await request("/profile/get_profile", {
        viewer_id: owner.viewerId, target_viewer_id: target.viewerId,
    })
    assert.equal(data.target_user_info.name, "archive-alternate")
    assert.equal(data.target_user_info.viewer_id, target.viewerId)
    saveAccountDefaultPlayer(target.accountId, target.id)
    assert.equal(rankRow(target).id, target.viewerId)
})

test("自己的资料及排名外条目使用真实 ID，自关注与错误目标不创建关系", async t => {
    const request = await api(t)
    const owner = await player("self-owner")
    const payload = buildNativeLeaderboardPayload(getLeaderboardCompetition("rush:700099:1"), owner.id)
    assert.equal(payload.item.id, owner.viewerId)
    const profile = await request("/profile/get_profile", {
        viewer_id: owner.viewerId, target_viewer_id: payload.item.id,
    })
    assert.equal(profile.target_user_info.viewer_id, owner.viewerId)
    for (const id of [owner.viewerId, toProfileTargetId(owner.id), 0, -1,
        toProfileTargetId(owner.id) + 0.5, Number.MAX_SAFE_INTEGER + 1]) {
        await request("/follow/add", { viewer_id: owner.viewerId, follow_id: id }, 1457)
    }
    assert.equal(getFollowRelationSync(owner.id, owner.id).state, 0)
})

test("旧编码批量关注遇到粉丝上限时返回真实 viewer ID", async t => {
    const request = await api(t)
    const owner = await player("full-owner")
    const target = await player("full-target")
    for (let index = 0; index < MAX_FOLLOWERS; index++) {
        const follower = await player(`full-follower-${index}`, false)
        assert.equal(addFollowSync(follower.id, target.id), "added")
    }
    const result = await request("/follow/bulk_edit", {
        viewer_id: owner.viewerId,
        add_follow_id_list: [toProfileTargetId(target.id)], delete_follow_id_list: [],
    })
    assert.deepEqual(result.max_follower_user_viewer_id_list, [target.viewerId])
    assert.equal(getFollowRelationSync(owner.id, target.id).state, 0)
})
