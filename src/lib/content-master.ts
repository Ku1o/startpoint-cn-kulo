import baseCharacters from "../../assets/character.json"
import rankP5bCharacters from "../../assets/character_rank_p5b.json"
import baseCdnCharacters from "../../assets/cdndata/character.json"
import rankP5bCdnCharacters from "../../assets/cdndata/character_rank_p5b.json"
import baseCdnCharacterTexts from "../../assets/cdndata/character_text.json"
import rankP5bCdnCharacterTexts from "../../assets/cdndata/character_text_rank_p5b.json"
import baseDegrees from "../../assets/degree.json"
import rankP5bDegrees from "../../assets/degree_rank_p5b.json"
import baseEventShops from "../../assets/event_item_shop.json"
import rankP5bEventShops from "../../assets/event_item_shop_rank_p5b.json"
import baseEventShopIdMap from "../../assets/event_item_shop_id_map.json"
import rankP5bEventShopIdMap from "../../assets/event_item_shop_id_map_rank_p5b.json"
import baseGachas from "../../assets/gacha.json"
import cnmodGachas from "../../assets/gacha_cnmod.json"
import rankP5bGachas from "../../assets/gacha_rank_p5b.json"
import baseItemIds from "../../assets/item_ids.json"
import rankP5bItemIds from "../../assets/item_ids_rank_p5b.json"
import baseManaNodes from "../../assets/mana_node.json"
import cnmodManaNodes from "../../assets/mana_node_cnmod.json"
import rankP5bManaNodes from "../../assets/mana_node_rank_p5b.json"

export const serverCharacters = { ...baseCharacters, ...rankP5bCharacters }
export const cdnCharacters = { ...baseCdnCharacters, ...rankP5bCdnCharacters }
export const cdnCharacterTexts = { ...baseCdnCharacterTexts, ...rankP5bCdnCharacterTexts }
export const degreeDefinitions = { ...baseDegrees, ...rankP5bDegrees }
export const serverGachas = { ...baseGachas, ...cnmodGachas, ...rankP5bGachas }
export const serverManaNodes = { ...baseManaNodes, ...cnmodManaNodes, ...rankP5bManaNodes }
export const serverItemIds = [...new Set([...baseItemIds, ...rankP5bItemIds])]

export const serverEventShops = {
    ...baseEventShops,
    "11": {
        ...(baseEventShops as Record<string, any>)["11"],
        "700099": {
            ...(baseEventShops as Record<string, any>)["11"]?.["700099"],
            ...(rankP5bEventShops as Record<string, any>)["11"]?.["700099"],
        },
    },
}
export const serverEventShopIdMap = { ...baseEventShopIdMap, ...rankP5bEventShopIdMap }
