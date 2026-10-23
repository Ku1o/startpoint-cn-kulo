export interface ServerStatus {
    server: {
        uptimeSeconds: number
        onlinePlayers: number
        nodeVersion: string
        platform: string
        pid: number
        memory: { rss: number; heapUsed: number; heapTotal: number }
        listenHost: string
        listenPort: string
    }
    cdn: {
        baseUrl: string
        baseline: {
            mode: string
            source: string
            fullVersion: string
            cnFinalVersion: string
            detectedArchiveVersion: string
            manifestVersion: string
            pinned: boolean
            dataScope: string[]
        }
        extension: {
            mode: string
            status: string
            runtimeEnabled: boolean
            effectiveVersionPreview: string
            enabledPatchCount: number
            totalPatchCount: number
            activePatchArchiveCount: number
            note: string
        }
        storage: {
            configuredDir: string
            directoryPresent: boolean
            archiveCount: number
            archiveBytes: number
            latestArchiveMtime: string | null
        }
        configuredDir: string
        directoryPresent: boolean
        archiveCount: number
        archiveBytes: number
        latestArchiveMtime: string | null
        fullVersion: string
        detectedVersion: string
        effectiveVersion: string
        manifestVersion: string
        enabledPatchCount: number
        totalPatchCount: number
        activePatchArchiveCount: number
    }
}
