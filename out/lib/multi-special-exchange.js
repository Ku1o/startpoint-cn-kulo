"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.isMultiSpecialExchangeCharacter = exports.getMultiSpecialExchangeCampaignDefinition = void 0;
const multi_special_exchange_campaign_character_json_1 = __importDefault(require("../../assets/multi_special_exchange_campaign_character.json"));
// CN master/campaign/multi_special_exchange currently contains campaigns 1-3.
// Campaigns 4-5 use the same sequential ticket allocation in later official
// data; campaign 5 is also present in the repository's captured API response.
const CAMPAIGNS = new Map([
    [1, { campaignId: 1, ticketItemIds: [980001, 980002, 980003] }],
    [2, { campaignId: 2, ticketItemIds: [980004] }],
    [3, { campaignId: 3, ticketItemIds: [980005] }],
    [4, { campaignId: 4, ticketItemIds: [980006] }],
    [5, { campaignId: 5, ticketItemIds: [980007] }],
]);
// Exchangeable characters per ticket item, mirrored from the client master
// table master/campaign/multi_special_exchange/multi_special_exchange_campaign_character
// (ticket item id -> character ids). The client builds its selection list from
// the same table, so only these pairs can be chosen in the exchange screen.
// Tickets without a client list (980006/980007) have no exchangeable characters.
const EXCHANGEABLE_CHARACTERS = new Map(Object.entries(multi_special_exchange_campaign_character_json_1.default)
    .map(([ticketItemId, characterIds]) => [Number(ticketItemId), new Set(characterIds)]));
function getMultiSpecialExchangeCampaignDefinition(campaignId) {
    var _a;
    return (_a = CAMPAIGNS.get(campaignId)) !== null && _a !== void 0 ? _a : null;
}
exports.getMultiSpecialExchangeCampaignDefinition = getMultiSpecialExchangeCampaignDefinition;
function isMultiSpecialExchangeCharacter(ticketItemId, characterId) {
    var _a, _b;
    return (_b = (_a = EXCHANGEABLE_CHARACTERS.get(ticketItemId)) === null || _a === void 0 ? void 0 : _a.has(characterId)) !== null && _b !== void 0 ? _b : false;
}
exports.isMultiSpecialExchangeCharacter = isMultiSpecialExchangeCharacter;
