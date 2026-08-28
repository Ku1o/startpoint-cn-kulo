const test = require("node:test");
const assert = require("node:assert/strict");

const { resolveRogueRoundDrops } = require("../out/lib/quest/finish/rogue-drop-schedule");
const config = require("../assets/rogue_event.json").events["700099"];
const extension = require("../assets/rogue_event_cnmod.json").events["700099"];

function sequence(values) {
    let position = 0;
    return () => {
        assert.ok(position < values.length, "random sequence exhausted");
        return values[position++];
    };
}

test("keeps round 1 at one guaranteed token and a 1% single-ticket roll", () => {
    const missed = resolveRogueRoundDrops(config, 1, sequence([0.01]));
    assert.deepEqual(missed.map(drop => [drop.id, drop.additional_reward_index]), [
        [2370099, 1],
    ]);

    const hit = resolveRogueRoundDrops(config, 1, sequence([0.009]));
    assert.deepEqual(hit.map(drop => [drop.id, drop.additional_reward_index]), [
        [2370099, 1],
        [999013, 9],
    ]);
});

test("uses independent token slots and the final 16-29 +1 percentage-point curve", () => {
    const round16 = resolveRogueRoundDrops(config, 16, sequence([0.50, 0.51, 0.9, 1]));
    assert.equal(round16.filter(drop => drop.id === 2370099).length, 5);

    const round29 = resolveRogueRoundDrops(
        config,
        29,
        sequence([0.63, 0.64, 0.10, 0.14]),
    );
    assert.deepEqual(round29.map(drop => [drop.id, drop.additional_reward_index]), [
        [2370099, 1], [2370099, 2], [2370099, 3], [2370099, 4], [2370099, 5],
        [2370099, 6], [2370099, 8], [999013, 9],
    ]);
});

test("replaces the single ticket with the floor-specific ten-ticket roll every 5 floors", () => {
    const round25 = resolveRogueRoundDrops(
        config,
        25,
        sequence([1, 1, 1, 0.049]),
    );
    assert.equal(round25.some(drop => drop.id === 999013), false);
    assert.equal(round25.some(drop => drop.id === 999014), true);
});

test("does not attach per-round drops to the final floor", () => {
    assert.deepEqual(resolveRogueRoundDrops(config, 30, () => 0), []);
});

test("keeps the final ten-ticket chance identical across base and CN extension configs", () => {
    const base = config.folder_clear_chance.find(reward => reward.id === 999014);
    const extra = extension.folder_clear_chance.find(reward => reward.id === 999014);
    assert.deepEqual(extra, base);
    assert.equal(base.chance, 0.10);
});
