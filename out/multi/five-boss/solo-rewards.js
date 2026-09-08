"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.grantFiveBossSoloRewardsSync = void 0;
const item_1 = require("../../data/domains/item");
const rewards_1 = require("./rewards");
/**
 * 单人打五重决战(2026-09-05 作者:"单人那还是有奖励")的结算发放。
 *
 * 单人 start/finish 走 singleBattleQuest 的普通领主战链路,不经过 five-boss runtime,
 * 所以模式材料(图纸/结晶/证/心核)要在这里按同一张 reward plan 发,倍率固定 1
 * (单人没有 AUTO 关闭双倍那套 boost 语义)。
 */
function grantFiveBossSoloRewardsSync(input) {
    var _a;
    const give = (_a = input.givePlayerItemSync) !== null && _a !== void 0 ? _a : item_1.givePlayerItemSync;
    const plan = (0, rewards_1.buildFiveBossGauntletRewardPlan)({
        firstClear: input.firstClear,
        rewardMultiplier: 1,
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
