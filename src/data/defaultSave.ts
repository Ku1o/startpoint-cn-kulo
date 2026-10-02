import { existsSync } from "../lib/file-exists";
/**
 * 默认存档模板：管理员上传一份存档快照，作为「账户新建存档」时的初始内容。
 * 持久化到 .database/default_save.json（与 active_account.json 同目录，均 gitignored）。
 * 快照格式与 GET /api/player/save 导出一致，只接受完整存档 V2。
 */
import * as fs from "fs";
import * as path from "path";

const DATA_DIRECTORY = process.env.DATA_DIR
    ? path.resolve(process.env.DATA_DIR)
    : path.resolve(__dirname, "../../.database");
const FILE = path.join(DATA_DIRECTORY, "default_save.json");

export interface DefaultSaveSnapshot {
    schema: string;
    version: number;
    scope?: string;
    exportedAt?: string;
    playerId?: number;
    summary?: {
        playerName?: string;
        includedTableCount?: number;
        rowCount?: number;
    };
    data?: any;
}

export interface DefaultSaveMeta {
    exists: boolean;
    playerName?: string | null;
    exportedAt?: string | null;
    sourcePlayerId?: number | null;
    version?: number | null;
    scope?: string | null;
    includedTableCount?: number | null;
    rowCount?: number | null;
}

export function saveDefaultSaveTemplate(snapshot: DefaultSaveSnapshot): void {
    const dir = path.dirname(FILE);
    if (!existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(FILE, JSON.stringify(snapshot), "utf-8");
}

export function loadDefaultSaveTemplate(): DefaultSaveSnapshot | null {
    try {
        if (!existsSync(FILE)) return null;
        const parsed = JSON.parse(fs.readFileSync(FILE, "utf-8")) as DefaultSaveSnapshot;
        // A stale V1 template may remain on disk after an upgrade. Ignore it
        // instead of silently applying a partial snapshot to new accounts.
        if (parsed?.schema !== "starpoint-cn-save" || parsed.version !== 2 || parsed.scope !== "player-archive") {
            return null;
        }
        return parsed;
    } catch {
        return null;
    }
}

export function clearDefaultSaveTemplate(): boolean {
    try {
        if (existsSync(FILE)) { fs.unlinkSync(FILE); return true; }
    } catch { /* ignore */ }
    return false;
}

export function getDefaultSaveMeta(): DefaultSaveMeta {
    const t = loadDefaultSaveTemplate();
    if (!t) return { exists: false };
    return {
        exists: true,
        playerName: t.summary?.playerName ?? t.data?.player?.name ?? null,
        exportedAt: t.exportedAt ?? null,
        sourcePlayerId: t.playerId ?? null,
        version: t.version ?? null,
        scope: t.scope ?? null,
        includedTableCount: t.summary?.includedTableCount ?? null,
        rowCount: t.summary?.rowCount ?? null,
    };
}
