import { parentPort } from "node:worker_threads"
import { encodeCnResponse, type ResponseEncodingInput } from "../lib/cn-response-encoding"
import { installWorkerMemoryProbe } from "../lib/memory-diagnostics"

let completed = 0
installWorkerMemoryProbe(() => ({ completed }))
parentPort?.on("message", async (message: { type: string, id: number, input: ResponseEncodingInput }) => {
    if (message.type !== "encode") return
    try {
        const result = await encodeCnResponse(message.input)
        completed++
        parentPort!.postMessage({ type: "encoded", id: message.id, result })
    } catch {
        parentPort!.postMessage({ type: "encoded", id: message.id, error: true })
    }
})
