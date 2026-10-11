import * as path from "node:path"
import type { RoomCommandGateway } from "./command-gateway"
import type { RoomCommandExecutor } from "./command-executor"
import type { RoomCommandTransport } from "./command-protocol"
import { CommandProcessTransport } from "./command-process"
import { handleParentBusiness } from "./business-rpc"
import { isRealtimeParent } from "./runtime-role"
import { assertServerAcceptingWork, hasServerWorkAdmission, isServerShuttingDown } from "../../lib/shutdown-state"
import { createAcceptedRealtimeBusinessScope } from "./parent-business-admission"

let gateway: RoomCommandGateway | undefined
let executor: RoomCommandExecutor | undefined
let processTransport: CommandProcessTransport | undefined
let starting: Promise<void> | undefined
let phase: "idle" | "starting" | "running" | "quiescing" | "stopped" | "failed" = "idle"
let quiesced: Promise<void> | undefined
let stopped: Promise<void> | undefined
function assertOwnerAdmission(): void {
    assertServerAcceptingWork()
    if (phase === "stopped" || phase === "failed" || (phase === "quiescing" && !hasServerWorkAdmission())) {
        throw Object.assign(new Error("REALTIME_OWNER_UNAVAILABLE"), { code: "REALTIME_OWNER_UNAVAILABLE" })
    }
}

export function registerRealtimeDomainHandlers(owner: RoomCommandExecutor): void {
    const modules = [
        ["./room-command-handlers", "registerRoomCommandHandlers"],
        ["./battle-command-handlers", "registerBattleCommandHandlers"],
        ["./lobby-command-handlers", "registerLobbyCommandHandlers"],
        ["./lounge-command-handlers", "registerLoungeCommandHandlers"],
        ["./five-boss-command-handlers", "registerFiveBossCommandHandlers"],
        ["./runtime-command-handlers", "registerRuntimeCommandHandlers"],
    ]
    for (const [module, method] of modules) require(module)[method](owner)
}

/** One configured owner. A failed remote owner never creates embedded authority. */
export function getRoomCommandGateway(): RoomCommandGateway {
    if (gateway) return gateway
    assertOwnerAdmission()
    const { RoomCommandGateway } = require("./command-gateway") as typeof import("./command-gateway")
    if (isRealtimeParent()) {
        const lazy: RoomCommandTransport = {
            get ownerEpoch() { return processTransport?.ownerEpoch },
            submit: async command => { assertOwnerAdmission(); await startRealtimeOwner(); return processTransport!.submit(command) },
            queryResult: async id => {
                if (!processTransport && phase !== "idle") throw new Error("REALTIME_OWNER_UNAVAILABLE")
                await startRealtimeOwner(); return processTransport!.queryResult(id)
            },
        }
        gateway = new RoomCommandGateway(lazy, { timeoutMs: 8000, maxAgeMs: 10000 })
    } else {
        const { RoomCommandExecutor } = require("./command-executor") as typeof import("./command-executor")
        executor = new RoomCommandExecutor()
        const owner = executor
        const admissions = new Map<string, ReturnType<typeof createAcceptedRealtimeBusinessScope>>()
        owner.setHandlerContext((id, operation) => {
            const admission = admissions.get(id)
            if (!admission) throw new Error("REALTIME_BUSINESS_ADMISSION_INVALID")
            return admission.run(async () => operation())
        })
        registerRealtimeDomainHandlers(executor)
        const embeddedTransport: RoomCommandTransport = {
            ownerEpoch: owner.ownerEpoch,
            async submit(command) {
                assertOwnerAdmission()
                const ownsAdmission = !admissions.has(command.commandId)
                const scope = ownsAdmission ? createAcceptedRealtimeBusinessScope({ ownerEpoch: owner.ownerEpoch, commandId: command.commandId }) : admissions.get(command.commandId)!
                if (ownsAdmission) admissions.set(command.commandId, scope)
                try { return await owner.submit(command, hasServerWorkAdmission()) }
                finally { if (ownsAdmission) { admissions.delete(command.commandId); scope.release() } }
            },
            queryResult: id => owner.queryResult(id),
        }
        gateway = new RoomCommandGateway(embeddedTransport)
    }
    return gateway
}

