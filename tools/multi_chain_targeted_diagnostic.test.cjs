const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const tempDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "multi-chain-targeted-"))
process.chdir(tempDirectory)
process.env.MULTI_CHAIN_DIAGNOSTIC_VIEWERS = "590670669; 273328465,invalid"

const {
    clearChainDiagnosticRoom,
    parseDiagnosticViewerIds,
    recordBattleConnection,
    recordBattleNotify,
    recordBattleReceive,
    recordBattleRelay,
    recordBattleServerSend,
    recordBattleSendAnomaly,
} = require("../out/multi/tcp/chain-diagnostic.js")

function fakeClient(viewerId, roomNumber, connectionId) {
    return {
        viewerId,
        roomNumber,
        roomGeneration: 7,
        connectionId,
        socket: {
            bytesRead: 100,
            bytesWritten: 200,
            readableLength: 0,
            writableLength: 0,
            destroyed: false,
            readable: true,
            writable: true,
        },
    }
}

async function main() {
    assert.deepEqual([...parseDiagnosticViewerIds("1, 2;2 bad -3")], [1, 2])

    const target = fakeClient(590670669, "target-room", "target-c1")
    const peer = fakeClient(111111111, "target-room", "peer-c1")
    const unrelated = fakeClient(222222222, "unrelated-room", "other-c1")

    // A target recipient activates recording for the entire room. Subsequent
    // peer traffic is retained so packet and heartbeat gaps can be compared.
    recordBattleRelay(peer, [target], "broadcast", 1, [2, "peer-c1", [[0, 1]]])
    recordBattleConnection(target, "connected", [target, peer], "loading")
    recordBattleReceive(peer, [1, [[0, 2]]])
    recordBattleNotify(peer, 5, [5])
    recordBattleServerSend(peer, "battle_heartbeat_ack", "sent", [1, [3, 0, 0, Date.now()]])
    recordBattleSendAnomaly("backpressure_recovered", {
        roomNumber: peer.roomNumber,
        roomGeneration: peer.roomGeneration,
        connectionId: peer.connectionId,
        viewerId: peer.viewerId,
        channel: "battle_broadcast",
    }, { blockedMs: 150 })
    recordBattleRelay(unrelated, [], "broadcast", 1, [2, "other-c1", []])
    clearChainDiagnosticRoom(target.roomNumber)

    await new Promise(resolve => setTimeout(resolve, 100))
    const logDirectory = path.join(tempDirectory, ".logs")
    const files = fs.readdirSync(logDirectory).filter(name => name.endsWith(".jsonl"))
    assert.equal(files.length, 1)
    const records = fs.readFileSync(path.join(logDirectory, files[0]), "utf8")
        .trim()
        .split(/\r?\n/)
        .map(line => JSON.parse(line))

    assert.ok(records.some(record => record.event === "battle_room_targeted"))
    assert.ok(records.some(record => record.event === "battle_receive" && record.sourceViewer === peer.viewerId))
    assert.ok(records.some(record => record.event === "battle_notify" && record.sourceViewer === peer.viewerId))
    assert.ok(records.some(record => record.event === "battle_server_send"
        && record.recipientViewer === peer.viewerId
        && record.channel === "battle_heartbeat_ack"))
    assert.ok(records.some(record => record.event === "battle_send_anomaly" && record.viewer === peer.viewerId))
    assert.ok(records.some(record => record.event === "battle_room_tracking_stopped"))
    assert.equal(records.some(record => record.room === unrelated.roomNumber), false)

    console.log("multi_chain_targeted_diagnostic.test: ok")
}

main().then(
    () => process.exit(0),
    error => {
        console.error(error)
        process.exit(1)
    },
)
