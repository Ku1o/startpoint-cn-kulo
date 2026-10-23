import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import seedValidator, { PoolMode, SeedTag, SeedValidator, SeedAdminColumn } from "../../lib/seed-validator";
import { join } from "path";
import { SeedFileCountCache } from "../../lib/seed-file-count-cache";

const ASSETS_DIR = join(__dirname, "..", "..", "..", "assets");

const GROUPS: Readonly<Record<string, readonly string[]>> = {
    fes: ["fes", "fes_guarantee"], normal: ["normal", "normal_guarantee"],
};

interface ModeBody { mode: PoolMode; selectedMovieId?: string; }
interface TagBody { seed: number; tag: SeedTag; movieId: string; }

export function createSeedsAdminRoutes(validator: SeedValidator = seedValidator, counts = new SeedFileCountCache(ASSETS_DIR)) {
const routes = async (fastify: FastifyInstance) => {
    fastify.get("/group/:group/overview", async (request, reply) => {
        const group = (request.params as { group: string }).group;
        const movies = Object.prototype.hasOwnProperty.call(GROUPS, group) ? GROUPS[group] : undefined;
        if (!movies) return reply.status(400).send({ error: "卡池组无效" });
        if (Object.keys(request.query as object).length) return reply.status(400).send({ error: "概况参数无效" });
        const snapshot = counts.snapshot(), summary = validator.getAdminGroupSummary(movies, snapshot.catalogs);
        const catalogAvailable = movies.every(movie => snapshot.catalogs.get(movie)?.valid === true);
        const total = movies.reduce((sum, movie) => sum + (snapshot.catalogs.get(movie)?.size ?? 0), 0);
        const aggregate = { confirm: 0, pending: 0, play: 0, verified: 0, learned: 0, catalogKnown: 0, baseConfirm: 0, gtConfirm: 0,
            columns: { play: { r3: 0, r4: 0, r4b: 0, r5: 0, r5b: 0 }, verified: { r3: 0, r4: 0, r4b: 0, r5: 0, r5b: 0 } } };
        for (const movie of summary.movies) {
            for (const key of ["confirm", "pending", "play", "verified", "learned", "catalogKnown"] as const) aggregate[key] += movie[key];
            aggregate[movie.movieId.endsWith("_guarantee") ? "gtConfirm" : "baseConfirm"] += movie.confirm;
            for (const kind of ["play", "verified"] as const) for (const column of Object.keys(movie.columns[kind]) as SeedAdminColumn[]) aggregate.columns[kind][column] += movie.columns[kind][column];
        }
        return reply.send({ group, movies, mode: summary.mode, testSeeds: summary.testSeeds, testSeedTags: summary.testSeedTags,
            ...aggregate, total, catalogTotal: total, catalogAvailable,
            catalogKnown: catalogAvailable ? aggregate.catalogKnown : null,
            tested: catalogAvailable ? aggregate.catalogKnown : null,
            externalKnown: catalogAvailable ? aggregate.learned - aggregate.catalogKnown : null,
            unknown: catalogAvailable ? total - aggregate.catalogKnown : null,
            coverage: catalogAvailable && total > 0 ? aggregate.catalogKnown / total * 100 : null });
    });
    fastify.get("/group/:group/list", async (request, reply) => {
        const group = (request.params as { group: string }).group;
        const movies = Object.prototype.hasOwnProperty.call(GROUPS, group) ? GROUPS[group] : undefined;
        const query = request.query as Record<string, string | undefined>;
        const page = query.page === undefined ? 1 : Number(query.page), pageSize = query.pageSize === undefined ? 100 : Number(query.pageSize);
        if (!movies || Object.keys(query).some(key => !["kind", "page", "pageSize"].includes(key))
            || !["play", "verified"].includes(query.kind ?? "")
            || (query.page !== undefined && !/^\d+$/.test(query.page)) || (query.pageSize !== undefined && !/^\d+$/.test(query.pageSize))
            || !Number.isSafeInteger(page) || page < 1 || !Number.isSafeInteger(pageSize) || pageSize < 1 || pageSize > 200) {
            return reply.status(400).send({ error: "种子列表参数无效" });
        }
        return reply.send({ group, kind: query.kind, ...validator.getAdminSeedPage(movies, query.kind as "play" | "verified", page, pageSize) });
    });
    fastify.get("/stats", async (request: FastifyRequest, reply: FastifyReply) => {
        const mid = (request.query as any).movieId || validator.getSelectedMovieId();
        const s = validator.stats(mid), snapshot = counts.snapshot();
        const totalSeeds = snapshot.total;
        const movieTotal = snapshot.byMovie.get(mid) ?? 0;
        const known = s.confirm_total + s.play_total + (s.verified_total || 0);
        const perMovieKnown = (s.confirm || 0) + (s.mov_play || 0) + (s.verified || 0);
        return reply.status(200).send({
            movieId: mid,
            unknown: mid ? Math.max(0, movieTotal - perMovieKnown) : totalSeeds - known,
            movie_total: movieTotal,
            confirm: s.confirm, confirm_total: s.confirm_total,
            play_r3: s.play_r3, play_r4: s.play_r4, play_r5: s.play_r5, play_total: s.play_total,
            mov_play: s.mov_play,
            verified: s.verified || 0, verified_total: s.verified_total || 0,
            pending: s.pending || 0, pending_total: s.pending_total || 0,
            test_seeds: s.test_seeds,
            mode: s.mode,
            selectedMovieId: s.selectedMovieId, movieIds: s.movieIds,
            total: totalSeeds,
            tested: known, coverage: totalSeeds > 0 ? Math.round(known / totalSeeds * 100) : 0,
        });
    });

    fastify.get("/list", async (request: FastifyRequest, reply: FastifyReply) => {
        const mid = (request.query as any).movieId || validator.getSelectedMovieId() || 'fes';
        return reply.status(200).send({
            play: validator.getPlayList(mid),
            verified: validator.getVerifiedList(mid),
            movieId: mid
        });
    });

    fastify.post("/mode", async (request: FastifyRequest, reply: FastifyReply) => {
        const { mode, selectedMovieId } = request.body as ModeBody;
        if (mode !== undefined && !['natural','play','test'].includes(mode)) return reply.status(400).send({ ok: false, error: "抽取模式无效" });
        if (mode !== undefined) validator.setMode(mode);
        if (selectedMovieId) validator.setSelectedMovieId(selectedMovieId);
        return reply.status(200).send({ ok: true, mode: validator.getMode(), selectedMovieId: validator.getSelectedMovieId() });
    });

    fastify.post("/tag", async (request: FastifyRequest, reply: FastifyReply) => {
        const { seed, tag, movieId } = request.body as TagBody;
        if (!Number.isSafeInteger(seed) || seed < 0 || !['未测试','热血躲避球','普通躲避球','冷血躲避球'].includes(tag))
            return reply.status(400).send({ ok: false, error: "种子或标签无效" });
        const mid = movieId || validator.getSelectedMovieId() || 'fes';
        const ok = validator.setTag(mid, seed, tag);
        if (!ok) return reply.status(409).send({ ok: false, error: "该种子已不在播放池，标签未修改。请刷新列表后重试。" });
        await validator.flushPersistence();
        return reply.status(200).send({ seed, tag, ok });
    });

    fastify.post("/test-seed", async (request: FastifyRequest, reply: FastifyReply) => {
        const { seed, rarity } = request.body as any;
        const mid = validator.getSelectedMovieId() || 'fes';
        if (!Number.isSafeInteger(seed) || seed < 0 || ![3,4,5].includes(rarity)) return reply.status(400).send({ ok: false, error: "种子或星级无效" });
        const ok = validator.setTestSeed(mid, rarity, seed);
        return reply.status(ok ? 200 : 409).send(ok ? { ok: true } : { ok: false, error: "测试种子未设置，请刷新后重试。" });
    });

    fastify.delete("/test-seed", async (request: FastifyRequest, reply: FastifyReply) => {
        const rarity = Number((request.query as any).rarity);
        if (![3,4,5].includes(rarity)) return reply.status(400).send({ ok: false, error: "星级无效" });
        const ok = validator.clearTestSeed(rarity);
        return reply.status(ok ? 200 : 409).send(ok ? { ok: true } : { ok: false, error: "该星级当前没有测试种子，未执行清除。请刷新后重试。" });
    });
};
return routes;
}
export default createSeedsAdminRoutes();
