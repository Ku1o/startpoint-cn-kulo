import { FastifyInstance, FastifyRequest } from "fastify"
import { readFileSync } from "fs"
import path from "path"
import { staticPagesDir } from "./index"

const routes = async (fastify: FastifyInstance) => {
    const template = readFileSync(path.join(__dirname, staticPagesDir, "mail.html"), "utf-8")

    fastify.get("/mail", async (request: FastifyRequest, reply) => {
        const okMsg = (request.query as any).ok || ""
        const errMsg = (request.query as any).error || ""

        let html = template
        if (okMsg) {
            html = html.replace(
                '<p id="result" class="text-sm mt-2"></p>',
                `<p id="result" class="text-sm mt-2 text-green-600">${okMsg}</p>`
            )
        } else if (errMsg) {
            html = html.replace(
                '<p id="result" class="text-sm mt-2"></p>',
                `<p id="result" class="text-sm mt-2 text-error">${errMsg}</p>`
            )
        }

        reply.header("content-type", "text/html; charset=utf-8")
        reply.status(200).send(html)
    })
}

export default routes
