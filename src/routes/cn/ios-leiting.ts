import { FastifyInstance } from "fastify";
import { IosCompatConfig } from "../../lib/ios-compat";

// AES-encrypted fixed guest UserBean accepted by the iOS 1.8.4 Leiting SDK.
// The AOT iOS client cannot use the Android sdkDummy path, so these endpoints
// reproduce the native SDK's successful guest-login response.
const IOS_SDK_LOGIN_BLOB = "Ox8piDWnl7p3xCrJ3bwS8RSjUahG/oB4S8D+s39R7Bb/C7XfVkgxohfumfFMK/Or8Kppz+Bk/tZyrEHnERbc0NYeuBKFrcWdQ+gzSuuliP9kIb1uUBP9Uj0DxB49Pnr3MSs6FDp8SZXDvmPjKT8y0twAiSYGQu1GCUwpKT0uJH1zxb8Q6Zyj70UPLlRKPoKnsSRscBIlOj/ACkDy4cBCfAYFFTApjQY4+NnsddSYs40399y59OzTsKMGCuyghJeeBCeATZYeihAkkcj93Prd6YYI7jLYfUPDN4Rxlj5fx9d89ZKQcRE9GTophK7MWQdP6ihEfY49aUHvXXQjRlO3z+gAAhb2VPW8KHnmG/K0jds182SXYhY3EXqf9bPpbO8NqtYKOAx8lRQBO/h01yRP9vBITftZQ0PIee/27v4EsifUiNpGgZO0Z1nduxadLfZuScp+rsPO8LfXK9pc2LPq7Q86AuH80NfA7/zVnCzhvoOLf5G+KpyOtvlHnuVei76T0/clqHs2iBtrPv8vqlBxjeJo0g08dMbaZhYTsOrZv7Q0KSAd3lPrtI6EeB2PqNG1";

const IOS_LOGIN_OK = {
    status: "0",
    type: "0",
    message: "",
    data: IOS_SDK_LOGIN_BLOB,
};

const IOS_STATUS_OK = {
    status: "0",
    statusCode: "0",
    memo: "",
    message: "",
    data: "",
};

const IOS_LOGIN_PATHS = [
    "/mobile!mobileLoginPubV2.action",
    "/login/mobile!mobileLoginPubV2.action",
    "/mobile!sdkLogin.action",
    "/login/mobile!sdkLogin.action",
    "/mobile!guestRegister.action",
    "/login/mobile!guestRegister.action",
    "/mobile!sdkCheckLogin.action",
    "/login/mobile!sdkCheckLogin.action",
    "/sdk/v3-3/code_login_v2.do",
    "/sdk/v3-3/code_login.do",
    "/sdk/v3-3/pwd_login.do",
    "/sdk/v3-3/check_login.do",
    "/sdk/v3-3/check_force.do",
    "/sdk/v3-3/taptap_login.do",
    "/sdk/auth_login.do",
    "/sdk/v3-3/auth_login.do",
] as const;

const IOS_STUB_PATHS = [
    "/mobile_two!getRegisterCodeOnly.action",
    "/login/mobile_two!getRegisterCodeOnly.action",
    "/aes/message/send_phone_code",
    "/aes/message/send_login_verify_code",
    "/aes/message/send_bind_phone_login_code",
    "/aes/message/send_register_code",
] as const;

const SDK_LOG_PATHS = [
    "/api/sdk_log!addScreenLog",
    "/api/sdk_log!addScreenLog.action",
    "/api/sdk_api!getCaidNew",
    "/api/sdk_api!getCaidNew.action",
] as const;

const MG_LOG_PATHS = [
    "/api/mg_log!addMgActivateLog.action",
    "/api/mg_log!addMgCreateRoleLog.action",
    "/api/mg_log!addMgLoginLog.action",
    "/api/mg_log!addMgRegisterLog.action",
] as const;

export interface IosLeitingPluginOptions {
    readonly ios: IosCompatConfig;
}

export default async function iosLeitingRoutes(
    fastify: FastifyInstance,
    options: IosLeitingPluginOptions,
): Promise<void> {
    fastify.get("/area/config.json", async (_request, reply) => {
        return reply.type("application/json").send({
            area_list: [],
            cdn_list: [{ url: "" }],
        });
    });

    fastify.get("/protocols/leiting/switch/switch.txt", async (_request, reply) => {
        return reply.type("text/plain").send("{}");
    });

    fastify.get("/myip", async (request, reply) => {
        return reply.type("text/plain").send(request.ip);
    });

    fastify.post("/logmonitor/api/advert!getNewConfig.action", async (_request, reply) => {
        return reply.type("application/json").send({ code: 0, data: {} });
    });

    fastify.get("/api/skan/query_detail", async (_request, reply) => {
        return reply.type("application/json").send({ code: 0, data: {} });
    });

    for (const route of SDK_LOG_PATHS) {
        fastify.post(route, async (_request, reply) => {
            return reply.type("application/json").send({ code: 0, data: {} });
        });
    }

    for (const route of MG_LOG_PATHS) {
        fastify.all(route, async (_request, reply) => {
            return reply.type("application/json").send({ code: 0, message: "success" });
        });
    }

    fastify.get("/wf/210009_config_20200415.json", async (_request, reply) => {
        return reply.type("application/json").send({
            default: {
                apiPath: options.ios.apiHost,
                apiScheme: options.ios.apiScheme,
            },
        });
    });

    fastify.post("/sync_data", async (_request, reply) => {
        return reply.type("application/json").send({ code: 0 });
    });

    for (const route of IOS_LOGIN_PATHS) {
        fastify.all(route, async (_request, reply) => reply.send(IOS_LOGIN_OK));
    }

    for (const route of IOS_STUB_PATHS) {
        fastify.all(route, async (_request, reply) => reply.send(IOS_STATUS_OK));
    }
}