export function assertRealtimeOwnerEpoch(epoch: string, claimToken?: string, ordinary = false): void {
    if (isRealtimeParent()) {
        if (!processTransport?.isReady || processTransport.ownerEpoch !== epoch) throw new Error("REALTIME_OWNER_UNAVAILABLE")
    } else {
        getRoomCommandGateway()
        if (executor?.ownerEpoch !== epoch) throw new Error("REALTIME_OWNER_EPOCH_CHANGED")
        if (claimToken) {
            if (ordinary) {
                require("./battle-command-handlers").assertOrdinaryStartClaim(claimToken)
                return
            }
            const { assertFiveBossStartClaim } = require("./five-boss-command-handlers") as {
                assertFiveBossStartClaim(token: string): void
            }
            assertFiveBossStartClaim(claimToken)
        }
    }
}

export function realtimeOwnerStatus() {
    return { mode: isRealtimeParent() ? "process" : "embedded", pid: processTransport?.pid ?? process.pid,
        ownerEpoch: processTransport?.ownerEpoch ?? executor?.ownerEpoch ?? null,
        phase, ready: phase !== "stopped" && phase !== "failed" && (isRealtimeParent() ? !!processTransport?.isReady : !!executor),
        endpoint: processTransport?.bootstrapMetadata() ?? null,
        transport: processTransport?.diagnostics() ?? null }
}

async function startRealtimeOwner(): Promise<void> {
    if (!starting) {
        assertOwnerAdmission()
        if (phase === "quiescing") throw new Error("REALTIME_OWNER_UNAVAILABLE")
        phase = "starting"
        processTransport = new CommandProcessTransport({
            registerModule: path.join(__dirname, "realtime-owner-bootstrap.js"),
            childEnv: { MULTI_REALTIME_OWNER_CHILD: "1", MULTI_REALTIME_PROCESS: "0", MULTI_BATTLE_RELAY_PROCESS: "0",
                CN_WRITER_THREAD: "0", PROCESS_MEMORY_DIAGNOSTICS: "false" },
            businessHandler: handleParentBusiness, startTimeoutMs: 15000, inheritOutput: true,
            maxPending: 128, maxPendingBytes: 4 * 1024 * 1024,
        })
        starting = processTransport.start().then(() => { if (phase === "starting") phase = "running" }, error => {
            phase = "failed"; gateway?.close(); throw error
        })
    }
    await starting
}

export async function startRealtimeSessionServer(): Promise<void> {
    if (isServerShuttingDown()) throw Object.assign(new Error("SERVER_CLOSING"), { code: "SERVER_CLOSING" })
    if (phase === "quiescing") throw new Error("REALTIME_OWNER_UNAVAILABLE")
    if (phase === "stopped" || phase === "failed") {
        gateway = undefined; executor = undefined; processTransport = undefined; starting = undefined
        quiesced = undefined; stopped = undefined; phase = "idle"
        require("./durable-owner-event").resumeDurableOwnerEvents()
    }
    process.env.MULTI_REALTIME_PROCESS ??= "1"
    if (!isRealtimeParent()) { getRoomCommandGateway(); await require("../tcp/server").startSessionServer(); phase = "running"; return }
    await startRealtimeOwner()
    getRoomCommandGateway()
    console.log(`[MULTI-REALTIME] owner ready pid=${processTransport!.pid} epoch=${processTransport!.ownerEpoch}`)
}
export function quiesceRealtimeSessionServer(): Promise<void> {
    if (!quiesced) {
        if (phase !== "stopped" && phase !== "failed") phase = "quiescing"
        executor?.quiesce()
        quiesced = (async () => {
            if (isRealtimeParent()) { await starting?.catch(() => {}); await processTransport?.quiesce() }
            else require("../tcp/server").quiesceSessionServer()
        })()
    }
    return quiesced
}
export async function drainRealtimeWork(): Promise<void> {
    await executor?.drain()
    await gateway?.drain()
    if (isRealtimeParent()) await processTransport?.drain()
    else {
        await require("./embedded").embeddedMultiCoordinator.drain()
        await require("../five-boss/lobby-runtime").drainFiveBossSignalPersistence()
    }
}
export function stopRealtimeSessionServer(): Promise<void> {
    if (!stopped) stopped = (async () => {
        require("./durable-owner-event").quiesceDurableOwnerEvents()
        await quiesceRealtimeSessionServer()
        await require("./durable-owner-event").drainDurableOwnerEvents()
        await drainRealtimeWork()
        gateway?.close(); executor?.close()
        if (isRealtimeParent()) await processTransport?.stop()
        else await require("../tcp/server").stopSessionServer()
        phase = "stopped"
    })()
    return stopped
}
/** Security/channel failure seals this owner until the service is explicitly restarted. */
export async function failRealtimeOwner(): Promise<void> {
    phase = "failed"
    gateway?.close()
    executor?.close()
    if (!isRealtimeParent()) { await require("../tcp/server").stopSessionServer(); return }
    await processTransport?.abort()
}
