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
exports.ENTITY_LISTS_DIR = exports.CDN_TOTAL_SIZE = exports.getAssetDownloadSize = exports.reportPatchChainIntegrity = exports.checkPatchChainIntegrity = exports.compareDiffArchiveNames = exports.parseDiffArchiveName = exports.getVersionInfo = exports.getDiffArchiveSubdirs = exports.getFullArchiveSubdirs = exports.getEntityListName = exports.isIosAssetDevice = exports.isSupportedAssetDevice = exports.DIFF_ARCHIVE_SUBDIRS = exports.FULL_ARCHIVE_SUBDIRS = exports.getAssetArchiveMetadata = exports.invalidateAssetArchiveCatalog = exports.joinCdnPath = exports.normalizeCdnBaseUrl = void 0;
const file_exists_1 = require("../../lib/file-exists");
const utils_1 = require("../../utils");
const path_1 = __importDefault(require("path"));
const zip_summary_cache_1 = require("../../lib/zip-summary-cache");
const version_1 = require("../../lib/version");
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
    if ((0, file_exists_1.existsSync)(path_1.default.join(cdnDir, "EntityLists")))
        return "EntityLists";
    if ((0, file_exists_1.existsSync)(path_1.default.join(cdnDir, "entities")))
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
/**
 * Return the archive names explicitly published by enabled manifest entries.
 *
 * The active directory also contains held local-test and superseded archives.
 * Scanning that directory as the source of truth can make a clean client
 * download multiple archives for the same version edge; whichever archive is
 * applied last then wins for overlapping resources.  The manifest is the
 * release boundary, while the directory is only the storage location.
 */
function getEnabledPatchArchiveNames() {
    var _a;
    const names = new Set();
    const manifest = (0, version_1.getPatchManifest)();
    for (const patch of (_a = manifest.patches) !== null && _a !== void 0 ? _a : []) {
        if (patch.type !== "patch" || patch.enabled !== true)
            continue;
        const archives = Array.isArray(patch.chain)
            ? patch.chain
            : [patch.archive];
        for (const archive of archives) {
            if (typeof archive === "string" && archive.length > 0)
                names.add(archive);
        }
    }
    return names;
}
const ACTIVE_PATCH_DIR = path_1.default.join(__dirname, "..", "..", "..", "assets", "asset-patch", "active");
/** Parses `pinball-<from>-<to>-<seq>-<name>.zip`; returns null for other names. */
function parseDiffArchiveName(filename) {
    const match = filename.match(/pinball-(\d+\.\d+\.\d+)-(\d+\.\d+\.\d+)-(\d+)-/);
    if (!match)
        return null;
    return { from: match[1], to: match[2], seq: Number.parseInt(match[3], 10) };
}
exports.parseDiffArchiveName = parseDiffArchiveName;
/** Numeric (from, to, seq) order; the file name only breaks exact ties. */
function compareDiffArchiveNames(a, b) {
    const ka = parseDiffArchiveName(a), kb = parseDiffArchiveName(b);
    if (ka && kb) {
        const order = compareVersion(ka.from, kb.from)
            || compareVersion(ka.to, kb.to)
            || ka.seq - kb.seq;
        if (order !== 0)
            return order;
    }
    else if (ka || kb) {
        return ka ? -1 : 1;
    }
    return a < b ? -1 : a > b ? 1 : 0;
}
exports.compareDiffArchiveNames = compareDiffArchiveNames;
/**
 * The client concatenates each version group's `archive` array in the order
 * returned here and hands the flat list to its downloader, so archives of one
 * version edge must follow their numeric sequence. Directory listing order is
 * platform dependent and sorts "10" before "2", so it is never relied on.
 */
function sortDiffArchives(archives) {
    const entries = [];
    for (const archive of archives) {
        const key = parseDiffArchiveName(archive.filename);
        if (key)
            entries.push({ archive, key });
    }
    return entries.sort((a, b) => compareDiffArchiveNames(a.archive.filename, b.archive.filename));
}
/**
 * Reports publication problems in the enabled patch chain: duplicate
 * (from, to, seq) triples, sequence gaps inside one edge, conflicting or
 * non-contiguous version edges, and listed archives missing from disk.
 * Returns readable warnings; an empty array means the chain is clean.
 */
