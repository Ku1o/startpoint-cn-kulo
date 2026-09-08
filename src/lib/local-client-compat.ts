import { FastifyInstance } from "fastify";

/** Local Android candidate testing while the matching iOS runtime is pending. */
export function installLocalClientCompat(
    app: FastifyInstance,
    platform = process.env.CN_LOCAL_CLIENT_PLATFORM,
): void {
    if (!platform) return;
    if (platform !== "android") throw new Error("CN_LOCAL_CLIENT_PLATFORM must be android or unset");
    app.addHook("onRequest", async (request, reply) => {
        const raw = request.headers.device;
        const device = typeof raw === "string" ? raw.trim().toLowerCase() : "";
        const url = request.url.split("?", 1)[0];
        const ios = device === "1" || device === "ios"
            || /iphone|ipad|ipod/i.test(request.headers["user-agent"] ?? "")
            || url.endsWith("client_release_ios.dis");
        if (ios) {
            return reply.code(409).send({
                code: "LOCAL_ANDROID_TEST_ONLY",
                message: "本地正在测试安卓新内容，请使用本次内网安卓候选包；iOS 暂未开放。",
            });
        }
    });
}
