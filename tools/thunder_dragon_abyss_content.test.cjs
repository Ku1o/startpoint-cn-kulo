require("ts-node/register");

const assert = require("assert");
const Fastify = require("fastify");

const characters = require("../assets/character.json");
const characterRows = require("../assets/cdndata/character.json");
const characterTextRows = require("../assets/cdndata/character_text.json");
const gachaRows = require("../assets/cdndata/gacha.json");
const featureRows = require("../assets/cdndata/gacha_feature_content.json");
const itemIds = require("../assets/item_ids.json");
const itemLookup = require("../assets/item_lookup_cnmod.json");
const manaBoard = require("../assets/mana_board_cnmod.json");
const characterTable = require("../docs/generated/character_table.json");
const lookupRoutes = require("../src/routes/web_api/lookup.ts").default;
const {
  getEventShopItemsSync,
  getGachaSync,
  getRushEventFolderClearRewards,
  getCharacterManaNodesSync,
  getManaNodeAwakeCost,
} = require("../src/lib/assets.ts");
const { getGachaTicketCost } = require("../src/lib/gacha-ticket.ts");
const { GACHA_EXEC_TYPES } = require("../src/lib/gacha-rules.ts");

const THUNDER_DRAGON_ID = 139998;
const ABYSS_GACHA_ID = 990001;
const SINGLE_TICKET_ID = 999013;
const MULTI_TICKET_ID = 999014;
const ULTIMATE_TOTEM_ID = 2370097;

assert.deepStrictEqual(characters[String(THUNDER_DRAGON_ID)], {
  name: "拉姆斯",
  rarity: 5,
  element: 2,
  skill_count: 6,
});
assert.strictEqual(characterRows[String(THUNDER_DRAGON_ID)][0][0], "cnmod_thunder_dragon_ascendant");
assert.strictEqual(characterRows[String(THUNDER_DRAGON_ID)][0][18], "碧海雷鸣的共振");
assert.strictEqual(characterTextRows[String(THUNDER_DRAGON_ID)][0][0], "拉姆斯");
assert.strictEqual(characterTextRows[String(THUNDER_DRAGON_ID)][0][3], "鸣彻碧海的雷龙");
assert.strictEqual(characterTextRows[String(THUNDER_DRAGON_ID)][0][4], "碧海雷潮");

const adminCharacter = characterTable.find((entry) => entry.id === THUNDER_DRAGON_ID);
assert.deepStrictEqual(adminCharacter, {
  id: THUNDER_DRAGON_ID,
  name: "拉姆斯",
  title: "鸣彻碧海的雷龙",
  rarity: "5★",
  element: "雷",
  gender: "女性",
  race: "Dragon",
});

const swimExAdminCharacter = characterTable.find((entry) => entry.id === 139997);
assert.deepStrictEqual(swimExAdminCharacter, {
  id: 139997,
  name: "莉莉丝",
  title: "雷雨的夏日公主",
  rarity: "5★",
  element: "雷",
  gender: "女性",
  race: "Human,Element",
});
assert.ok(itemIds.includes(SINGLE_TICKET_ID));
assert.ok(itemIds.includes(MULTI_TICKET_ID));
assert.strictEqual(itemLookup[String(SINGLE_TICKET_ID)], "深渊单抽券");
assert.strictEqual(itemLookup[String(MULTI_TICKET_ID)], "深渊十连券");
assert.strictEqual(itemLookup[String(ULTIMATE_TOTEM_ID)], "究极图腾");

const cdnGachaRow = gachaRows[String(ABYSS_GACHA_ID)][0];
assert.strictEqual(cdnGachaRow[1], "深渊限定扭蛋");
assert.strictEqual(cdnGachaRow[4], "2");
assert.strictEqual(cdnGachaRow[27], String(SINGLE_TICKET_ID));
assert.strictEqual(cdnGachaRow[28], String(MULTI_TICKET_ID));
assert.strictEqual(
  featureRows[String(ABYSS_GACHA_ID)]["1"][0][1],
  "dynamic/gacha_banner/cnmod_abyss_limited_gacha",
);

