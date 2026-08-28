const test = require("node:test");
const assert = require("node:assert/strict");

const {
    classifyDeepAbyssFolderReset,
    classifyDeepAbyssFolderSelection,
    isStaleDeepAbyssEndlessFolderLock,
} = require("../out/lib/rush-event-folder-lock");

test("repairs only the persisted Deep Abyss endless folder lock", () => {
    assert.equal(isStaleDeepAbyssEndlessFolderLock(700099, 2), true);
    assert.equal(isStaleDeepAbyssEndlessFolderLock(700099, 1), false);
    assert.equal(isStaleDeepAbyssEndlessFolderLock(700099, null), false);
    assert.equal(isStaleDeepAbyssEndlessFolderLock(700098, 2), false);
    assert.equal(isStaleDeepAbyssEndlessFolderLock(700001, 2), false);
});

test("keeps Deep Abyss endless playable without treating it as a regular lock", () => {
    assert.equal(classifyDeepAbyssFolderSelection(700099, 1), "standard");
    assert.equal(classifyDeepAbyssFolderSelection(700099, 2), "endless_compat");
    assert.equal(classifyDeepAbyssFolderSelection(700099, 3), "invalid");
});

test("does not change folder handling for other Rush events", () => {
    assert.equal(classifyDeepAbyssFolderSelection(700098, 1), "standard");
    assert.equal(classifyDeepAbyssFolderSelection(700098, 2), "standard");
    assert.equal(classifyDeepAbyssFolderSelection(700001, 4), "standard");
});

test("always restarts the Deep Abyss finite folder from the first round", () => {
    assert.equal(classifyDeepAbyssFolderReset(700099), "restart_from_first");
});

test("keeps the native reset behaviour for every other Rush event", () => {
    assert.equal(classifyDeepAbyssFolderReset(700098), "native");
    assert.equal(classifyDeepAbyssFolderReset(700001), "native");
});
