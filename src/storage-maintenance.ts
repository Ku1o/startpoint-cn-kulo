/** Offline maintenance CLI. Deliberately never imports data/db or server startup. */
import Database from "better-sqlite3"
import { createHash, randomUUID } from "crypto"
import { closeSync, copyFileSync, createReadStream, existsSync, fsyncSync, lstatSync, mkdirSync, openSync, readFileSync, readdirSync, realpathSync, renameSync, rmdirSync, statfsSync, statSync, unlinkSync, writeFileSync } from "fs"
import path from "path"
import { writeJsonAtomicSync } from "./lib/atomic-json-file"
import { assertStorageLayout, getStorageLayoutVersion, migrateStorageLayout, WDFP_DATA_VERSION } from "./lib/storage-layout"
import { DEFAULT_HISTORY_POLICY, acquireHistoryLease, finishHistoryLease, initializeMaintenanceState, readHistoryPolicy, refreshHistoryLease } from "./lib/maintenance-state"
import { isReceiveHistoryRetentionEnabled, runReceiveHistoryRetentionPass } from "./lib/receive-history-retention"

export interface MaintenancePaths { project: string; database: string; lock: string; state: string; backups: string }
interface RunState {
    format: 1; id: string; database: string; phase: string; createdAt: string; backup: string; backupSha256?: string
    layoutBefore: number; before: unknown; migration?: unknown; retention?: unknown; after?: unknown; error?: string
}

export function maintenancePaths(project = path.resolve(__dirname, "..")): MaintenancePaths {
    const root = realpathSync(project)
    const dataDir = realpathSync(process.env.DATA_DIR ? path.resolve(root,process.env.DATA_DIR) : path.join(root,".database"))
    return {project:root,database:path.join(dataDir,"wdfp_data.db"),lock:path.join(dataDir,"storage-maintenance.lock"),
        state:path.join(dataDir,"storage-maintenance-state.json"),backups:path.join(dataDir,"maintenance-backups")}
}

async function sha256(file: string): Promise<string> {
    const hash=createHash("sha256")
    for await (const chunk of createReadStream(file)) hash.update(chunk)
    return hash.digest("hex")
}

function loadState(paths: MaintenancePaths): RunState {
    const state=JSON.parse(readFileSync(paths.state,"utf8")) as RunState
    const backupRoot=path.resolve(paths.backups)
    const directory=path.dirname(path.resolve(state.backup))
    if (state.format!==1 || state.database!==paths.database || path.dirname(directory)!==backupRoot || path.basename(directory)!==state.id
        || !/^storage-\d{8}T\d{9}Z-[a-f0-9-]{36}$/.test(state.id) || path.basename(state.backup)!=="wdfp_data.db") {
        throw new Error("维护状态与当前数据库不匹配")
    }
    return state
}

function saveState(paths: MaintenancePaths, state: RunState, phase: string): void {
    state.phase=phase
    writeJsonAtomicSync(paths.state,state)
    writeJsonAtomicSync(path.join(path.dirname(state.backup),"report.json"),state)
}

function databaseStats(db: Database.Database): unknown {
    return {pageCount:db.pragma("page_count",{simple:true}),freePages:db.pragma("freelist_count",{simple:true}),
        pageSize:db.pragma("page_size",{simple:true}),layoutVersion:getStorageLayoutVersion(db),
        objects:db.prepare("SELECT name,SUM(pgsize) bytes FROM dbstat GROUP BY name ORDER BY bytes DESC").all()}
}

