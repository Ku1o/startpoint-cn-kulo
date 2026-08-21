require("ts-node/register");

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const {
  handleAutoplayModeChange,
  parseAutoplayModeChange,
} = require("../src/multi/tcp/autoplay-mode.ts");

assert.deepStrictEqual(parseAutoplayModeChange([7, false, true]), {
  autoplayMode: false,
  manualMode: true,
});
assert.strictEqual(parseAutoplayModeChange([7, 0, true]), null);
assert.strictEqual(parseAutoplayModeChange([7, false]), null);

const yourself = { viewerId: 123, autoplayMode: true };
const rosterCopy = { viewerId: 123, autoplayMode: true };
const client = {
  viewerId: 123,
  roomNumber: "654321",
  yourself,
  mates: [rosterCopy, { viewerId: 456, autoplayMode: true }],
};
const broadcasts = [];

assert.deepStrictEqual(
  handleAutoplayModeChange(client, [7, false, true], (roomNumber, message) => {
    broadcasts.push({ roomNumber, message });
  }),
  { autoplayMode: false, manualMode: true },
);
assert.strictEqual(yourself.autoplayMode, false);
assert.strictEqual(rosterCopy.autoplayMode, false);
assert.strictEqual(client.mates[1].autoplayMode, true);
assert.deepStrictEqual(broadcasts, [{
  roomNumber: "654321",
  message: [1, [3, 123, false, true]],
}]);

const lobbySource = fs.readFileSync(
  path.join(__dirname, "..", "src", "multi", "tcp", "lobby.ts"),
  "utf8",
);
assert.match(lobbySource, /case 7:\s*\{[\s\S]*handleAutoplayModeChange\(/);

console.log("multi autoplay mode tests passed");
