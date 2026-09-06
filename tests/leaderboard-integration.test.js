const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-leaderboard-test-"))
process.env.DATA_DIR = temporaryDataDir

const { getDb } = require("../out/data/db")
const Fastify = require("fastify")
const rushEventRoutes = require("../out/routes/api/rushEvent").default
const profileRoutes = require("../out/routes/api/profile").default
const followRoutes = require("../out/routes/api/follow").default
const { insertAccountSync } = require("../out/data/domains/account")
const { insertDefaultPlayerSync, updatePlayerSync } = require("../out/data/domains/player")
const { updatePlayerPartySync } = require("../out/data/domains/party")
const { insertSessionWithToken } = require("../out/data/domains/session")
const { saveAccountDefaultPlayer } = require("../out/data/activeAccount")
const { PROFILE_FAVORITE_PARTY_CATEGORY } = require("../out/lib/profileFavorite")
const {
    countLeaderboardRanksSync,
    getLeaderboardRankPageSync,
    getLeaderboardSeasonSync,
} = require("../out/data/domains/leaderboard")
const { getViewerIdByPlayerIdSync } = require("../out/data/domains/follow")
const { getLeaderboardCompetition } = require("../out/lib/leaderboard/competition")
const { setLeaderboardAvailabilitySync } = require("../out/lib/leaderboard/availability")
const {
    finishLeaderboardQuestSync,
    startLeaderboardQuestSync,
} = require("../out/lib/leaderboard/service")
const {
    buildLeaderboardTermsText,
    buildNativeLeaderboardPayload,
    buildUnavailableNativeLeaderboardPayload,
    getOfficialLeaderboardPageSync,
    fromProfileTargetId,
    toProfileTargetId,
} = require("../out/lib/leaderboard/presentation")
const {
    getLeaderboardSettlementConfigSync,
    rolloverLeaderboardSeasonSync,
    settleLeaderboardSeasonSync,
} = require("../out/lib/leaderboard/settlement")

const competition = getLeaderboardCompetition("rush:700099:1")
assert.ok(competition)

function createPlayer(name, idpCode = "leiting") {
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode,
        idpId: "",
        status: "normal",
    })
    const player = insertDefaultPlayerSync(account.id)
    insertSessionWithToken({
        token: String(700000000 + player.id),
        accountId: account.id,
        expires: new Date(Date.now() + 86_400_000),
        type: 2,
    })
    updatePlayerSync({ id: player.id, name, rankPoint: 100000 })
    return player.id
}

const party = {
    characterIds: [169980, 169994, 169995],
    unisonCharacterIds: [null, null, null],
    equipmentIds: [null, null, null],
    abilitySoulIds: [null, null, null],
    evolutionImgLevels: [1, 0, 1],
    unisonEvolutionImgLevels: [null, null, null],
}

function completeRun(playerId, times, startAt) {
    for (let index = 0; index < times.length; index++) {
        const round = index + 1
        const quest = {
            category: competition.category,
            eventId: competition.eventId,
            folderId: competition.folderId,
            round,
            questId: 700099000 + round,
            totalRounds: times.length,
        }
        assert.ok(startLeaderboardQuestSync(playerId, quest, startAt + index * 10_000))
        finishLeaderboardQuestSync({
            playerId,
            quest,
            accomplished: true,
            clientBattleMs: times[index],
            party,
            finishedAtMs: startAt + index * 10_000 + times[index],
        })
    }
}

function addOwnedCharacter(playerId, characterId, evolutionLevel, illustrationSettings = null) {
    getDb().prepare(`
        INSERT INTO players_characters (
            id, entry_count, evolution_level, over_limit_step, protection,
            join_time, update_time, exp, stack, mana_board_index, player_id,
            ex_boost_status_id, ex_boost_ability_id_list, illustration_settings
        ) VALUES (?, 1, ?, 0, 0, '2026-01-01', '2026-01-01', 0, 0, 1, ?, NULL, NULL, ?)
    `).run(
        characterId,
        evolutionLevel,
        playerId,
        illustrationSettings === null ? null : JSON.stringify(illustrationSettings),
    )
}

