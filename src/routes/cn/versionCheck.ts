import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { IosCompatConfig } from "../../lib/ios-compat";

const CN_API_HOST = "shijtswygamegf.leiting.com";

export interface VersionCheckPluginOptions {
    readonly ios?: IosCompatConfig;
}

const versionDataAndroid = [
    "// 用于官服正式用",
    JSON.stringify({
        "default": {
            "apiPath": CN_API_HOST,
        },
    })
].join("\r\n");

const routes = async (fastify: FastifyInstance, options: VersionCheckPluginOptions = {}) => {
    const versionDataIos = options.ios?.enabled === true
        ? [
            "// 用于官服正式用",
            JSON.stringify({
                "default": {
                    "apiPath": options.ios.apiHost,
                    "apiScheme": options.ios.apiScheme,
                },
            }),
        ].join("\r\n")
        : versionDataAndroid;

    fastify.get("/shijtswy/version/client_release_android.dis",
        async (_request: FastifyRequest, reply: FastifyReply) => {
        reply.header("content-type", "text/plain; charset=utf-8");
        reply.status(200).send(versionDataAndroid);
    });

    fastify.get("/shijtswy/version/client_release_ios.dis",
        async (_request: FastifyRequest, reply: FastifyReply) => {
        reply.header("content-type", "text/plain; charset=utf-8");
        reply.status(200).send(versionDataIos);
    });
};

export default routes;
