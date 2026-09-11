"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.grantFiveBossSoloRewardsSync = void 0;
const item_1 = require("../../data/domains/item");
const rewards_1 = require("./rewards");
/**
 * 单人打五重决战(2026-09-05 作者:"单人那还是有奖励")的结算发放。
 *
 * 单人 start/finish 走 singleBattleQuest 的普通领主战链路,不经过 five-boss runtime,
 * 按整轮 AUTO 记录决定模式材料倍率；图纸和首通凭证仍遵循固定奖励口径。
 */
function grantFiveBossSoloRewardsSync(input) {
    var _a, _b;
    const give = (_a = input.givePlayerItemSync) !== null && _a !== void 0 ? _a : item_1.givePlayerItemSync;
    const plan = (0, rewards_1.buildFiveBossGauntletRewardPlan)({
        firstClear: input.firstClear,
        rewardMultiplier: (_b = input.rewardMultiplier) !== null && _b !== void 0 ? _b : 1,
        randomFloat: input.randomFloat,
    });
    const items = {};
    const granted = [];
    for (const item of plan.items) {
        if (item.amount <= 0)
            continue;
        items[item.itemId] = give(input.playerId, item.itemId, item.amount);
        granted.push({ itemId: item.itemId, amount: item.amount });
    }
    return {
        items,
        dropAdditionalRewardIds: (0, rewards_1.buildFiveBossAdditionalRewardDrops)(granted),
        granted,
    };
}
exports.grantFiveBossSoloRewardsSync = grantFiveBossSoloRewardsSync;
