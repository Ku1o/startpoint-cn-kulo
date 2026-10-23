import { defineConfig, loadEnv } from "vite"
import type { Plugin } from "vite"
import react from "@vitejs/plugin-react"
import { brotliCompressSync, gzipSync } from "node:zlib"
import { readFileSync, writeFileSync } from "node:fs"
import path from "node:path"

function precompressAdmin(): Plugin {
    return {
        name: "admin-precompress",
        writeBundle(options, bundle) {
            if (!options.dir) throw new Error("管理面板预压缩需要输出目录")
            for (const [fileName, entry] of Object.entries(bundle)) {
                if (!/\.(js|css|html)$/.test(fileName)) continue
                // Vite replaces preload markers after generateBundle; compress final emitted bytes.
                if (entry.type !== "chunk" && entry.type !== "asset") continue
                const output = path.join(options.dir, fileName)
                const bytes = Uint8Array.from(readFileSync(output))
                if (bytes.length < 1024 && !fileName.endsWith(".html")) continue
                for (const [extension, compressed] of [["gz", gzipSync(bytes)], ["br", brotliCompressSync(bytes)]] as const) {
                    if (compressed.length < bytes.length) writeFileSync(`${output}.${extension}`, Uint8Array.from(compressed))
                }
            }
        },
    }
}

function adminSlashRedirect() {
    return {
        name: "admin-slash-redirect",
        configureServer(server: any) {
            server.middlewares.use((req: any, res: any, next: any) => {
                if (req.url === "/admin") {
                    res.statusCode = 302
                    res.setHeader("Location", "/admin/")
                    res.end()
                    return
                }
                next()
            })
        },
        configurePreviewServer(server: any) {
            server.middlewares.use((req: any, res: any, next: any) => {
                if (req.url === "/admin") {
                    res.statusCode = 302
                    res.setHeader("Location", "/admin/")
                    res.end()
                    return
                }
                next()
            })
        },
    }
}

// dev: 5173, /api 代理到 CN 服务（默认 localhost:8001）
// 若 CN_LISTEN_HOST 绑定了 LAN IP，在 admin/.env 里设 VITE_API_TARGET 覆盖
// build: 产物输出到 ../web/dist，由 cn-server 挂载在 /admin
export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, process.cwd(), "")
    const apiTarget = env.VITE_API_TARGET || "http://localhost:8001"
    return {
        plugins: [adminSlashRedirect(), react(), precompressAdmin()],
        base: "/admin/",
        server: {
            port: 5173,
            proxy: {
                "/api": {
                    target: apiTarget,
                    changeOrigin: true
                }
            }
        },
        build: {
            outDir: "../web/dist",
            // Old browser tabs may still reference previous hash chunks.
            emptyOutDir: false
        }
    }
})
