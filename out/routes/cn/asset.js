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
exports.ENTITY_LISTS_DIR = exports.CDN_TOTAL_SIZE = exports.getAssetDownloadSize = exports.getVersionInfo = exports.getDiffArchiveSubdirs = exports.getFullArchiveSubdirs = exports.getEntityListName = exports.isIosAssetDevice = exports.isSupportedAssetDevice = exports.DIFF_ARCHIVE_SUBDIRS = exports.FULL_ARCHIVE_SUBDIRS = exports.getAssetArchiveMetadata = exports.invalidateAssetArchiveCatalog = exports.joinCdnPath = exports.normalizeCdnBaseUrl = void 0;
const utils_1 = require("../../utils");
const fs_1 = require("fs");
const path_1 = __importDefault(require("path"));
const zip_summary_cache_1 = require("../../lib/zip-summary-cache");
const CN_PORT = process.env.CN_LISTEN_PORT || "8001";
/** Validates the configured origin and removes trailing slashes before path joins. */
function normalizeCdnBaseUrl(value) {
    const trimmed = value.trim();
    let parsed;
    try {
        parsed = new URL(trimmed);
    }
    catch (_a) {
        throw new Error("CDN_BASE_URL must be an absolute HTTP(S) URL.");
    }
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
        throw new Error("CDN_BASE_URL must use HTTP or HTTPS.");
    }
    if (parsed.username || parsed.password || parsed.search || parsed.hash) {
        throw new Error("CDN_BASE_URL must not contain credentials, a query, or a fragment.");
    }
    return parsed.toString().replace(/\/+$/, "");
}
exports.normalizeCdnBaseUrl = normalizeCdnBaseUrl;
function joinCdnPath(baseUrl, ...segments) {
    const normalizedBase = baseUrl.replace(/\/+$/, "");
    const suffix = segments
        .map(segment => segment.replace(/^\/+|\/+$/g, ""))
        .filter(Boolean)
        .join("/");
    return suffix ? `${normalizedBase}/${suffix}` : normalizedBase;
}
exports.joinCdnPath = joinCdnPath;
const CDN_BASE = process.env.CDN_BASE_URL
    ? normalizeCdnBaseUrl(process.env.CDN_BASE_URL)
    : undefined;
/** Clears short-lived ZIP metadata after an in-process asset publication. */
function invalidateAssetArchiveCatalog(directory) {
    (0, zip_summary_cache_1.invalidateZipCache)(directory);
}
exports.invalidateAssetArchiveCatalog = invalidateAssetArchiveCatalog;
/** Reads ZIP names and sizes with a short TTL; response URLs are never cached. */
function getAssetArchiveMetadata(directory) {
    return (0, zip_summary_cache_1.getZipArchiveMetadata)(directory);
}
exports.getAssetArchiveMetadata = getAssetArchiveMetadata;
exports.FULL_ARCHIVE_SUBDIRS = [
    "archive-common-full",
    "archive-medium-full",
    "archive-android-full",
    "archive-ios-full",
];
exports.DIFF_ARCHIVE_SUBDIRS = [
    "archive-common-diff",
    "archive-medium-diff",
    "archive-android-diff",
    "archive-ios-diff",
];
/** Get CDN base URL from request Host header, fall back to CDN_BASE_URL env or default. */
function getCdnBase(request) {
    if (CDN_BASE)
        return CDN_BASE;
    const host = request.headers.host || `localhost:${CN_PORT}`;
    return normalizeCdnBaseUrl(`http://${host}/patch/cn`);
}
function headerValue(request, name) {
    const value = request.headers[name];
    return typeof value === "string" ? value : undefined;
}
/**
 * CN iOS clients use the same asset update chain as Android clients.
 * Numeric platform values are sent by some client builds (1 = iOS, 2 = Android).
 */