function checkPatchChainIntegrity(publishedNames, filesOnDisk) {
    var _a, _b, _c;
    const warnings = [];
    const onDisk = new Set(filesOnDisk);
    const triples = new Map();
    const edges = new Map();
    const fromByTarget = new Map();
    for (const name of publishedNames) {
        if (!onDisk.has(name))
            warnings.push(`listed archive missing from active directory: ${name}`);
        const key = parseDiffArchiveName(name);
        if (!key) {
            warnings.push(`listed archive name has no (from,to,seq) prefix: ${name}`);
            continue;
        }
        const triple = `${key.from}->${key.to}#${key.seq}`;
        triples.set(triple, [...((_a = triples.get(triple)) !== null && _a !== void 0 ? _a : []), name]);
        const edgeId = `${key.from}->${key.to}`;
        const edge = (_b = edges.get(edgeId)) !== null && _b !== void 0 ? _b : { from: key.from, to: key.to, seqs: [] };
        edge.seqs.push(key.seq);
        edges.set(edgeId, edge);
        const froms = (_c = fromByTarget.get(key.to)) !== null && _c !== void 0 ? _c : new Set();
        froms.add(key.from);
        fromByTarget.set(key.to, froms);
    }
    for (const [triple, names] of triples) {
        if (names.length > 1)
            warnings.push(`duplicate (from,to,seq) ${triple}: ${[...names].sort().join(", ")}`);
    }
    for (const [to, froms] of fromByTarget) {
        if (froms.size > 1) {
            warnings.push(`version ${to} is reached from several versions: ${[...froms].sort(compareVersion).join(", ")}`);
        }
    }
    const ordered = [...edges.values()]
        .sort((a, b) => compareVersion(a.from, b.from) || compareVersion(a.to, b.to));
    for (const edge of ordered) {
        const seqs = [...new Set(edge.seqs)].sort((a, b) => a - b);
        const expected = seqs.map((_, index) => index + 1);
        if (seqs.join(",") !== expected.join(",")) {
            warnings.push(`sequence gap in ${edge.from}->${edge.to}: found [${seqs.join(",")}], expected [${expected.join(",")}]`);
        }
    }
    for (let i = 1; i < ordered.length; i++) {
        const previous = ordered[i - 1], current = ordered[i];
        if (previous.to === current.to)
            continue;
        if (current.from !== previous.to) {
            warnings.push(`chain gap: ${previous.from}->${previous.to} is followed by ${current.from}->${current.to}`);
        }
    }
    return warnings;
}
exports.checkPatchChainIntegrity = checkPatchChainIntegrity;
/** Startup self-check: logs a malformed patch chain, never blocks startup. */
function reportPatchChainIntegrity() {
    let warnings;
    try {
        const filesOnDisk = (0, file_exists_1.existsSync)(ACTIVE_PATCH_DIR)
            ? getAssetArchiveMetadata(ACTIVE_PATCH_DIR).map(archive => archive.filename)
            : [];
        warnings = checkPatchChainIntegrity(getEnabledPatchArchiveNames(), filesOnDisk);
    }
    catch (e) {
        warnings = [`self-check could not run: ${e.message}`];
    }
    for (const warning of warnings)
        console.warn(`[PATCH] chain self-check: ${warning}`);
    return warnings;
}
exports.reportPatchChainIntegrity = reportPatchChainIntegrity;
function buildDiffList(baseUrl, cdnDir, clientVersion, targetVersion, device) {
    const groups = new Map();
    // CDN diff archives
    for (const subdir of getDiffArchiveSubdirs(device)) {
        const dir = path_1.default.join(cdnDir, subdir);
        try {
            for (const { archive, key } of sortDiffArchives(getAssetArchiveMetadata(dir))) {
                if (!groups.has(key.to))
                    groups.set(key.to, { original_version: key.from, archive: [] });
                groups.get(key.to).archive.push({ location: joinCdnPath(baseUrl, subdir, archive.filename), size: archive.size, sha256: "" });
            }
        }
        catch (e) {
            console.error(`[CDN] buildDiffList failed for ${subdir}:`, e.message);
        }
    }
    // Asset patch archives (active patches only)
    const publishedArchives = getEnabledPatchArchiveNames();
    try {
        const published = getAssetArchiveMetadata(ACTIVE_PATCH_DIR)
            .filter(archive => publishedArchives.has(archive.filename));
        for (const { archive, key } of sortDiffArchives(published)) {
            if (!groups.has(key.to))
                groups.set(key.to, { original_version: key.from, archive: [] });
            groups.get(key.to).archive.push({ location: joinCdnPath(baseUrl, "asset-patch", "active", archive.filename), size: archive.size, sha256: "" });
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
// 启动时检查一次补丁链，只告警不阻断启动
reportPatchChainIntegrity();
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
        return reply.status(200).send({
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
        // Empty objects/arrays become Option.Some in AIR and open a 0 MB dialog.
        // Only acknowledge an already-current client with no archive tasks.
        // Keep initial downloads and real (even tiny) archives on the download path.
        const noUpdate = !first && resVer === targetVersion
            && fullArchives.length === 0 && diffArchives.length === 0;
        reply.type("application/json");
        return reply.status(200).send({
            data_headers: (0, utils_1.generateDataHeaders)({ asset_update: !noUpdate }),
            data: {
                info: {
                    client_asset_version: resVer !== null && resVer !== void 0 ? resVer : "",
                    target_asset_version: targetVersion,
                    eventual_target_asset_version: targetVersion,
                    is_initial: first,
                    latest_maj_first_version: "1.4.0"
                },
                full: noUpdate ? null : {
                    version: fullVersion,
                    archive: fullArchives
                },
                diff: noUpdate ? null : diffArchives,
                asset_version_hash: ""
            }
        });
    }));
});
exports.default = routes;
exports.CDN_TOTAL_SIZE = TOTAL_SIZE;
exports.ENTITY_LISTS_DIR = entityListsDirName();