test("完整连续通关才入榜，并按最佳 client_battle_ms 去重排序", () => {
    const playerA = createPlayer("Alice")
    const playerB = createPlayer("Rush Bot", "rushbot")
    const incomplete = createPlayer("Interrupted")

    completeRun(playerA, [1000, 1000, 1000], 1_000_000)
    completeRun(playerA, [800, 800, 800], 2_000_000)
    completeRun(playerB, [700, 700, 700], 3_000_000)

    const roundTwoOnly = {
        category: competition.category,
        eventId: competition.eventId,
        folderId: competition.folderId,
        round: 2,
        questId: 700099002,
        totalRounds: 3,
    }
    startLeaderboardQuestSync(incomplete, roundTwoOnly, 4_000_000)
    finishLeaderboardQuestSync({
        playerId: incomplete,
        quest: roundTwoOnly,
        accomplished: true,
        clientBattleMs: 100,
        party,
        finishedAtMs: 4_000_100,
    })

    const season = getLeaderboardSeasonSync(competition.key)
    assert.equal(countLeaderboardRanksSync(competition.key, season), 2)
    const rows = getLeaderboardRankPageSync({
        competitionKey: competition.key,
        season,
        offset: 0,
        limit: 100,
    })
    assert.deepEqual(rows.map(row => [row.rankNumber, row.displayName, row.clientBattleMs]), [
        [1, "Rush Bot", 2100],
        [2, "Alice", 2400],
    ])

    const payload = buildNativeLeaderboardPayload(competition, playerA)
    assert.equal(payload.enabled, true)
    assert.equal(payload.name, "深渊连战")
    assert.equal(payload.item.rank, "1位")
    assert.equal(payload.item.id, getViewerIdByPlayerIdSync(playerA))
    assert.equal(payload.index, 0)
    assert.equal(payload.row, 0)
    assert.equal(payload.total, 1)
    assert.equal(payload.reward.length, 1)
    assert.deepEqual(payload.reward.map(tier => [
        tier.fromRank, tier.toRank, tier.itemId, tier.itemName, tier.itemCount,
    ]), [
        [1, 1, 999018, "竞速池十连券", 10],
    ])
    assert.equal(payload.item.a, "character/abyss_beast_playable/ui/thumb_party_unison_1")
    assert.equal(payload.item.b, "character/white_tiger_ghost_playable/ui/thumb_party_unison_0")
    assert.equal(payload.item.c, "character/maou2_playable/ui/thumb_party_unison_1")
    assert.match(buildLeaderboardTermsText(competition), /星渊主宰者/)

    addOwnedCharacter(playerA, 10, 1, [0])
    addOwnedCharacter(playerA, 111001, 1)
    const favoriteParty = {
        name: "Ranking Favorite",
        characterIds: [1, 10, 111001],
        unisonCharacterIds: [null, null, null],
        equipmentIds: [null, null, null],
        abilitySoulIds: [null, null, null],
        edited: true,
        category: PROFILE_FAVORITE_PARTY_CATEGORY,
        currentBattlePower: 0,
        beforeBattlePower: 0,
    }
    updatePlayerPartySync(playerA, 1, favoriteParty)

    const completeFavoritePayload = buildNativeLeaderboardPayload(competition, playerA)
    assert.equal(completeFavoritePayload.item.a, "character/alk/ui/thumb_party_unison_0")
    assert.equal(completeFavoritePayload.item.b, "character/white_tiger/ui/thumb_party_unison_0")
    assert.equal(completeFavoritePayload.item.c, "character/fire_dragon/ui/thumb_party_unison_1")

    updatePlayerPartySync(playerA, 1, {
        ...favoriteParty,
        characterIds: [1, null, null],
    })

    const personalizedPayload = buildNativeLeaderboardPayload(competition, playerA)
    assert.equal(personalizedPayload.item.a, "character/alk/ui/thumb_party_unison_0")
    assert.equal(personalizedPayload.item.b, "character/white_tiger_ghost_playable/ui/thumb_party_unison_0")
    assert.equal(personalizedPayload.item.c, "character/maou2_playable/ui/thumb_party_unison_1")

    const official = getOfficialLeaderboardPageSync({ competition, playerId: playerA, page: 0 })
    assert.deepEqual(official.myData.party_member_list, [
        { character_id: 1, evolution_img_level: 0 },
        { character_id: 169994, evolution_img_level: 0 },
        { character_id: 169995, evolution_img_level: 1 },
    ])

    const partyIndexes = getDb().prepare("PRAGMA index_list('players_parties')").all()
    assert.ok(partyIndexes.some(index =>
        index.name === "idx_players_parties_player_category_order"))
})

