import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { generateDataHeaders, generateViewerId } from "../../utils";
import { deleteAccountSessionsOfTypeSync, deleteDeviceBindingSync, getAccountSessionsOfTypeSync, getDeviceBindingSync, insertDeviceBindingSync, insertSessionWithToken } from "../../data/domains/session"
import { getAccountSync, insertAccountSync, updateAccountSync } from "../../data/domains/account"
import { getPlayerSync, insertDefaultPlayerSync } from "../../data/domains/player"
import { SessionType } from "../../data/types";
import { saveAccountDefaultPlayer } from "../../data/activeAccount";
import { getDb } from "../../data/db";

interface CnSignupBody {
    device_id: number;
    channelNo: string;
    media?: string;
    androidId?: string;
    oaid?: string;
    mac?: string;
    terminInfo?: string;
    osVer?: string;
    storage_directory_path?: string;
    first_viewer_id?: number;
    advertise_id?: string;
}

function generateLoginToken(): string {
    const chars = "abcdefghijklmnopqrstuvwxyz0123456789";
    let token = "";
    for (let i = 0; i < 32; i++) {
        token += chars[Math.floor(Math.random() * chars.length)];
    }
    return token;
}

const viewerIdToAccountId = new Map<number, number>();

function createAccountForDevice(deviceId: number): number {
    const created = getDb().transaction(() => {
        const account = insertAccountSync({
            appId: "wf_cn", idpAlias: "", idpCode: "leiting", idpId: "", status: "normal"
        })
        const player = insertDefaultPlayerSync(account.id)
        insertDeviceBindingSync(deviceId, account.id)
        return { accountId: account.id, playerId: player.id }
    })()

    // Persist the management-panel preference only after the database commit.
    // A failed player materialization must not leave an account with no save.
    saveAccountDefaultPlayer(created.accountId, created.playerId)
    return created.accountId
}

interface GetHeaderResponseBody {
    viewer_id: number
}

const routes = async (fastify: FastifyInstance) => {
    fastify.post("/get_header_response", (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as GetHeaderResponseBody;
        reply.header("content-type", "application/x-msgpack");
        reply.status(200).send({
            "data_headers": generateDataHeaders({
                viewer_id: body.viewer_id
            }),
            "data": []
        });
    });

    fastify.post("/auth", async (_request: FastifyRequest, reply: FastifyReply) => {
        reply.header("content-type", "application/x-msgpack");
        reply.status(200).send({
            data_headers: generateDataHeaders(),
            data: {}
        });
    });

    fastify.post("/signup", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as CnSignupBody;
        const udid = request.headers["udid"] as string || "unknown";
        const shortUdid = 0;
        const deviceId = body.device_id

        const loginToken = generateLoginToken();
        let accountId: number;
        let newAccount = true;
        let viewerId: number | undefined;   // set when reusing existing session

        if (!deviceId) {
            return reply.status(400).send({ error: "Missing device_id" })
        }

        // Device binding: each device gets its own account
        const binding = getDeviceBindingSync(deviceId)

        if (binding) {
            // Known device — verify account still exists
            const accountExists = getAccountSync(binding.account_id)
            if (accountExists) {
                accountId = binding.account_id
                newAccount = false
                updateAccountSync({
                    id: accountId,
                    lastLoginTime: new Date(),
                    // A still-bound device is authoritative after reinstall;
                    // refresh its local UDID so the takeover old-device guard
                    // does not reject the newly initialized local store.
                    ...(accountExists.takeoverUdid ? { takeoverUdid: udid } : {}),
                })
                // Clean all old sessions for this account, reuse first token
                const sessions = getAccountSessionsOfTypeSync(accountId, SessionType.VIEWER)
                if (sessions.length > 0) {
                    viewerId = parseInt(sessions[0].token)
                    deleteAccountSessionsOfTypeSync(accountId, SessionType.VIEWER)
                }
            } else {
                // Account was deleted — clean up stale binding and create new account
                deleteDeviceBindingSync(deviceId)
                accountId = createAccountForDevice(deviceId)
            }
        } else {
            // New device → create account
            accountId = createAccountForDevice(deviceId)
        }

        if (!viewerId) {
            viewerId = generateViewerId()
        }
        await insertSessionWithToken({
            token: String(viewerId),
            accountId: accountId,
            type: SessionType.VIEWER,
            expires: new Date(Date.now() + 365 * 24 * 60 * 60 * 1000)
        });

        viewerIdToAccountId.set(viewerId, accountId);

        reply.header("content-type", "application/x-msgpack");
        reply.status(200).send({
            data_headers: generateDataHeaders({
                viewer_id: viewerId,
                short_udid: shortUdid,
                udid: udid,
            }),
            data: {
                login_token: loginToken,
                newAccount: newAccount ? 1 : 0,
                roleName: `Player${accountId}`,
                accountName: `Player${accountId}`,
                sign: "dummy_sign",
                createDate: new Date().toISOString(),
                serverName: "StarPoint CN",
                serverId: 1,
            }
        });
    });
};

export default routes;
