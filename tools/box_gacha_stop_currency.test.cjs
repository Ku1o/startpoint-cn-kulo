require("ts-node/register");

const assert = require("assert");

const { drawBoxGachaSync } = require("../src/lib/gacha.ts");
const {
  BoxGachaRewardTier,
  BoxGachaRewardType,
} = require("../src/lib/types/box-gacha.ts");

const featuredOnlyBox = {
  "1001": {
    type: BoxGachaRewardType.EMPTY,
    count: 0,
    available: 3,
    tier: BoxGachaRewardTier.FEATURED,
  },
};

const stoppedResult = drawBoxGachaSync(featuredOnlyBox, [], 3, true);
assert.strictEqual(stoppedResult.drawCount, 1);
assert.strictEqual(
  stoppedResult.rewards.reduce((sum, reward) => sum + reward.number, 0),
  1,
);

const fullResult = drawBoxGachaSync(featuredOnlyBox, [], 3, false);
assert.strictEqual(fullResult.drawCount, 3);
assert.strictEqual(
  fullResult.rewards.reduce((sum, reward) => sum + reward.number, 0),
  3,
);

const currencyBefore = 10_000;
const currencyPerDraw = 10;
assert.strictEqual(currencyBefore - stoppedResult.drawCount * currencyPerDraw, 9_990);
assert.strictEqual(currencyBefore - fullResult.drawCount * currencyPerDraw, 9_970);

console.log("box_gacha_stop_currency tests passed");
