'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { verifyFrameEquality } = require('../gacha_skill_media.cjs');
test('equivalent native frames retain every value and order', () => {
  const a = [{ draws: [[1, 2, 3, 4, 5, 6, .5, 'add']] }];
  verifyFrameEquality(a, structuredClone(a), 'cover');
  const b = structuredClone(a); b[0].draws[0][6] = .6;
  assert.throws(() => verifyFrameEquality(a, b, 'cover'), /^Error: Movie frame differs: cover, index 0$/);
});
test('representation mismatch reports location without formatting a full diff', () => {
  const a = [{ draws: Array.from({ length: 10000 }, (_, i) => ({ x: i, y: i + 1 })) }];
  const b = [{ draws: a[0].draws.map(p => [p.x, p.y]) }];
  let failure;
  try { verifyFrameEquality(a, b, 'poster'); } catch (error) { failure = error; }
  assert(failure && failure.message.length < 100);
  assert(!('actual' in failure) && !('expected' in failure));
  assert.throws(() => verifyFrameEquality(a, [], 'poster'), /count differs/);
});