function isSupportedAssetDevice(device) {
    if (device === undefined)
        return true;
    const normalized = device.toLowerCase();
    return normalized === "1"
        || normalized === "2"
        || normalized === "android"
        || normalized === "ios";
}
exports.isSupportedAssetDevice = isSupportedAssetDevice;
function isIosAssetDevice(device) {
    const normalized = device === null || device === void 0 ? void 0 : device.toLowerCase();
    return normalized === "1" || normalized === "ios";
}
exports.isIosAssetDevice = isIosAssetDevice;
function getEntityListName(device) {
    return isIosAssetDevice(device)
        ? "10939-ios_medium.csv"
        : "10939-android_medium.csv";
}
exports.getEntityListName = getEntityListName;
function getFullArchiveSubdirs(device) {
    return [
        "archive-common-full",
        "archive-medium-full",
        isIosAssetDevice(device) ? "archive-ios-full" : "archive-android-full",
    ];
}
exports.getFullArchiveSubdirs = getFullArchiveSubdirs;
function getDiffArchiveSubdirs(device) {
    return [
        "archive-common-diff",
        "archive-medium-diff",
        isIosAssetDevice(device) ? "archive-ios-diff" : "archive-android-diff",
    ];
}
exports.getDiffArchiveSubdirs = getDiffArchiveSubdirs;
/** Detect CDN path-list dir name: `EntityLists` (cn_cdn) or `entities` (cn_cdn_new). */
function entityListsDirName() {
    if ((0, fs_1.existsSync)(path_1.default.join(cdnDir, "EntityLists")))
        return "EntityLists";
    if ((0, fs_1.existsSync)(path_1.default.join(cdnDir, "entities")))
        return "entities";
    return "EntityLists";
}
function getVersionInfo(baseUrl, totalSize, device) {
    const el = entityListsDirName();
    const entityBase = `${joinCdnPath(baseUrl, el, ...(el === "entities" ? ["files"] : []))}/`;
    return {
        base_url: entityBase,
        files_list: joinCdnPath(baseUrl, el, getEntityListName(device)),
        total_size: totalSize,
        delayed_assets_size: 0
    };
}
exports.getVersionInfo = getVersionInfo;
function buildArchiveList(baseUrl, cdnDir, subdir) {
    const dir = path_1.default.join(cdnDir, subdir);
    try {
        return getAssetArchiveMetadata(dir).map(archive => ({
            location: joinCdnPath(baseUrl, subdir, archive.filename),
            size: archive.size,
            sha256: ""
        }));
    }
    catch (e) {
        console.error(`[CDN] buildArchiveList failed for ${subdir}:`, e.message);
        return [];
    }
}
function parseVersion(v) {
    return v.split(".").map(Number);
}
function compareVersion(a, b) {
    const av = parseVersion(a), bv = parseVersion(b);
    for (let i = 0; i < 3; i++) {
        if (av[i] !== bv[i])
            return av[i] - bv[i];
    }
    return 0;
}
function buildDiffList(baseUrl, cdnDir, clientVersion, targetVersion, device) {
    const groups = new Map();
    // CDN diff archives
    for (const subdir of getDiffArchiveSubdirs(device)) {
        const dir = path_1.default.join(cdnDir, subdir);
        try {
            for (const archive of getAssetArchiveMetadata(dir)) {
                const f = archive.filename;
                const match = f.match(/pinball-(\d+\.\d+\.\d+)-(\d+\.\d+\.\d+)-\d+-/);
                if (match) {
                    const from = match[1];
                    const to = match[2];
                    if (!groups.has(to))
                        groups.set(to, { original_version: from, archive: [] });
                    groups.get(to).archive.push({ location: joinCdnPath(baseUrl, subdir, f), size: archive.size, sha256: "" });
                }
            }
        }
        catch (e) {
            console.error(`[CDN] buildDiffList failed for ${subdir}:`, e.message);
        }
    }
    // Asset patch archives (active patches only)
    const patchDir = path_1.default.join(__dirname, "..", "..", "..", "assets", "asset-patch", "active");
    try {
        for (const archive of getAssetArchiveMetadata(patchDir)) {
            const f = archive.filename;
            const match = f.match(/pinball-(\d+\.\d+\.\d+)-(\d+\.\d+\.\d+)-\d+-/);
            if (match) {
                const from = match[1];
                const to = match[2];
                if (!groups.has(to))
                    groups.set(to, { original_version: from, archive: [] });
                groups.get(to).archive.push({ location: joinCdnPath(baseUrl, "asset-patch", "active", f), size: archive.size, sha256: "" });
            }
        }
    }
    catch (e) {
        console.error(`[PATCH] buildDiffList failed for active patches:`, e.message);
    }
    return [...groups.entries()]
        // The client totals every returned archive for its confirmation
        // dialog. Do not expose unrelated historical update steps.
        .filter(([version]) => compareVersion(version, clientVersion) > 0
        && compareVersion(version, targetVersion) <= 0)
        .sort(([a], [b]) => compareVersion(a, b))
        .map(([version, data]) => ({ original_version: data.original_version, version, archive: data.archive }));
}
const envCdnDir = process.env.CDN_DIR || ".cdn";
const cdnDir = path_1.default.isAbsolute(envCdnDir) ? path_1.default.join(envCdnDir, "cn") : path_1.default.join(__dirname, "..", "..", "..", envCdnDir, "cn");
function sumArchiveSizes(archives) {
    return archives.reduce((total, archive) => total + archive.size, 0);
}
/** Calculate only the archives this client will actually download. */
function getAssetDownloadSize(resVer, device) {
    const { computeAssetTarget } = require("../../lib/version");
    const { targetVersion, isFirstTime: first, fullVersion } = computeAssetTarget(resVer);
    const fullArchives = first
        ? [
            ...getFullArchiveSubdirs(device).flatMap(subdir => buildArchiveList("", cdnDir, subdir)),
        ]
        : [];
    const diffBaseVersion = first ? fullVersion : (resVer !== null && resVer !== void 0 ? resVer : fullVersion);
    const diffArchives = buildDiffList("", cdnDir, diffBaseVersion, targetVersion, device)
        .flatMap(group => group.archive);
    return sumArchiveSizes(fullArchives) + sumArchiveSizes(diffArchives);
}
exports.getAssetDownloadSize = getAssetDownloadSize;
// 启动时扫描一次，动态计算总大小
const TOTAL_SIZE = (() => {
    let total = 0;
    for (const subdir of [...exports.FULL_ARCHIVE_SUBDIRS, ...exports.DIFF_ARCHIVE_SUBDIRS]) {
        try {
            for (const archive of getAssetArchiveMetadata(path_1.default.join(cdnDir, subdir))) {
                total += archive.size;
            }
        }
        catch (e) {
            console.error(`[CDN] TOTAL_SIZE failed for ${subdir}:`, e.message);
        }
    }
    return total;
})();
const routes = (fastify) => __awaiter(void 0, void 0, void 0, function* () {
    fastify.post("/version_info", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const baseUrl = getCdnBase(request);
        const resVer = request.headers['res_ver'];
        const device = headerValue(request, "device");
        reply.type("application/json");
        reply.status(200).send({
            data_headers: (0, utils_1.generateDataHeaders)(),
            data: getVersionInfo(baseUrl, getAssetDownloadSize(resVer, device), device)
        });
    }));
    fastify.post("/get_path", (request, reply) => __awaiter(void 0, void 0, void 0, function* () {
        const device = headerValue(request, "device");
        if (!isSupportedAssetDevice(device)) {
            return reply.status(400).type("application/json").send({
                code: "UNSUPPORTED_PLATFORM",
                message: `unsupported DEVICE header: ${device === null || device === void 0 ? void 0 : device.toLowerCase()}`
            });
        }
        const baseUrl = getCdnBase(request);
        const resVer = request.headers['res_ver'];
        const { computeAssetTarget } = require("../../lib/version");
        const { targetVersion, isFirstTime: first, fullVersion } = computeAssetTarget(resVer);
        const fullArchives = first
            ? [
                ...getFullArchiveSubdirs(device).flatMap(subdir => buildArchiveList(baseUrl, cdnDir, subdir)),
            ]
            : [];
        const diffBaseVersion = first ? fullVersion : (resVer !== null && resVer !== void 0 ? resVer : fullVersion);
        const diffArchives = buildDiffList(baseUrl, cdnDir, diffBaseVersion, targetVersion, device);
        reply.type("application/json");
        reply.status(200).send({
            data_headers: (0, utils_1.generateDataHeaders)({ asset_update: true }),
            data: {
                info: {
                    client_asset_version: resVer !== null && resVer !== void 0 ? resVer : "",
                    target_asset_version: targetVersion,
                    eventual_target_asset_version: targetVersion,
                    is_initial: first,
                    latest_maj_first_version: "1.4.0"
                },
                full: {
                    version: fullVersion,
                    archive: fullArchives
                },
                diff: diffArchives,
                asset_version_hash: ""
            }
        });
    }));
});
exports.default = routes;
exports.CDN_TOTAL_SIZE = TOTAL_SIZE;
exports.ENTITY_LISTS_DIR = entityListsDirName();
