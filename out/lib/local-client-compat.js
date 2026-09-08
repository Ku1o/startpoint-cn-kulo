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
exports.installLocalClientCompat = void 0;
/** Local Android candidate testing while the matching iOS runtime is pending. */
function installLocalClientCompat(app, platform = process.env.CN_LOCAL_CLIENT_PLATFORM) {
    if (!platform)
        return;
    if (platform !== "android")
        throw new Error("CN_LOCAL_CLIENT_PLATFORM must be android or unset");
    app.addHook("onRequest", (request, reply) => __awaiter(this, void 0, void 0, function* () {
        var _a;
        const raw = request.headers.device;
        const device = typeof raw === "string" ? raw.trim().toLowerCase() : "";
        const url = request.url.split("?", 1)[0];
        const ios = device === "1" || device === "ios"
            || /iphone|ipad|ipod/i.test((_a = request.headers["user-agent"]) !== null && _a !== void 0 ? _a : "")
            || url.endsWith("client_release_ios.dis");
        if (ios) {
            return reply.code(409).send({
                code: "LOCAL_ANDROID_TEST_ONLY",
                message: "本地正在测试安卓新内容，请使用本次内网安卓候选包；iOS 暂未开放。",
            });
        }
    }));
}
exports.installLocalClientCompat = installLocalClientCompat;
