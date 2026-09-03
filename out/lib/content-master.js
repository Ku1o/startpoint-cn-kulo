"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
var _a, _b;
Object.defineProperty(exports, "__esModule", { value: true });
exports.serverEventShopIdMap = exports.serverEventShops = exports.serverItemIds = exports.serverManaNodes = exports.serverGachas = exports.degreeDefinitions = exports.cdnCharacterTexts = exports.cdnCharacters = exports.serverCharacters = void 0;
const character_json_1 = __importDefault(require("../../assets/character.json"));
const character_rank_p5b_json_1 = __importDefault(require("../../assets/character_rank_p5b.json"));
const character_json_2 = __importDefault(require("../../assets/cdndata/character.json"));
const character_rank_p5b_json_2 = __importDefault(require("../../assets/cdndata/character_rank_p5b.json"));
const character_text_json_1 = __importDefault(require("../../assets/cdndata/character_text.json"));
const character_text_rank_p5b_json_1 = __importDefault(require("../../assets/cdndata/character_text_rank_p5b.json"));
const degree_json_1 = __importDefault(require("../../assets/degree.json"));
const degree_rank_p5b_json_1 = __importDefault(require("../../assets/degree_rank_p5b.json"));
const event_item_shop_json_1 = __importDefault(require("../../assets/event_item_shop.json"));
const event_item_shop_rank_p5b_json_1 = __importDefault(require("../../assets/event_item_shop_rank_p5b.json"));
const event_item_shop_id_map_json_1 = __importDefault(require("../../assets/event_item_shop_id_map.json"));
const event_item_shop_id_map_rank_p5b_json_1 = __importDefault(require("../../assets/event_item_shop_id_map_rank_p5b.json"));
const gacha_json_1 = __importDefault(require("../../assets/gacha.json"));
const gacha_cnmod_json_1 = __importDefault(require("../../assets/gacha_cnmod.json"));
const gacha_rank_p5b_json_1 = __importDefault(require("../../assets/gacha_rank_p5b.json"));
const item_ids_json_1 = __importDefault(require("../../assets/item_ids.json"));
const item_ids_rank_p5b_json_1 = __importDefault(require("../../assets/item_ids_rank_p5b.json"));
const mana_node_json_1 = __importDefault(require("../../assets/mana_node.json"));
const mana_node_cnmod_json_1 = __importDefault(require("../../assets/mana_node_cnmod.json"));
const mana_node_rank_p5b_json_1 = __importDefault(require("../../assets/mana_node_rank_p5b.json"));
exports.serverCharacters = Object.assign(Object.assign({}, character_json_1.default), character_rank_p5b_json_1.default);
exports.cdnCharacters = Object.assign(Object.assign({}, character_json_2.default), character_rank_p5b_json_2.default);
exports.cdnCharacterTexts = Object.assign(Object.assign({}, character_text_json_1.default), character_text_rank_p5b_json_1.default);
exports.degreeDefinitions = Object.assign(Object.assign({}, degree_json_1.default), degree_rank_p5b_json_1.default);
exports.serverGachas = Object.assign(Object.assign(Object.assign({}, gacha_json_1.default), gacha_cnmod_json_1.default), gacha_rank_p5b_json_1.default);
exports.serverManaNodes = Object.assign(Object.assign(Object.assign({}, mana_node_json_1.default), mana_node_cnmod_json_1.default), mana_node_rank_p5b_json_1.default);
exports.serverItemIds = [...new Set([...item_ids_json_1.default, ...item_ids_rank_p5b_json_1.default])];
// Five Boss is intentionally dormant.  Keep its raw definitions for a future
// opening, but do not expose its Death Bringer exchange through the effective
// runtime shop view while the matching client row is absent.
const DORMANT_EVENT_SHOP_ITEM_IDS = new Set(["59001010"]);
const mergedEventShops = Object.assign(Object.assign({}, event_item_shop_json_1.default), { "11": Object.assign(Object.assign({}, event_item_shop_json_1.default["11"]), { "700099": Object.assign(Object.assign({}, (_a = event_item_shop_json_1.default["11"]) === null || _a === void 0 ? void 0 : _a["700099"]), (_b = event_item_shop_rank_p5b_json_1.default["11"]) === null || _b === void 0 ? void 0 : _b["700099"]) }) });
exports.serverEventShops = Object.fromEntries(Object.entries(mergedEventShops).map(([eventType, events]) => [
    eventType,
    Object.fromEntries(Object.entries(events).map(([eventId, items]) => [
        eventId,
        Object.fromEntries(Object.entries(items).filter(([itemId]) => !DORMANT_EVENT_SHOP_ITEM_IDS.has(itemId))),
    ])),
]));
exports.serverEventShopIdMap = Object.fromEntries(Object.entries(Object.assign(Object.assign({}, event_item_shop_id_map_json_1.default), event_item_shop_id_map_rank_p5b_json_1.default)).filter(([itemId]) => !DORMANT_EVENT_SHOP_ITEM_IDS.has(itemId)));