test("旧版深渊默认奖励自动升级，现有数据库不继续发旧票券", () => {
    const legacy = [
        { fromRank: 1, toRank: 1, itemId: 999015, itemName: "终焉裁定券", itemCount: 10, degreeId: 9900002, degreeName: "深渊冠军", degreeImage: "dynamic/degree/degree_mod_abyss_rush_champion.png" },
        { fromRank: 2, toRank: 3, itemId: 999015, itemName: "终焉裁定券", itemCount: 5, degreeId: 9900003, degreeName: "深渊亚季军", degreeImage: "dynamic/degree/degree_mod_abyss_rush_runner_up.png" },
        { fromRank: 4, toRank: 15, itemId: 999015, itemName: "终焉裁定券", itemCount: 2, degreeId: 9900004, degreeName: "深渊上位者", degreeImage: "dynamic/degree/degree_mod_abyss_rush_upper_rank.png" },
        { fromRank: 16, toRank: null, itemId: null, itemName: null, itemCount: 0, degreeId: 9900005, degreeName: "深渊参与者", degreeImage: "dynamic/degree/degree_mod_abyss_rush_participant.png" },
    ]
    getDb().prepare(`
        UPDATE leaderboard_settlement_configs SET reward_tiers_json = ?
        WHERE competition_key = ?
    `).run(JSON.stringify(legacy), competition.key)

    const upgraded = getLeaderboardSettlementConfigSync(competition.key)
    assert.deepEqual(upgraded.rewardTiers.map(tier => [tier.itemId, tier.itemCount]), [
        [999018, 10], [999018, 5], [999018, 5], [999018, 2], [999017, 1],
    ])
})

test("结算快照幂等，百分比榜排除机器人后发奖，换季后榜单归零", () => {
    const season = getLeaderboardSeasonSync(competition.key)
    const first = settleLeaderboardSeasonSync(competition.key, "test", 5_000_000)
    assert.equal(first.ok, true)
    assert.equal(first.rankedPlayers, 1)
    assert.equal(first.rewardedPlayers, 1)

    const settlementRows = getDb().prepare(`
        SELECT rank_number, skip_reason, item_id, item_count, degree_id
        FROM leaderboard_settlement_results
        WHERE settlement_id = ? ORDER BY rank_number
    `).all(first.settlementId)
    assert.deepEqual(settlementRows, [
        { rank_number: 1, skip_reason: null, item_id: 999018, item_count: 10, degree_id: 9900007 },
    ])
    assert.equal(getDb().prepare("SELECT COUNT(*) count FROM players_mails").get().count, 2)

    const repeated = settleLeaderboardSeasonSync(competition.key, "test-repeat", 5_100_000)
    assert.equal(repeated.reason, "already-settled")
    assert.equal(repeated.settlementId, first.settlementId)
    assert.equal(getDb().prepare("SELECT COUNT(*) count FROM players_mails").get().count, 2)

    const rollover = rolloverLeaderboardSeasonSync(competition.key, "test-rollover", 5_200_000)
    assert.equal(rollover.ok, true)
    assert.equal(rollover.rolled, true)
    assert.equal(rollover.nextSeason, season + 1)
    assert.equal(countLeaderboardRanksSync(competition.key, season + 1), 0)

    const unsettledRollover = rolloverLeaderboardSeasonSync(
        competition.key,
        "test-empty-rollover",
        5_300_000,
    )
    assert.equal(unsettledRollover.ok, false)
    assert.equal(unsettledRollover.reason, "season-not-settled")
    assert.equal(unsettledRollover.rolled, false)
    assert.equal(unsettledRollover.nextSeason, season + 1)

    const emptySettlement = settleLeaderboardSeasonSync(
        competition.key,
        "test-empty-settlement",
        5_400_000,
    )
    assert.equal(emptySettlement.ok, true)
    assert.equal(emptySettlement.rankedPlayers, 0)
    const emptyRollover = rolloverLeaderboardSeasonSync(
        competition.key,
        "test-empty-rollover",
        5_500_000,
    )
    assert.equal(emptyRollover.ok, true)
    assert.equal(emptyRollover.rolled, true)
    assert.equal(emptyRollover.nextSeason, season + 2)
})