export function previewMaintenance(paths: MaintenancePaths): unknown {
    const versionFile=paths.database+".version"
    if(!existsSync(versionFile))throw new Error("缺少 wdfp_data.db.version，不能确认基础数据库版本，未执行维护")
    const databaseVersion=Number(readFileSync(versionFile,"utf8").trim())
    if(databaseVersion!==WDFP_DATA_VERSION)throw new Error(`基础数据库版本 ${databaseVersion} 与维护工具要求 ${WDFP_DATA_VERSION} 不一致`)
    const db=new Database(paths.database,{readonly:true,fileMustExist:true})
    try {
        db.pragma("query_only=ON")
        assertStorageLayout(db)
        const settings=db.prepare("SELECT 1 FROM sqlite_master WHERE name='server_maintenance_settings'").get()
        const policy=settings?readHistoryPolicy(db):DEFAULT_HISTORY_POLICY
        const cutoff=new Date(Date.now()-policy.maxDays*86400_000).toISOString()
        const candidates=db.prepare(`SELECT COUNT(*) n FROM (SELECT create_time,
            ROW_NUMBER() OVER(PARTITION BY player_id ORDER BY create_time DESC,id DESC) position FROM players_receive_history)
            WHERE position>? OR julianday(create_time)<julianday(?)`).get(policy.maxRows,cutoff) as {n:number}
        const size=statSync(paths.database).size
        const logicalBytes=Number(db.pragma("page_count",{simple:true}))*Number(db.pragma("page_size",{simple:true}))
        const fs=statfsSync(path.dirname(paths.database))
        const available=Number(fs.bavail)*Number(fs.bsize)
        return {database:paths.database,databaseVersion,lock:paths.lock,state:paths.state,backups:paths.backups,bytes:size,
            logicalBytes,availableBytes:available,requiredAdditionalBytes:Math.max(size,logicalBytes)*3+256*1024*1024,
            policy,automaticRetentionEnabled:isReceiveHistoryRetentionEnabled(),historyDeletionCandidates:candidates.n,locked:existsSync(paths.lock),
            port:Number(process.env.CN_LISTEN_PORT??8001),stats:databaseStats(db)}
    } finally {db.close()}
}

function openExclusive(paths: MaintenancePaths): Database.Database {
    const db=new Database(paths.database,{fileMustExist:true,timeout:1000})
    try {
        db.pragma("temp_store=FILE")
        db.pragma("locking_mode=EXCLUSIVE")
        db.exec("BEGIN EXCLUSIVE; COMMIT")
        return db
    } catch (error) {db.close(); throw error}
}

export async function applyMaintenance(paths: MaintenancePaths, checkpoint: (stage:string)=>void = ()=>{}): Promise<RunState> {
    if(existsSync(paths.state)) {
        const previous=loadState(paths)
        if(!["completed","rolled-back"].includes(previous.phase)) throw new Error(`上次维护尚未结束（${previous.phase}），请使用恢复入口`)
    }
    const preview=previewMaintenance(paths) as {availableBytes:number;requiredAdditionalBytes:number;automaticRetentionEnabled:boolean}
    if(!preview.automaticRetentionEnabled)throw new Error("RECEIVE_HISTORY_RETENTION_ENABLED 已关闭自动维护；请先检查该配置，当前不会覆盖原有开关")
    if(preview.availableBytes<preview.requiredAdditionalBytes) throw new Error("磁盘空间不足以同时保留备份、迁移临时数据和空间回收文件")
    const descriptor=openSync(paths.lock,"wx")
    writeFileSync(descriptor,JSON.stringify({pid:process.pid,createdAt:new Date().toISOString(),database:paths.database}))
    fsyncSync(descriptor); closeSync(descriptor)
    let db: Database.Database | undefined
    let state: RunState | undefined
    try {
        db=openExclusive(paths)
        assertStorageLayout(db)
        if(db.pragma("quick_check",{simple:true})!=="ok") throw new Error("数据库检查失败，未执行迁移")
        const id=`storage-${new Date().toISOString().replace(/[-:.]/g,"")}-${randomUUID()}`
        const directory=path.join(paths.backups,id)
        mkdirSync(directory,{recursive:true})
        state={format:1,id,database:paths.database,phase:"backing-up",createdAt:new Date().toISOString(),
            backup:path.join(directory,"wdfp_data.db"),layoutBefore:getStorageLayoutVersion(db),before:preview}
        saveState(paths,state,"backing-up")
        await db.backup(state.backup)
        const backupDb=new Database(state.backup,{fileMustExist:true})
        try {
            backupDb.pragma("journal_mode=DELETE")
            if(backupDb.pragma("quick_check",{simple:true})!=="ok")throw new Error("备份完整性检查失败")
        } finally {backupDb.close()}
        state.backupSha256=await sha256(state.backup)
        for(const name of ["wdfp_data.db.version","active_account.json"]) {
            const source=path.join(path.dirname(paths.database),name)
            if(existsSync(source))copyFileSync(source,path.join(directory,name))
        }
        saveState(paths,state,"migrating")
        checkpoint("backup-verified")
        state.migration=migrateStorageLayout(db,checkpoint)
        saveState(paths,state,"retaining-history")
        initializeMaintenanceState(db)
        const lease=acquireHistoryLease(db)
        if(!lease)throw new Error("数据库仍有历史清理任务租约，稍后恢复维护，避免重叠运行")
        try {
            const result=await runReceiveHistoryRetentionPass(db,{...readHistoryPolicy(db),pauseMs:0},()=>{refreshHistoryLease(db!,lease);return false})
            finishHistoryLease(db,lease,result,result.failedPlayers===0&&!result.stopped)
            state.retention=result
            if(result.failedPlayers>0||result.stopped)throw new Error("领取历史维护未完整完成")
        } catch(error) {finishHistoryLease(db,lease,undefined,false,String(error));throw error}
        saveState(paths,state,"compacting")
        checkpoint("before-vacuum")
        db.exec("VACUUM; ANALYZE")
        if(db.pragma("integrity_check",{simple:true})!=="ok" || (db.pragma("foreign_key_check") as unknown[]).length>0)throw new Error("维护后数据库完整性检查失败")
        state.after=databaseStats(db)
        db.pragma("wal_checkpoint(TRUNCATE)")
        saveState(paths,state,"ready")
        return state
    } catch(error) {
        if(state) {state.error=error instanceof Error?error.message:String(error);saveState(paths,state,"failed")}
        else unlinkSync(paths.lock) // No data or migration has been written yet.
        throw error
    } finally {if(db?.open)db.close()}
}

