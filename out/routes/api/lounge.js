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
exports.buildLoungeListData = void 0;
const session_1 = require("../../data/domains/session");
const utils_1 = require("../../utils");
function buildLoungeListData() {
    return {
        lounge_list: [],
    };
}
exports.buildLoungeListData = buildLoungeListData;
const routes = (fastify) => __awaiter(void 0, void 0, void 0, function* () {
    fastify.post("/get_list", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const body = request.body;
        const viewerId = Number(body === null || body === void 0 ? void 0 : body.viewer_id);
        if (!Number.isSafeInteger(viewerId) || viewerId <= 0) {
            return reply.status(400).send({
                error: "Bad Request",
                message: "Invalid request body.",
            });
        }
        const session = yield (0, session_1.getSession)(String(viewerId));
        if (!session) {
            return reply.status(400).send({
                error: "Bad Request",
                message: "Invalid viewer id.",
            });
        }
        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            data_headers: (0, utils_1.generateDataHeaders)({ viewer_id: viewerId }),
            data: buildLoungeListData(),
        });
    }));
});
exports.default = routes;