test("独立 Rush 排行接口返回原生 item/reward/total 字段", async t => {
    const account = insertAccountSync({
        appId: "wf_cn", idpAlias: "", idpCode: "leiting", idpId: "", status: "normal",
    })
    const player = insertDefaultPlayerSync(account.id)
    updatePlayerSync({ id: player.id, name: "Native Client", rankPoint: 100000 })
    saveAccountDefaultPlayer(account.id, player.id)
    const viewerId = 77119912
    await insertSessionWithToken({
        token: String(viewerId),
        accountId: account.id,
        expires: new Date(Date.now() + 86_400_000),
        type: 2,
    })
    setLeaderboardAvailabilitySync(competition.key, true)
    completeRun(player.id, [900, 900, 900], 6_000_000)

    const app = Fastify({ logger: false })
    app.addHook("onSend", (_request, reply, payload, done) => {
        const contentType = String(reply.getHeader("content-type") ?? "")
        done(null, contentType.startsWith("application/x-msgpack") && typeof payload === "object"
            ? JSON.stringify(payload)
            : payload)
    })
    await app.register(rushEventRoutes, { prefix: "/event/rush" })
    await app.register(profileRoutes, { prefix: "/profile" })
    await app.ready()
    t.after(() => app.close())

    const response = await app.inject({
        method: "POST",
        url: "/event/rush/leaderboard",
        headers: { "content-type": "application/json" },
        payload: { viewer_id: viewerId, event_id: 700099 },
    })
    assert.equal(response.statusCode, 200, response.payload)
    const data = JSON.parse(response.payload).data
    assert.equal(data.rows.length, 1)
    assert.equal(data.item.id, viewerId)
    assert.equal(data.item.rank, "1位")
    assert.equal(data.page, 0)
    assert.equal(data.row, 0)
    assert.equal(data.index, 0)
    assert.equal(data.total, 1)
    assert.equal(data.reward.length, 1)

    const profileResponse = await app.inject({
        method: "POST",
        url: "/profile/get_profile",
        headers: { "content-type": "application/json" },
        payload: { viewer_id: viewerId, target_viewer_id: data.item.id },
    })
    assert.equal(profileResponse.statusCode, 200, profileResponse.payload)
    const profileData = JSON.parse(profileResponse.payload).data
    assert.equal(profileData.target_user_info.name, "Native Client")
    assert.equal(profileData.target_user_info.viewer_id, viewerId)

    const legacyProfileResponse = await app.inject({
        method: "POST",
        url: "/profile/get_profile",
        headers: { "content-type": "application/json" },
        payload: { viewer_id: viewerId, target_viewer_id: toProfileTargetId(player.id) },
    })
    assert.equal(legacyProfileResponse.statusCode, 200, legacyProfileResponse.payload)
    assert.equal(JSON.parse(legacyProfileResponse.payload).data.target_user_info.name, "Native Client")
    assert.equal(JSON.parse(legacyProfileResponse.payload).data.target_user_info.viewer_id, viewerId)
})