export async function rollbackMaintenance(paths: MaintenancePaths): Promise<RunState> {
    const state=loadState(paths)
    if(!existsSync(paths.lock))throw new Error("维护锁不存在，不能回滚可能已恢复服务的数据库")
    if(state.phase==="rollback-ready")return state
    if(!["failed","backing-up","migrating","retaining-history","compacting","ready","restoring"].includes(state.phase)) {
        throw new Error("服务可能已重新开放写入，拒绝覆盖旧备份；请使用继续启动/状态检查")
    }
    if(!state.backupSha256) {
        // Failure before the verified backup cannot have modified game data.
        saveState(paths,state,"rollback-ready")
        return state
    }
    if(await sha256(state.backup)!==state.backupSha256)throw new Error("备份校验值不匹配，拒绝恢复")
    if(state.phase!=="restoring") {
        const db=openExclusive(paths)
        try {
            db.pragma("wal_checkpoint(TRUNCATE)")
            // Let SQLite remove its own WAL/SHM under the exclusive lock.
            // An SHM file can remain after a readonly connection closes; its
            // mere existence does not prove that another process is active.
            if(db.pragma("journal_mode=DELETE",{simple:true})!=="delete")throw new Error("无法独占关闭 WAL 日志")
        } finally {db.close()}
    }
    for(const suffix of ["-wal","-shm"]) {
        const file=paths.database+suffix
        if(!existsSync(file))continue
        if(suffix==="-wal"&&statSync(file).size>0)throw new Error("数据库旁仍有未回收 WAL 内容，拒绝恢复")
        // journal_mode=DELETE succeeded under an exclusive lock above. Any
        // remaining SHM is now a stale index, and the WAL must be empty.
        if(path.dirname(path.resolve(file))!==path.dirname(paths.database))throw new Error("数据库恢复路径越界")
        unlinkSync(file)
    }
    saveState(paths,state,"restoring")
    const temp=paths.database+".maintenance-restore"
    copyFileSync(state.backup,temp)
    const descriptor=openSync(temp,"r+");fsyncSync(descriptor);closeSync(descriptor)
    renameSync(temp,paths.database)
    const verify=new Database(paths.database,{readonly:true,fileMustExist:true})
    try {if(verify.pragma("quick_check",{simple:true})!=="ok")throw new Error("恢复后数据库检查失败")} finally {verify.close()}
    saveState(paths,state,"rollback-ready")
    return state
}

export function releaseMaintenance(paths: MaintenancePaths): RunState {
    const state=loadState(paths)
    if(!["ready","rollback-ready","service-starting","rollback-starting"].includes(state.phase))throw new Error("维护尚未校验完成，不能启动服务")
    const rollback=state.phase.startsWith("rollback")
    saveState(paths,state,rollback?"rollback-starting":"service-starting")
    if(existsSync(paths.lock))unlinkSync(paths.lock)
    return state
}

export function completeMaintenance(paths: MaintenancePaths): RunState {
    const state=loadState(paths)
    if(!["service-starting","rollback-starting"].includes(state.phase))throw new Error("维护不在启动验收阶段")
    saveState(paths,state,state.phase==="rollback-starting"?"rolled-back":"completed")
    pruneMaintenanceBackups(paths,state.id)
    return state
}

