import { existsSync as nativeExistsSync, statSync, PathLike } from "node:fs"

/**
 * Node 20.20.2 on Windows leaks the access-path buffer in fs.existsSync when
 * access succeeds and the same uv_fs_t is reused for stat without cleanup.
 * A single stat keeps live existence checks (including symlink targets) without
 * that allocation. Preserve existsSync's false-on-error contract and avoid a
 * cache, so file creation, deletion and replacement remain visible immediately.
 */
export function existsSync(path: PathLike): boolean {
    if (process.platform !== "win32") return nativeExistsSync(path)
    try {
        return statSync(path, { throwIfNoEntry: false }) !== undefined
    } catch {
        return false
    }
}
