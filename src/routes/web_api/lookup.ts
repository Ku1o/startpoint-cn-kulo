import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import characterTable from "../../../docs/generated/character_table.json";
import itemLookup from "../../../assets/item_lookup.json";
import cnmodItemLookup from "../../../assets/item_lookup_cnmod.json";
import equipmentLookup from "../../../assets/equipment_lookup.json";
import questLookup from "../../../assets/quest_lookup.json";

interface CharEntry { id: number; name: string; title: string; rarity: string; element: string }
const charMap: Record<number, { name: string; title: string; rarity: string; element: string }> = {}
const mergedItemLookup = {
    ...(itemLookup as Record<string, string>),
    ...(cnmodItemLookup as Record<string, string>),
}
for (const c of (characterTable as CharEntry[])) {
    charMap[c.id] = { name: c.name, title: c.title, rarity: c.rarity, element: c.element }
}

const routes = async (fastify: FastifyInstance) => {
    fastify.get("/characters", async (_request: FastifyRequest, reply: FastifyReply) => {
        return reply.send(charMap)
    })

    fastify.get("/items", async (_request: FastifyRequest, reply: FastifyReply) => {
        return reply.send(mergedItemLookup)
    })

    fastify.get("/equipment", async (_request: FastifyRequest, reply: FastifyReply) => {
        return reply.send(equipmentLookup)
    })

    fastify.get("/quests", async (_request: FastifyRequest, reply: FastifyReply) => {
        return reply.send(questLookup)
    })
}

export default routes;
