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
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.installCustomCdnResourceRoutes = void 0;
const fs_1 = require("fs");
const path_1 = __importDefault(require("path"));
/** Serve loose custom resources in all native roots, then the pristine store. */
function installCustomCdnResourceRoutes(app, options) {
    for (const root of ["upload", "medium_upload", "android_upload", "ios_upload"]) {
        app.get(`/patch/cn/dummy/download/production/${root}/:prefix/:hash`, (request, reply) => __awaiter(this, void 0, void 0, function* () {
            const { prefix, hash } = request.params;
            if (!/^[a-f0-9]{2}$/.test(prefix) || !/^[a-f0-9]{38}$/.test(hash)) {
                return reply.status(404).send("Not Found");
            }
            const custom = path_1.default.join(options.patchRoot, "production", root, prefix, hash);
            const pristine = path_1.default.join(options.cdnRoot, "cn", "dummy", "download", "production", root, prefix, hash);
            const file = (0, fs_1.existsSync)(custom) ? custom : pristine;
            if ((0, fs_1.existsSync)(file)) {
                return reply.type("application/octet-stream").send((0, fs_1.readFileSync)(file));
            }
            return reply.status(404).send("Not Found");
        }));
    }
}
exports.installCustomCdnResourceRoutes = installCustomCdnResourceRoutes;
