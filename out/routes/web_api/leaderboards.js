"use strict";
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
Object.defineProperty(exports, "__esModule", { value: true });
const leaderboard_1 = require("../../data/domains/leaderboard");
const competition_1 = require("../../lib/leaderboard/competition");
const settlement_1 = require("../../lib/leaderboard/settlement");
const availability_1 = require("../../lib/leaderboard/availability");
function resolveKey(request, reply) {
    const key = request.params.key;
    if ((0, competition_1.getLeaderboardCompetition)(key) !== null)
        return key;
    reply.status(404).send({ error: "Leaderboard competition not found." });
    return null;
}
const routes = (fastify) => __awaiter(void 0, void 0, void 0, function* () {
    fastify.get("/", (_request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        return reply.send((0, competition_1.getLeaderboardCompetitions)().map(competition => ({
            competition,
            availability: (0, availability_1.getLeaderboardAvailabilitySync)(competition.key),
            overview: (0, settlement_1.getLeaderboardSettlementOverviewSync)(competition.key),
        })));
    }));
    fastify.get("/:key", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _a;
        const key = resolveKey(request, reply);
        if (key === null)
            return;
        const competition = (0, competition_1.getLeaderboardCompetition)(key);
        const season = (0, competition_1.getLeaderboardCompetitionSeasonSync)(key);
        const total = (0, leaderboard_1.countLeaderboardRanksSync)(key, season);
        const query = request.query;
        const page = Math.max(0, Math.floor(Number((_a = query.page) !== null && _a !== void 0 ? _a : 0) || 0));
        return reply.send({
            competition,
            availability: (0, availability_1.getLeaderboardAvailabilitySync)(key),
            overview: (0, settlement_1.getLeaderboardSettlementOverviewSync)(key),
            page,
            rows: (0, leaderboard_1.getLeaderboardRankPageSync)({
                competitionKey: key,
                season,
                offset: page * competition.pageSize,
                limit: competition.pageSize,
            }),
            total,
        });
    }));
    fastify.patch("/:key/availability", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _b;
        const key = resolveKey(request, reply);
        if (key === null)
            return;
        const body = ((_b = request.body) !== null && _b !== void 0 ? _b : {});
        if (typeof body.enabled !== "boolean") {
            return reply.status(400).send({ error: "enabled must be a boolean." });
        }
        return reply.send(Object.assign({ ok: true }, (0, availability_1.setLeaderboardAvailabilitySync)(key, body.enabled)));
    }));
    fastify.patch("/:key/config", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _c;
        const key = resolveKey(request, reply);
        if (key === null)
            return;
        const current = (0, settlement_1.getLeaderboardSettlementConfigSync)(key);
        const body = ((_c = request.body) !== null && _c !== void 0 ? _c : {});
        const rewardTiers = body.rewardTiers === undefined
            ? current.rewardTiers
            : body.rewardTiers;
        try {
            (0, settlement_1.validateRewardTiers)(rewardTiers);
            (0, settlement_1.putLeaderboardSettlementConfigSync)(Object.assign(Object.assign({}, current), { autoEnabled: body.autoEnabled === undefined
                    ? current.autoEnabled : Boolean(body.autoEnabled), settleAtMs: body.settleAtMs === undefined
                    ? current.settleAtMs
                    : body.settleAtMs === null ? null : Number(body.settleAtMs), repeatIntervalMs: body.repeatIntervalMs === undefined
                    ? current.repeatIntervalMs
                    : body.repeatIntervalMs === null ? null : Number(body.repeatIntervalMs), rewardTiers, mailSubject: typeof body.mailSubject === "string"
                    ? body.mailSubject : current.mailSubject, mailBody: typeof body.mailBody === "string"
                    ? body.mailBody : current.mailBody, excludeBots: body.excludeBots === undefined
                    ? current.excludeBots : Boolean(body.excludeBots), updatedAtMs: Date.now() }));
        }
        catch (error) {
            return reply.status(400).send({
                error: error instanceof Error ? error.message : "Invalid settlement config.",
            });
        }
        return reply.send({ ok: true, config: (0, settlement_1.getLeaderboardSettlementConfigSync)(key) });
    }));
    fastify.post("/:key/settle", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const key = resolveKey(request, reply);
        if (key === null)
            return;
        const outcome = (0, settlement_1.settleLeaderboardSeasonSync)(key, "admin-manual");
        return reply.status(outcome.ok ? 200 : 409).send(outcome);
    }));
    fastify.post("/:key/rollover", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const key = resolveKey(request, reply);
        if (key === null)
            return;
        const outcome = (0, settlement_1.settleAndRolloverLeaderboardSync)(key, "admin-rollover");
        return reply.status(outcome.ok ? 200 : 409).send(outcome);
    }));
});
exports.default = routes;
