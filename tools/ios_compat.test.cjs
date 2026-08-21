const assert = require("node:assert/strict");
const Fastify = require("fastify");

const { parseIosCompatConfig } = require("../out/lib/ios-compat");
const versionCheckPlugin = require("../out/routes/cn/versionCheck").default;
const iosLeitingPlugin = require("../out/routes/cn/ios-leiting").default;

const ANDROID_VERSION_DATA = [
    "// 用于官服正式用",
    JSON.stringify({ default: { apiPath: "shijtswygamegf.leiting.com" } }),
].join("\r\n");

async function testConfig() {
    const warnings = [];
    assert.deepEqual(
        parseIosCompatConfig({}, message => warnings.push(message)),
        { enabled: false, apiHost: "", apiScheme: "http" },
    );
    assert.deepEqual(
        parseIosCompatConfig({
            IOS_COMPAT_ENABLED: "1",
            IOS_API_HOST: "175.178.160.158",
            IOS_API_SCHEME: "http",
        }),
        { enabled: true, apiHost: "175.178.160.158", apiScheme: "http" },
    );
    assert.equal(
        parseIosCompatConfig({
            IOS_COMPAT_ENABLED: "1",
            IOS_API_HOST: "http://175.178.160.158",
        }, message => warnings.push(message)).enabled,
        false,
    );
    assert.equal(warnings.length, 1);
}

async function testVersionSplit() {
    const enabled = {
        enabled: true,
        apiHost: "175.178.160.158",
        apiScheme: "http",
    };
    const app = Fastify();
    await app.register(versionCheckPlugin, { ios: enabled });

    const android = await app.inject({
        method: "GET",
        url: "/shijtswy/version/client_release_android.dis",
    });
    assert.equal(android.statusCode, 200);
    assert.equal(android.body, ANDROID_VERSION_DATA);

    const ios = await app.inject({
        method: "GET",
        url: "/shijtswy/version/client_release_ios.dis",
    });
    assert.equal(ios.statusCode, 200);
    assert.deepEqual(JSON.parse(ios.body.split("\r\n")[1]), {
        default: { apiPath: "175.178.160.158", apiScheme: "http" },
    });
    await app.close();

    const disabledApp = Fastify();
    await disabledApp.register(versionCheckPlugin, {
        ios: { enabled: false, apiHost: "", apiScheme: "http" },
    });
    const disabledIos = await disabledApp.inject({
        method: "GET",
        url: "/shijtswy/version/client_release_ios.dis",
    });
    assert.equal(disabledIos.body, ANDROID_VERSION_DATA);
    await disabledApp.close();
}

async function testLeitingRoutes() {
    const app = Fastify();
    const ios = {
        enabled: true,
        apiHost: "175.178.160.158",
        apiScheme: "http",
    };
    await app.register(iosLeitingPlugin, { ios });

    const login = await app.inject({ method: "POST", url: "/sdk/v3-3/check_login.do" });
    assert.equal(login.statusCode, 200);
    assert.equal(login.json().status, "0");
    assert.ok(login.json().data.length > 100);

    const bootstrap = await app.inject({
        method: "GET",
        url: "/wf/210009_config_20200415.json",
    });
    assert.deepEqual(bootstrap.json(), {
        default: { apiPath: "175.178.160.158", apiScheme: "http" },
    });

    const telemetry = await app.inject({
        method: "GET",
        url: "/api/mg_log!addMgLoginLog.action",
    });
    assert.equal(telemetry.statusCode, 200);
    assert.deepEqual(telemetry.json(), { code: 0, message: "success" });
    await app.close();
}

async function main() {
    await testConfig();
    await testVersionSplit();
    await testLeitingRoutes();
    console.log("iOS compatibility tests passed");
}

main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