/** Keep three completed backups, including the latest pre-migration baseline. */
function pruneMaintenanceBackups(paths: MaintenancePaths, currentId: string): void {
    const root=realpathSync(paths.backups)
    const candidates: {id:string;state:RunState;directory:string}[]=[]
    for(const entry of readdirSync(root,{withFileTypes:true})) {
        if(!entry.isDirectory()||entry.isSymbolicLink()||!/^storage-\d{8}T\d{9}Z-[a-f0-9-]{36}$/.test(entry.name))continue
        const directory=path.resolve(root,entry.name)
        if(realpathSync(directory)!==directory)continue
        try {
            const state=JSON.parse(readFileSync(path.join(directory,"report.json"),"utf8")) as RunState
            if(state.format===1&&state.id===entry.name&&state.database===paths.database&&["completed","rolled-back"].includes(state.phase))candidates.push({id:entry.name,state,directory})
        } catch { /* Unknown/incomplete directories remain available for recovery. */ }
    }
    candidates.sort((a,b)=>b.id.localeCompare(a.id))
    const keep=new Set([currentId])
    const baseline=candidates.find(c=>c.state.layoutBefore===0&&c.state.phase==="completed")
    if(baseline)keep.add(baseline.id)
    for(const c of candidates){if(keep.size>=3)break;keep.add(c.id)}
    const allowed=new Set(["wdfp_data.db","wdfp_data.db.version","active_account.json","report.json","report.json.bak"])
    for(const c of candidates) {
        if(keep.has(c.id))continue
        const files=readdirSync(c.directory)
        if(files.some(f=>!allowed.has(f)||!lstatSync(path.join(c.directory,f)).isFile()||lstatSync(path.join(c.directory,f)).isSymbolicLink()))continue
        // Each exact resolved target is checked within this backup directory.
        for(const f of files){const target=path.resolve(c.directory,f);if(path.dirname(target)!==c.directory)throw new Error("备份路径越界");unlinkSync(target)}
        rmdirSync(c.directory)
    }
}

export function unlockUnstartedMaintenance(paths: MaintenancePaths): void {
    if(existsSync(paths.state)&&!["completed","rolled-back"].includes(loadState(paths).phase))throw new Error("已有未结束维护，不能直接解锁")
    if(!existsSync(paths.lock))return
    const lock=JSON.parse(readFileSync(paths.lock,"utf8")) as {pid:number;database:string}
    if(lock.database!==paths.database||!Number.isSafeInteger(lock.pid)||lock.pid<1)throw new Error("维护锁信息无效")
    let running=true
    try{process.kill(lock.pid,0)}catch(error){if((error as NodeJS.ErrnoException).code==="ESRCH")running=false;else throw error}
    if(running)throw new Error("维护进程仍在运行，不能解锁")
    unlinkSync(paths.lock)
}

async function main(): Promise<void> {
    const command=process.argv[2]??"preview"
    const projectArgument=process.argv.indexOf("--project")
    if(projectArgument>=0&&!process.argv[projectArgument+1])throw new Error("--project 缺少项目目录")
    const paths=maintenancePaths(projectArgument>=0?process.argv[projectArgument+1]:undefined)
    let result: unknown
    switch(command) {
        case "preview":result=previewMaintenance(paths);break
        case "status":result=existsSync(paths.state)?loadState(paths):{phase:"not-started",database:paths.database};break
        case "apply":result=await applyMaintenance(paths,stage=>console.error(`[STORAGE] ${stage}`));break
        case "rollback":result=await rollbackMaintenance(paths);break
        case "release":result=releaseMaintenance(paths);break
        case "complete":result=completeMaintenance(paths);break
        case "unlock-unstarted":unlockUnstartedMaintenance(paths);result={unlocked:true};break
        default:throw new Error("支持命令：preview / apply / status / rollback / release / complete")
    }
    if (["apply","rollback","release","complete"].includes(command)) {
        const state=result as RunState
        result={id:state.id,phase:state.phase,database:state.database,backup:state.backup,report:paths.state,
            migration:state.migration,retention:state.retention,error:state.error}
    }
    console.log(JSON.stringify(result,null,2))
}

if(require.main===module)void main().catch(error=>{console.error(error instanceof Error?error.message:String(error));process.exitCode=1})