test("排行榜资料页返回真实 viewer ID 并保持关注四态", async t => {
    const viewerAccount = insertAccountSync({
        appId: "wf_cn", idpAlias: "", idpCode: "leaderboard-follow-viewer", idpId: "", status: "normal",
    })
    const targetAccount = insertAccountSync({
        appId: "wf_cn", idpAlias: "", idpCode: "leaderboard-follow-target", idpId: "", status: "normal",
    })
    const viewerPlayer = insertDefaultPlayerSync(viewerAccount.id)
    const targetPlayer = insertDefaultPlayerSync(targetAccount.id)
    updatePlayerSync({ id: viewerPlayer.id, name: "Rank viewer", rankPoint: 100000 })
    updatePlayerSync({ id: targetPlayer.id, name: "Rank target", rankPoint: 100000 })
    saveAccountDefaultPlayer(viewerAccount.id, viewerPlayer.id)
    saveAccountDefaultPlayer(targetAccount.id, targetPlayer.id)
    const viewerId = 77120001
    const targetViewerId = 77120002
    await insertSessionWithToken({
        token: String(viewerId), accountId: viewerAccount.id,
        expires: new Date(Date.now() + 86_400_000), type: 2,
    })
    await insertSessionWithToken({
        token: String(targetViewerId), accountId: targetAccount.id,
        expires: new Date(Date.now() + 86_400_000), type: 2,
    })

    const app = Fastify({ logger: false })
    app.addHook("onSend", (_request, reply, payload, done) => {
        const contentType = String(reply.getHeader("content-type") ?? "")
        done(null, contentType.startsWith("application/x-msgpack") && typeof payload === "object"
            ? JSON.stringify(payload)
            : payload)
    })
    await app.register(profileRoutes, { prefix: "/profile" })
    await app.register(followRoutes, { prefix: "/follow" })
    await app.ready()
    t.after(() => app.close())

    const getProfile = async () => {
        const response = await app.inject({
            method: "POST",
            url: "/profile/get_profile",
            headers: { "content-type": "application/json" },
            payload: { viewer_id: viewerId, target_viewer_id: targetViewerId },
        })
        assert.equal(response.statusCode, 200, response.payload)
        return JSON.parse(response.payload).data.target_user_info
    }
    const follow = async (url, payload) => {
        const response = await app.inject({
            method: "POST", url, headers: { "content-type": "application/json" }, payload,
        })
        assert.equal(response.statusCode, 200, response.payload)
        assert.equal(JSON.parse(response.payload).data_headers.result_code, 1)
    }

    let profile = await getProfile()
    assert.equal(profile.viewer_id, targetViewerId)
    assert.equal(profile.follow_state, 0)

    // An incoming-only edge must not make the profile button look like cancel.
    await follow("/follow/add", { viewer_id: targetViewerId, follow_id: viewerId })
    profile = await getProfile()
    assert.equal(profile.follow_state, 3)

    // The profile button sends the real target viewer id and must affect the
    // same player shown by the leaderboard.
    await follow("/follow/add", { viewer_id: viewerId, follow_id: targetViewerId })
    profile = await getProfile()
    assert.equal(profile.follow_state, 1)

    await follow("/follow/delete", { viewer_id: viewerId, follow_id: targetViewerId })
    profile = await getProfile()
    assert.equal(profile.follow_state, 3)
})

test("unregistered Rush leaderboard returns a protocol-safe disabled payload", async (t) => {
    const viewerId = 703758899
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: `leaderboard-disabled-${viewerId}`,
        idpId: "",
        status: "normal",
    })
    const player = insertDefaultPlayerSync(account.id)
    updatePlayerSync({ id: player.id, name: "disabled-ranking", rankPoint: 100000 })
    saveAccountDefaultPlayer(account.id, player.id)
    await insertSessionWithToken({
        token: String(viewerId),
        accountId: account.id,
        expires: new Date(Date.now() + 86_400_000),
        type: 2,
    })

    const app = Fastify({ logger: false })
    app.addHook("onSend", (_request, reply, payload, done) => {
        const contentType = String(reply.getHeader("content-type") ?? "")
        done(null, contentType.startsWith("application/x-msgpack") && typeof payload === "object"
            ? JSON.stringify(payload)
            : payload)
    })
    await app.register(rushEventRoutes, { prefix: "/event/rush" })
    await app.ready()
    t.after(() => app.close())

    const response = await app.inject({
        method: "POST",
        url: "/event/rush/leaderboard",
        headers: { "content-type": "application/json" },
        payload: { viewer_id: viewerId, event_id: 700098 },
    })
    assert.equal(response.statusCode, 200, response.payload)
    const data = JSON.parse(response.payload).data
    assert.deepEqual(data, buildUnavailableNativeLeaderboardPayload())
    assert.equal(data.enabled, false)
    assert.equal(data.total, 0)
    assert.deepEqual(data.rows, [])
})