const gacha = getGachaSync(ABYSS_GACHA_ID);
assert.ok(gacha);
assert.strictEqual(gacha.pageKind, 2);
assert.strictEqual(gacha.onceTicketItemId, SINGLE_TICKET_ID);
assert.strictEqual(gacha.tenTicketItemId, MULTI_TICKET_ID);
assert.strictEqual(gacha.wildcardTicketAvailable, false);
assert.deepStrictEqual(gacha.rankRates, {
  normal: [150, 350, 500],
  multiGuarantee: [150, 850],
});
assert.deepStrictEqual(
  Object.fromEntries(Object.entries(gacha.pool).map(([rank, entries]) => [rank, entries.length])),
  { "1": 245, "2": 144, "3": 78 },
);
const fiveStars = gacha.pool["1"];
const rateUps = fiveStars.filter((entry) => entry.isRateUp).map((entry) => entry.id);
assert.deepStrictEqual(
  rateUps,
  [129999, 139997, 139998, 139999, 149998, 149999, 169998, 169999, 179999],
);
assert.strictEqual(fiveStars.find((entry) => entry.id === 139997)?.isExchangeable, false);
for (const id of [141129, 161141, 123001, 131182]) {
  assert.strictEqual(fiveStars.find((entry) => entry.id === id)?.isExchangeable, true);
}
assert.deepStrictEqual(
  getGachaTicketCost(GACHA_EXEC_TYPES.CONFIGURED_SINGLE_TICKET, 1, gacha),
  { itemId: SINGLE_TICKET_ID, useTicketCount: 1, pullCount: 1 },
);
assert.deepStrictEqual(
  getGachaTicketCost(GACHA_EXEC_TYPES.CONFIGURED_MULTI_TICKET, 1, gacha),
  { itemId: MULTI_TICKET_ID, useTicketCount: 1, pullCount: 10 },
);
assert.strictEqual(
  getGachaTicketCost(GACHA_EXEC_TYPES.WILDCARD_CHARACTER_SINGLE_TICKET, 1, gacha),
  null,
);

const shop = getEventShopItemsSync(11, 700099);
assert.deepStrictEqual(shop["9700116"], {
  costs: [{ id: 2370099, amount: 5 }],
  rewards: [{ type: 0, id: SINGLE_TICKET_ID, count: 1 }],
  availableFrom: "2000-01-01 00:00:00",
  availableUntil: "2099-12-31 23:59:59",
  stock: 9999,
});
assert.deepStrictEqual(shop["9700117"], {
  costs: [{ id: 2370099, amount: 50 }],
  rewards: [{ type: 0, id: MULTI_TICKET_ID, count: 1 }],
  availableFrom: "2000-01-01 00:00:00",
  availableUntil: "2099-12-31 23:59:59",
  stock: 9999,
});

const fantasyTicketProduct = {
  costs: [{ id: ULTIMATE_TOTEM_ID, amount: 1 }],
  rewards: [{ type: 0, id: MULTI_TICKET_ID, count: 3 }],
  availableFrom: "2000-01-01 12:00:00",
  availableUntil: "2099-12-31 11:59:59",
  stock: 9999,
};
assert.deepStrictEqual(getEventShopItemsSync(0, 300098)["9700212"], fantasyTicketProduct);
assert.deepStrictEqual(getEventShopItemsSync(11, 700098)["9700312"], fantasyTicketProduct);

const boardOne = getCharacterManaNodesSync(THUNDER_DRAGON_ID, 1);
const boardTwo = getCharacterManaNodesSync(THUNDER_DRAGON_ID, 2);
assert.strictEqual(Object.keys(boardOne).length, 23);
assert.strictEqual(Object.keys(boardTwo).length, 18);
assert.ok([...Object.keys(boardOne), ...Object.keys(boardTwo)].every((id) => id.startsWith("279996")));
assert.deepStrictEqual(Object.keys(manaBoard[String(THUNDER_DRAGON_ID)]), ["1", "2"]);
assert.ok(getManaNodeAwakeCost(THUNDER_DRAGON_ID, Object.keys(boardOne)[0], 5));

const originalRandom = Math.random;
try {
  Math.random = () => 0.01;
  for (let clear = 0; clear < 2; clear += 1) {
    const rewards = getRushEventFolderClearRewards(700099, 1);
    assert.strictEqual(rewards.find((reward) => reward.id === MULTI_TICKET_ID)?.count, 1);
  }
  Math.random = () => 0.99;
  const miss = getRushEventFolderClearRewards(700099, 1);
  assert.strictEqual(miss.some((reward) => reward.id === MULTI_TICKET_ID), false);
} finally {
  Math.random = originalRandom;
}

(async () => {
  const app = Fastify();
  await app.register(lookupRoutes, { prefix: "/api/lookup" });
  const itemsResponse = await app.inject({ method: "GET", url: "/api/lookup/items" });
  assert.strictEqual(itemsResponse.statusCode, 200);
  const items = itemsResponse.json();
  assert.strictEqual(items[String(SINGLE_TICKET_ID)], "深渊单抽券");
  assert.strictEqual(items[String(MULTI_TICKET_ID)], "深渊十连券");
  assert.strictEqual(items[String(ULTIMATE_TOTEM_ID)], "究极图腾");
  const charactersResponse = await app.inject({ method: "GET", url: "/api/lookup/characters" });
  assert.strictEqual(charactersResponse.statusCode, 200);
  assert.strictEqual(charactersResponse.json()[String(THUNDER_DRAGON_ID)].name, "拉姆斯");
  await app.close();
  console.log("thunder dragon / abyss content tests passed");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
