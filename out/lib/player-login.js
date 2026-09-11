"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.resetPlayerLoginPassword = exports.bindPlayerLogin = exports.previewPlayerClaim = exports.previewLocalPlayerClaim = exports.createPlayerLoginCode = exports.logoutPlayer = exports.resumePlayerLogin = exports.loginPlayer = exports.registerPlayerLogin = exports.finishPlayerLoginSwitch = exports.playerLoginAdminOverview = exports.playerLoginProfile = exports.playerSocketAllowed = exports.readPlayerLoginAccess = exports.readPlayerLoginSession = exports.playerAccountByViewer = exports.playerLoginManaged = exports.maintainPlayerLogin = exports.initializePlayerLogin = exports.PlayerLoginError = exports.disconnectDeletedPlayerLogin = exports.rememberVerifiedPlayerLogin = exports.verifiedPlayerLogin = void 0;
const node_crypto_1 = require("node:crypto");
const db_1 = require("../data/db");
const account_1 = require("../data/domains/account");
const player_1 = require("../data/domains/player");
const session_1 = require("../data/domains/session");
const activeAccount_1 = require("../data/activeAccount");
const stamina_1 = require("./stamina");
const utils_1 = require("../utils");
const DAY = 86400000;
let initialized = false;
let nextMaintenanceAt = 0;
const statements = new Map();
function sql(query) {
    let statement = statements.get(query);
    if (!statement) {
        statement = (0, db_1.getDb)().prepare(query);
        statements.set(query, statement);
    }
    return statement;
}
const verifiedRequests = new WeakMap();
function verifiedPlayerLogin(request) { return verifiedRequests.get(request); }
exports.verifiedPlayerLogin = verifiedPlayerLogin;
function rememberVerifiedPlayerLogin(request, session) { verifiedRequests.set(request, session); }
exports.rememberVerifiedPlayerLogin = rememberVerifiedPlayerLogin;
let disconnectViewer = () => { };
/** Close existing transports after an administrator has deleted the account. */
function disconnectDeletedPlayerLogin(viewerId) { disconnectViewer(viewerId); }
exports.disconnectDeletedPlayerLogin = disconnectDeletedPlayerLogin;
class PlayerLoginError extends Error {
    constructor(message, code = "INVALID_INPUT") {
        super(message);
        this.code = code;
    }
}
exports.PlayerLoginError = PlayerLoginError;
function initializePlayerLogin(disconnect) {
    (0, db_1.getDb)().exec(`
        CREATE TABLE IF NOT EXISTS player_login_credentials (
            account_id INTEGER PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
            password TEXT NOT NULL, created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS player_login_sessions (
            token TEXT PRIMARY KEY, account_id INTEGER NOT NULL UNIQUE REFERENCES accounts(id) ON DELETE CASCADE,
            viewer_id INTEGER NOT NULL, udid TEXT NOT NULL, expires_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS player_login_codes (
            code TEXT PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            purpose TEXT NOT NULL, expires_at INTEGER NOT NULL, consumed_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS player_login_claims (
            proof TEXT PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            source TEXT NOT NULL, original_value TEXT NOT NULL, expires_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS player_login_audit (
            id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, action TEXT NOT NULL, occurred_at INTEGER NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_player_login_username
            ON accounts(lower(username)) WHERE username IS NOT NULL AND username <> '';
        CREATE INDEX IF NOT EXISTS idx_player_login_session_expiry ON player_login_sessions(expires_at);
        CREATE INDEX IF NOT EXISTS idx_player_login_claim_expiry ON player_login_claims(expires_at);
        CREATE INDEX IF NOT EXISTS idx_player_login_code_expiry ON player_login_codes(expires_at);
        CREATE INDEX IF NOT EXISTS idx_player_login_code_consumed ON player_login_codes(consumed_at) WHERE consumed_at IS NOT NULL;
    `);
    initialized = true;
    if (disconnect)
        disconnectViewer = disconnect;
}
exports.initializePlayerLogin = initializePlayerLogin;
function fail(message, code = "INVALID_INPUT") { throw new PlayerLoginError(message, code); }
function token() { return (0, node_crypto_1.randomBytes)(32).toString("hex"); }
function equal(left, right) {
    const a = Buffer.from(left), b = Buffer.from(right);
    return a.length === b.length && (0, node_crypto_1.timingSafeEqual)(a, b);
}
function identity(accountId) {
    return (0, db_1.getDb)().prepare(`SELECT a.id,a.status,a.username,a.takeover_password,c.password
        FROM accounts a LEFT JOIN player_login_credentials c ON c.account_id=a.id WHERE a.id=?`).get(accountId);
}
function active(accountId) {
    const row = identity(accountId);
    if (!row || row.status !== "normal")
        fail("该账号当前无法登录，请联系管理员。");
    return row;
}
function audit(accountId, action) {
    const inserted = sql("INSERT INTO player_login_audit(account_id,action,occurred_at) VALUES(?,?,?)").run(accountId, action, Date.now());
    // One indexed row in steady state; also drains an older backlog in bounded batches.
    sql("DELETE FROM player_login_audit WHERE id IN (SELECT id FROM player_login_audit WHERE id<=? ORDER BY id LIMIT 100)").run(Number(inserted.lastInsertRowid) - 5000);
    maintainPlayerLogin();
}
/** Opportunistic, bounded cleanup; expiration is always enforced by reads, regardless of cleanup timing. */
function maintainPlayerLogin() {
    const now = Date.now();
    if (now < nextMaintenanceAt)
        return;
    nextMaintenanceAt = now + 60000;
    for (const table of ["player_login_claims", "player_login_codes", "player_login_sessions"]) {
        sql(`DELETE FROM ${table} WHERE rowid IN (SELECT rowid FROM ${table} WHERE expires_at <= ? ORDER BY expires_at LIMIT 100)`).run(now);
    }
    sql("DELETE FROM player_login_codes WHERE rowid IN (SELECT rowid FROM player_login_codes WHERE consumed_at IS NOT NULL ORDER BY consumed_at LIMIT 100)").run();
}
exports.maintainPlayerLogin = maintainPlayerLogin;
function input(username, password) {
    if (typeof username !== "string" || !/^[A-Za-z0-9_]{4,24}$/.test(username))
        fail("账号需为 4–24 位字母、数字或下划线。");
    if (typeof password !== "string" || password.length < 6 || password.length > 64 || /[\x00-\x1f]/.test(password))
        fail("密码需为 6–64 位字符。");
    return { username: username.toLowerCase(), password };
}
function setCredentials(accountId, username, password) {
    const value = input(username, password);
    if ((0, db_1.getDb)().prepare("SELECT 1 FROM accounts WHERE lower(username)=? AND id<>?").get(value.username, accountId))
        fail("这个账号名已被使用，请换一个。");
    if ((0, db_1.getDb)().prepare("SELECT 1 FROM player_login_credentials WHERE account_id=?").get(accountId))
        fail("该存档已经绑定账号，请使用账号登录。");
    // Plaintext player passwords are an explicit project requirement. Never return or log this column.
    (0, db_1.getDb)().prepare("INSERT INTO player_login_credentials(account_id,password,created_at) VALUES(?,?,?)").run(accountId, value.password, Date.now());
    (0, account_1.updateAccountSync)({ id: accountId, username: value.username });
}
function playerLoginManaged(accountId) {
    return initialized && Boolean(sql("SELECT 1 FROM player_login_credentials WHERE account_id=?").get(accountId));
}
exports.playerLoginManaged = playerLoginManaged;
function playerAccountByViewer(viewer) {
    var _a;
    if (!/^\d{1,15}$/.test(String(viewer !== null && viewer !== void 0 ? viewer : "")))
        return null;
    const row = sql("SELECT account_id FROM sessions WHERE token=? AND type=2").get(String(viewer));
    return (_a = row === null || row === void 0 ? void 0 : row.account_id) !== null && _a !== void 0 ? _a : null;
}
exports.playerAccountByViewer = playerAccountByViewer;
function readPlayerLoginSession(value) {
    var _a;
    if (!initialized || typeof value !== "string" || !/^[a-f0-9]{64}$/.test(value))
        return null;
    return (_a = sql(`SELECT s.* FROM player_login_sessions s JOIN accounts a ON a.id=s.account_id
        WHERE s.token=? AND s.expires_at>? AND a.status='normal'`).get(value, Date.now())) !== null && _a !== void 0 ? _a : null;
}
exports.readPlayerLoginSession = readPlayerLoginSession;
/** One indexed query on the authenticated game hot path; no cross-request authorization cache. */
function readPlayerLoginAccess(value, viewer) {
    var _a;
    if (!initialized || typeof value !== "string" || !/^[a-f0-9]{64}$/.test(value))
        return null;
    const viewerKey = /^\d{1,15}$/.test(String(viewer !== null && viewer !== void 0 ? viewer : "")) ? String(viewer) : "";
    return (_a = sql(`SELECT s.*,v.account_id AS request_account_id
        FROM player_login_sessions s JOIN accounts a ON a.id=s.account_id
        LEFT JOIN sessions v ON v.token=? AND v.type=2
        WHERE s.token=? AND s.expires_at>? AND a.status='normal'`).get(viewerKey, value, Date.now())) !== null && _a !== void 0 ? _a : null;
}
exports.readPlayerLoginAccess = readPlayerLoginAccess;
function playerSocketAllowed(viewer, value) {
    var _a;
    const accountId = playerAccountByViewer(viewer);
    if (!accountId || !playerLoginManaged(accountId))
        return true;
    return ((_a = readPlayerLoginSession(value)) === null || _a === void 0 ? void 0 : _a.account_id) === accountId;
}
exports.playerSocketAllowed = playerSocketAllowed;
function playerLoginProfile(accountId) {
    const acc = active(accountId);
    const playerId = (0, activeAccount_1.resolvePlayerIdSync)(accountId);
    const player = playerId ? sql("SELECT name,rank_point,leader_character_id FROM players WHERE id=?").get(playerId) : null;
    if (!player)
        fail("没有找到该账号的存档，请联系管理员。");
    return { username: acc.username, viewer_id: (0, session_1.getViewerIdSync)(accountId), name: player.name,
        rank: (0, stamina_1.getRankDegree)(player.rank_point), leader_character_id: player.leader_character_id };
}
exports.playerLoginProfile = playerLoginProfile;
function playerLoginAdminOverview() {
    if (!initialized)
        return new Map();
    const rows = sql(`SELECT c.account_id,c.created_at,s.expires_at FROM player_login_credentials c
        JOIN accounts a ON a.id=c.account_id LEFT JOIN player_login_sessions s
        ON s.account_id=c.account_id AND s.expires_at>? AND a.status='normal'`).all(Date.now());
    return new Map(rows.map(row => [row.account_id, { bound: true, boundAt: row.created_at, sessionExpiresAt: row.expires_at }]));
}
exports.playerLoginAdminOverview = playerLoginAdminOverview;
/** Switching disconnects previous transports, while keeping other saved accounts' credentials valid. */
function finishPlayerLoginSwitch(previous, next) {
    const old = readPlayerLoginSession(previous);
    if (old && old.viewer_id !== next.profile.viewer_id)
        disconnectViewer(old.viewer_id);
}
exports.finishPlayerLoginSwitch = finishPlayerLoginSwitch;
function issue(accountId, remember) {
    active(accountId);
    const result = { token: token(), account_id: accountId, viewer_id: (0, session_1.getViewerIdSync)(accountId),
        udid: token().slice(0, 32), expires_at: Date.now() + (remember ? 30 * DAY : DAY / 2) };
    if (!result.viewer_id)
        fail("存档缺少玩家序号，请联系管理员。");
    (0, db_1.getDb)().prepare("DELETE FROM player_login_sessions WHERE account_id=?").run(accountId);
    (0, db_1.getDb)().prepare("INSERT INTO player_login_sessions(token,account_id,viewer_id,udid,expires_at) VALUES(@token,@account_id,@viewer_id,@udid,@expires_at)").run(result);
    (0, account_1.updateAccountSync)({ id: accountId, takeoverUdid: result.udid, lastLoginTime: new Date() });
    audit(accountId, "login");
    return result;
}
function result(session) {
    disconnectViewer(session.viewer_id);
    return { token: session.token, udid: session.udid, expires_at: session.expires_at, profile: playerLoginProfile(session.account_id) };
}
function registerPlayerLogin(username, password, remember) {
    input(username, password);
    let newPlayerId = 0;
    const session = (0, db_1.getDb)().transaction(() => {
        const account = (0, account_1.insertAccountSync)({ appId: "wf_cn", idpAlias: "", idpCode: "leiting", idpId: "", status: "normal" });
        setCredentials(account.id, username, password);
        const player = (0, player_1.insertDefaultPlayerSync)(account.id);
        newPlayerId = player.id;
        let viewer = (0, utils_1.generateViewerId)();
        while ((0, db_1.getDb)().prepare("SELECT 1 FROM sessions WHERE token=?").get(String(viewer)))
            viewer = (0, utils_1.generateViewerId)();
        (0, db_1.getDb)().prepare("INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)").run(String(viewer), account.id, new Date(Date.now() + 365 * DAY).toISOString());
        return issue(account.id, remember);
    }).immediate();
    (0, activeAccount_1.saveAccountDefaultPlayer)(session.account_id, newPlayerId);
    return result(session);
}
exports.registerPlayerLogin = registerPlayerLogin;
function loginPlayer(username, password, remember) {
    const value = input(username, password);
    const session = (0, db_1.getDb)().transaction(() => {
        const row = (0, db_1.getDb)().prepare(`SELECT a.id,c.password FROM accounts a JOIN player_login_credentials c ON c.account_id=a.id
            WHERE lower(a.username)=? AND a.username IS NOT NULL AND a.username<>''`).get(value.username);
        if (!row || !equal(row.password, value.password))
            fail("账号或密码不正确。");
        return issue(row.id, remember);
    }).immediate();
    return result(session);
}
exports.loginPlayer = loginPlayer;
function resumePlayerLogin(value) {
    const session = readPlayerLoginSession(value);
    if (!session)
        fail("登录已过期或已在其他设备登录，请重新登录。", "SESSION_INVALID");
    return { token: session.token, udid: session.udid, expires_at: session.expires_at, profile: playerLoginProfile(session.account_id) };
}
exports.resumePlayerLogin = resumePlayerLogin;
function logoutPlayer(value) {
    const session = readPlayerLoginSession(value);
    if (!session)
        return;
    (0, db_1.getDb)().prepare("DELETE FROM player_login_sessions WHERE token=?").run(session.token);
    disconnectViewer(session.viewer_id);
    audit(session.account_id, "logout");
}
exports.logoutPlayer = logoutPlayer;
function createPlayerLoginCode(viewer, purpose) {
    if (purpose !== "bind" && purpose !== "reset")
        fail("绑定码用途无效。");
    const accountId = playerAccountByViewer(viewer);
    if (!accountId)
        fail("没有找到这个玩家序号。");
    active(accountId);
    if (playerLoginManaged(accountId) !== (purpose === "reset"))
        fail(purpose === "bind" ? "该存档已经绑定账号。" : "该存档尚未绑定账号。");
    const code = (0, node_crypto_1.randomBytes)(12).toString("hex").toUpperCase();
    const expiresAt = Date.now() + 15 * 60000;
    (0, db_1.getDb)().transaction(() => {
        (0, db_1.getDb)().prepare("DELETE FROM player_login_codes WHERE account_id=? AND purpose=?").run(accountId, purpose);
        (0, db_1.getDb)().prepare("INSERT INTO player_login_codes(code,account_id,purpose,expires_at) VALUES(?,?,?,?)").run(code, accountId, purpose, expiresAt);
        audit(accountId, `admin_${purpose}_code`);
    }).immediate();
    return { code, expires_at: expiresAt, profile: playerLoginProfile(accountId) };
}
exports.createPlayerLoginCode = createPlayerLoginCode;
function readCode(value, purpose) {
    const code = typeof value === "string" ? value.replace(/[\s-]/g, "").toUpperCase() : "";
    const row = (0, db_1.getDb)().prepare("SELECT * FROM player_login_codes WHERE code=? AND purpose=? AND consumed_at IS NULL AND expires_at>?").get(code, purpose, Date.now());
    if (!row)
        fail("该验证码无效、已使用或已过期。");
    active(row.account_id);
    return row;
}
function localSaveEvidence(body) {
    var _a;
    const viewer = String((_a = body.viewer_id) !== null && _a !== void 0 ? _a : "");
    const device = typeof body.device_id === "number" || typeof body.device_id === "string" ? Number(body.device_id) : 0;
    if (!/^[1-9]\d{0,14}$/.test(viewer))
        return null;
    return { viewer_id: viewer, device_id: Number.isSafeInteger(device) && device > 0 ? device : 0,
        udid: typeof body.udid === "string" && body.udid.length <= 128 ? body.udid : "" };
}
function localSaveMatch(evidence) {
    // Both lookups use primary keys. UID alone is never sufficient to claim a save.
    const row = sql(`SELECT a.id,a.status,a.takeover_udid,c.account_id AS bound_id,d.device_id
        FROM sessions v JOIN accounts a ON a.id=v.account_id
        LEFT JOIN player_login_credentials c ON c.account_id=a.id
        LEFT JOIN device_bindings d ON d.device_id=? AND d.account_id=a.id
        WHERE v.token=? AND v.type=2`).get(evidence.device_id, evidence.viewer_id);
    if (!row || row.status !== "normal")
        return null;
    if (row.bound_id)
        return { accountId: row.id, source: "bound" };
    // Once a transfer has installed a valid UDID, an old device binding cannot override it.
    if (row.takeover_udid && row.takeover_udid !== "unknown") {
        return evidence.udid.length >= 16 && equal(row.takeover_udid, evidence.udid)
            ? { accountId: row.id, source: "local_udid" } : null;
    }
    return row.device_id ? { accountId: row.id, source: "local_device" } : null;
}
/** First-upgrade discovery only; does not sign up, change device bindings or load a full save. */
function previewLocalPlayerClaim(body) {
    const evidence = localSaveEvidence(body);
    return (0, db_1.getDb)().transaction(() => {
        const match = evidence && localSaveMatch(evidence);
        if (!match)
            return { status: "manual_required" };
        // Do not reveal an existing username or profile from public UID input.
        if (match.source === "bound")
            return { status: "login_required" };
        const proof = token();
        (0, db_1.getDb)().prepare("INSERT INTO player_login_claims(proof,account_id,source,original_value,expires_at) VALUES(?,?,?,?,?)")
            .run(proof, match.accountId, match.source, JSON.stringify(evidence), Date.now() + 5 * 60000);
        audit(match.accountId, "local_claim_preview");
        return { status: "claimable", proof, profile: playerLoginProfile(match.accountId) };
    }).immediate();
}
exports.previewLocalPlayerClaim = previewLocalPlayerClaim;
function previewPlayerClaim(body) {
    return (0, db_1.getDb)().transaction(() => {
        let accountId, source, original;
        if (body.code) {
            const row = readCode(body.code, "bind");
            accountId = row.account_id;
            source = "code";
            original = row.code;
        }
        else {
            const id = playerAccountByViewer(body.viewer_id);
            const row = id ? identity(id) : undefined;
            if (!row || typeof body.inherit_password !== "string" || !row.takeover_password || !equal(row.takeover_password, body.inherit_password))
                fail("玩家序号或引继密码不正确。");
            active(row.id);
            accountId = row.id;
            source = "inherit";
            original = row.takeover_password;
        }
        if (playerLoginManaged(accountId))
            fail("该存档已经绑定账号，请使用账号登录。");
        const proof = token();
        (0, db_1.getDb)().prepare("INSERT INTO player_login_claims(proof,account_id,source,original_value,expires_at) VALUES(?,?,?,?,?)").run(proof, accountId, source, original, Date.now() + 5 * 60000);
        audit(accountId, "claim_preview");
        return { proof, profile: playerLoginProfile(accountId) };
    }).immediate();
}
exports.previewPlayerClaim = previewPlayerClaim;
function bindPlayerLogin(proof, username, password, remember) {
    input(username, password);
    const session = (0, db_1.getDb)().transaction(() => {
        const row = (0, db_1.getDb)().prepare("SELECT * FROM player_login_claims WHERE proof=? AND expires_at>?").get(typeof proof === "string" ? proof : "", Date.now());
        if (!row)
            fail("存档验证已过期，请重新验证。");
        const acc = active(row.account_id);
        if (playerLoginManaged(row.account_id))
            fail("该存档已经绑定账号，请使用账号登录。");
        if (row.source === "code") {
            readCode(row.original_value, "bind");
            (0, db_1.getDb)().prepare("UPDATE player_login_codes SET consumed_at=? WHERE code=?").run(Date.now(), row.original_value);
        }
        else if (row.source === "inherit") {
            if (!acc.takeover_password || !equal(acc.takeover_password, row.original_value))
                fail("引继密码已变化，请重新验证。");
        }
        else if (row.source === "local_device" || row.source === "local_udid") {
            const evidence = localSaveEvidence(JSON.parse(row.original_value));
            const match = evidence && localSaveMatch(evidence);
            if (!match || match.accountId !== row.account_id || match.source !== row.source)
                fail("原账号信息已变化，请重新验证存档。");
        }
        else
            fail("存档验证方式无效，请重新验证。");
        setCredentials(row.account_id, username, password);
        (0, db_1.getDb)().prepare("DELETE FROM player_login_claims WHERE account_id=?").run(row.account_id);
        audit(row.account_id, "bind_existing_save");
        return issue(row.account_id, remember);
    }).immediate();
    return result(session);
}
exports.bindPlayerLogin = bindPlayerLogin;
function resetPlayerLoginPassword(code, password) {
    input("validation", password);
    const accountId = (0, db_1.getDb)().transaction(() => {
        const row = readCode(code, "reset");
        if (!playerLoginManaged(row.account_id))
            fail("该存档尚未绑定账号。");
        (0, db_1.getDb)().prepare("UPDATE player_login_credentials SET password=? WHERE account_id=?").run(password, row.account_id);
        (0, db_1.getDb)().prepare("DELETE FROM player_login_sessions WHERE account_id=?").run(row.account_id);
        (0, db_1.getDb)().prepare("UPDATE player_login_codes SET consumed_at=? WHERE code=?").run(Date.now(), row.code);
        audit(row.account_id, "reset_password");
        return row.account_id;
    }).immediate();
    disconnectViewer((0, session_1.getViewerIdSync)(accountId));
    return { username: active(accountId).username };
}
exports.resetPlayerLoginPassword = resetPlayerLoginPassword;
