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
const realtime_diagnostics_1 = require("../../lib/realtime-diagnostics");
/** Management-only runtime controls for bounded multiplayer diagnostics. */
const routes = (fastify) => __awaiter(void 0, void 0, void 0, function* () {
    fastify.get("/realtime", (_request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        return reply.status(200).send((0, realtime_diagnostics_1.getRealtimeDiagnostics)());
    }));
    fastify.post("/realtime", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        var _a;
        try {
            return reply.status(200).send((0, realtime_diagnostics_1.configureRealtimeDiagnostics)(((_a = request.body) !== null && _a !== void 0 ? _a : {})));
        }
        catch (error) {
            return reply.status(400).send({ error: error instanceof Error ? error.message : String(error) });
        }
    }));
});
exports.default = routes;
