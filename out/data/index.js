"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.initializeDatabase = void 0;
const better_sqlite3_1 = __importDefault(require("better-sqlite3"));
const fs_1 = require("fs");
const os_1 = require("os");
const path_1 = __importDefault(require("path"));
const wdfpData_1 = require("./updaters/wdfpData");
const wdfpData_2 = __importDefault(require("./initializers/wdfpData"));
const quest_time_revision_1 = require("./initializers/quest-time-revision");
const admin_account_cleanup_1 = require("../lib/admin-account-cleanup");
// Use __dirname so DB path is relative to the source file, not process.cwd()
const dataDir = process.env.DATA_DIR
    ? path_1.default.resolve(process.env.DATA_DIR)
    : path_1.default.resolve(__dirname, "../../.database");
const versionFileExtension = ".version";
if (!(0, fs_1.existsSync)(dataDir)) {
    // make the data directory since it doesn't exist
    try {
        (0, fs_1.mkdirSync)(dataDir);
    }
    catch (error) {
        throw new Error(`Failed to create the data directory. Reason: ${error.message}`);
    }
}
const databasesMetadata = {
    [0 /* Database.WDFP_DATA */]: {
        path: "/wdfp_data.db",
        init: wdfpData_2.default,
        updateBefore: wdfpData_1.updateBeforeInit,
        updateAfter: wdfpData_1.updateAfterInit,
        latestVersion: 9
    }
};
const loadedDatabases = {};
function getDatabase(database) {
    // don't try to load an already-loaded database
    const isLoaded = loadedDatabases[database];
    if (isLoaded)
        return isLoaded;
    // get metadata
    const metadata = databasesMetadata[database];
    const relativeDatabasePath = metadata.path;
    const absoluteDatabasePath = path_1.default.join(dataDir, relativeDatabasePath);
    // check if the db already exists
    const dbExists = (0, fs_1.existsSync)(absoluteDatabasePath);
    // get the database's version
    let currentVersion = 0;
    const versionFilePath = path_1.default.join(dataDir, `${relativeDatabasePath}${versionFileExtension}`);
    if (dbExists && (0, fs_1.existsSync)(versionFilePath)) {
        const fileContents = (0, fs_1.readFileSync)(versionFilePath).toString('utf-8');
        const versionNumber = Number(fileContents);
        currentVersion = isNaN(versionNumber) ? currentVersion : versionNumber;
    }
    // create new db
    const db = new better_sqlite3_1.default(absoluteDatabasePath);
    // set pragma
    // Keep temporary SQLite structures on disk. Windows launchers point the
    // process at a stable project-local directory instead of an RDP session
    // temp folder that can disappear while the server is still running.
    console.log(`[DB] temp_dir=${(0, os_1.tmpdir)()}`);
    db.pragma('temp_store = FILE');
    console.log(`[DB] temp_store=${db.pragma('temp_store', { simple: true })} (1=FILE)`);
    db.pragma('journal_mode = WAL');
    db.pragma('busy_timeout = 1000');
    db.pragma('foreign_keys = OFF');
    // call init & update function
    const init = metadata.init;
    const updateBefore = metadata.updateBefore;
    const updateAfter = metadata.updateAfter;
    if (init !== undefined) {
        try {
            // try to update before initialization
            const latestVersion = metadata.latestVersion;
            const updateRequired = dbExists && metadata.latestVersion > currentVersion;
            console.log(`[DB] init: dbExists=${dbExists} currentVersion=${currentVersion} latestVersion=${latestVersion} updateRequired=${updateRequired}`);
            if (updateRequired && updateBefore !== undefined) {
                console.log("Updating wdfp_data.db...");
                updateBefore(db, currentVersion);
            }
            // initialize
            console.log("[DB] calling init...");
            init(db, dbExists);
            (0, quest_time_revision_1.initializeQuestTimeRevision)(db);
            console.log("[DB] init done");
            // try to update after initialization
            if (updateRequired && updateAfter !== undefined) {
                updateAfter(db, currentVersion);
                console.log("Successfully updated wdfp_data.db");
            }
            const createdCleanupIndexes = (0, admin_account_cleanup_1.ensureCascadeDeleteIndexes)(db);
            if (createdCleanupIndexes > 0) {
                console.log(`[DB] created ${createdCleanupIndexes} cascade-delete indexes`);
            }
            // write version file
            (0, fs_1.writeFileSync)(versionFilePath, latestVersion.toString(), { encoding: 'utf-8' });
        }
        catch (error) {
            console.log(error);
            console.log(`Initalization failed for module ${metadata.path}. Error: ${error}`);
        }
    }
    // re-enable foreign keys
    db.pragma('foreign_keys = ON');
    // add to loaded databases
    loadedDatabases[database] = db;
    return db;
}
exports.default = getDatabase;
function initializeDatabase() {
    return getDatabase(0 /* Database.WDFP_DATA */);
}
exports.initializeDatabase = initializeDatabase;
