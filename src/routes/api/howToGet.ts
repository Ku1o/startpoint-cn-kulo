import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { getSession } from "../../data/domains/session";
import { resolvePlayerIdSync } from "../../data/activeAccount";
import { getServerDate, generateDataHeaders } from "../../utils";
import { getPlayerShopPurchasesMapSync } from "../../data/domains/shopPurchase";
import { getPlayerDegreeIdsSync } from "../../data/domains/degree";
import { getShopItemSync } from "../../lib/assets";
import { ShopItemRewardType, DegreeShopItemReward } from "../../lib/types";
import { getHowToGetSources } from "../../lib/how-to-get-sources";
import { buildShopSalesEntry, isShopItemAvailable } from "../../lib/shop-sales";

interface GetListBody {
    viewer_id?: number;
    equipment_id?: number;
    item_id?: number;
}

function sendSources(reply: FastifyReply, viewerId: number, shops: Object[] = [], boxes: number[] = []) {
    reply.header("content-type", "application/x-msgpack");
    return reply.status(200).send({
        data_headers: generateDataHeaders({ viewer_id: viewerId }),
        data: {
            box_gacha_id_list: boxes,
            unselected_lineup_shop_sales_list: [],
            shop_sales_list: shops,
        },
    });
}

const routes = async (fastify: FastifyInstance) => {
    fastify.post("/get_list", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as GetListBody | undefined;
        const viewerId = Number(body?.viewer_id);
        const equipmentId = Number(body?.equipment_id);
        const isEquipment = Number.isSafeInteger(equipmentId) && equipmentId > 0;
        const targetId = isEquipment ? equipmentId : Number(body?.item_id);
        if (!Number.isSafeInteger(viewerId) || viewerId <= 0 || !Number.isSafeInteger(targetId) || targetId <= 0) {
            return sendSources(reply, Number.isSafeInteger(viewerId) && viewerId > 0 ? viewerId : 0);
        }
        const session = await getSession(String(viewerId));
        if (!session) return sendSources(reply, viewerId);
        const playerId = resolvePlayerIdSync(session.accountId);
        if (playerId == null) return sendSources(reply, viewerId);

        const sources = getHowToGetSources(isEquipment, targetId);
        const now = getServerDate();
        const purchases = getPlayerShopPurchasesMapSync(playerId);
        let ownedDegrees: Set<number> | undefined;
        const sales: Object[] = [];
        for (const source of sources.shops) {
            // The public accessor includes retired-row filtering and Rush rerun
            // compatibility periods. Never cache availability or player stock.
            const item = getShopItemSync(source.shopType, source.shopItemId);
            if (!item || !isShopItemAvailable(item, now)) continue;
            const degreeIds = item.rewards.filter(r => r.type === ShopItemRewardType.DEGREE)
                .map(r => (r as DegreeShopItemReward).id);
            if (degreeIds.length && !ownedDegrees) ownedDegrees = new Set(getPlayerDegreeIdsSync(playerId));
            const degreeOwned = degreeIds.some(id => ownedDegrees!.has(id));
            sales.push(buildShopSalesEntry(source.shopType, source.shopItemId, item, purchases, degreeOwned));
        }
        // Box event availability is resolved by the existing client against its
        // exchangeable event list. Keep that protocol and its original box IDs.
        return sendSources(reply, viewerId, sales, sources.boxes);
    });
};

export default routes;
