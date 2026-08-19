import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { getSession } from "../../data/domains/session";
import { generateDataHeaders } from "../../utils";

interface GetListBody {
    viewer_id: number;
    use_case?: number;
}

export function buildLoungeListData() {
    return {
        lounge_list: [] as unknown[],
    };
}

const routes = async (fastify: FastifyInstance) => {
    fastify.post("/get_list", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as GetListBody;
        const viewerId = Number(body?.viewer_id);

        if (!Number.isSafeInteger(viewerId) || viewerId <= 0) {
            return reply.status(400).send({
                error: "Bad Request",
                message: "Invalid request body.",
            });
        }

        const session = await getSession(String(viewerId));
        if (!session) {
            return reply.status(400).send({
                error: "Bad Request",
                message: "Invalid viewer id.",
            });
        }

        reply.header("content-type", "application/x-msgpack");
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: viewerId }),
            data: buildLoungeListData(),
        });
    });
};

export default routes;
