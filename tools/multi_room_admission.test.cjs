require("ts-node/register");

const assert = require("assert");

const {
  RoomAdmissionRegistry,
} = require("../src/multi/room/admission.ts");

const registry = new RoomAdmissionRegistry(1_000);
const room = "bell-room";
const generation = 0;
const host = [100];

assert.strictEqual(registry.getOccupancy(room, generation, host, 0), 1);
assert.strictEqual(registry.reserve(room, generation, 200, host, 3, 0), true);
assert.strictEqual(registry.getOccupancy(room, generation, host, 0), 2);

// Retrying the same HTTP selection renews one reservation instead of taking
// another seat.
assert.strictEqual(registry.reserve(room, generation, 200, host, 3, 100), true);
assert.strictEqual(registry.getOccupancy(room, generation, host, 100), 2);

assert.strictEqual(registry.reserve(room, generation, 300, host, 3, 100), true);
assert.strictEqual(registry.getOccupancy(room, generation, host, 100), 3);
assert.strictEqual(registry.reserve(room, generation, 400, host, 3, 100), false);

// Consuming a reservation at TCP admission and adding that viewer to the live
// roster keeps the room full without double-counting the same player.
assert.strictEqual(registry.consume(room, generation, 200, 100), true);
assert.strictEqual(registry.getOccupancy(room, generation, [100, 200], 100), 3);
assert.strictEqual(registry.reserve(room, generation, 400, [100, 200], 3, 100), false);

registry.clearRoom(room);
assert.strictEqual(registry.getOccupancy(room, generation, host, 100), 1);

// Failed clients do not hold a seat forever, and reservations never leak into
// a rematch generation.
assert.strictEqual(registry.reserve(room, generation, 200, host, 3, 0), true);
assert.strictEqual(registry.has(room, generation, 200, 999), true);
assert.strictEqual(registry.has(room, generation, 200, 1_000), false);
assert.strictEqual(registry.reserve(room, generation, 200, host, 3, 2_000), true);
assert.strictEqual(registry.getOccupancy(room, generation + 1, host, 2_000), 1);

console.log("multi_room_admission tests passed");
