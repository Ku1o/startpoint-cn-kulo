require("ts-node/register/transpile-only");

const assert = require("assert");
const fs = require("fs");
const Module = require("module");
const path = require("path");

let sessionResult = { accountId: 7 };
let requestedSessionKey;
const originalLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (parent?.filename.endsWith("lounge.ts") && request === "../../data/domains/session") {
    return {
      getSession: async (key) => {
        requestedSessionKey = key;
        return sessionResult;
      },
    };
  }
  if (parent?.filename.endsWith("lounge.ts") && request === "../../utils") {
    return {
      generateDataHeaders: (headers) => ({ result_code: 1, ...headers }),
    };
  }
  return originalLoad.call(this, request, parent, isMain);
};

const loungeModule = require("../src/routes/api/lounge.ts");
Module._load = originalLoad;
const { buildLoungeListData } = loungeModule;

assert.deepStrictEqual(buildLoungeListData(), {
  lounge_list: [],
});

let routePath;
let routeHandler;
const plugin = loungeModule.default;

function makeReply() {
  return {
    statusCode: null,
    headers: {},
    payload: undefined,
    status(code) {
      this.statusCode = code;
      return this;
    },
    header(name, value) {
      this.headers[name] = value;
      return this;
    },
    send(payload) {
      this.payload = payload;
      return payload;
    },
  };
}

(async () => {
  await plugin({
    post(pathname, handler) {
      routePath = pathname;
      routeHandler = handler;
    },
  });

  assert.strictEqual(routePath, "/get_list");

  const okReply = makeReply();
  await routeHandler({ body: { viewer_id: 297417490, use_case: 1 } }, okReply);
  assert.strictEqual(requestedSessionKey, "297417490");
  assert.strictEqual(okReply.statusCode, 200);
  assert.strictEqual(okReply.headers["content-type"], "application/x-msgpack");
  assert.deepStrictEqual(okReply.payload, {
    data_headers: { result_code: 1, viewer_id: 297417490 },
    data: { lounge_list: [] },
  });

  const invalidReply = makeReply();
  await routeHandler({ body: { viewer_id: 0 } }, invalidReply);
  assert.strictEqual(invalidReply.statusCode, 400);

  sessionResult = null;
  const missingSessionReply = makeReply();
  await routeHandler({ body: { viewer_id: 297417490 } }, missingSessionReply);
  assert.strictEqual(missingSessionReply.statusCode, 400);

  const root = path.join(__dirname, "..");
  const cnServerSource = fs.readFileSync(path.join(root, "src", "cn-server.ts"), "utf8");
  const legacyServerSource = fs.readFileSync(path.join(root, "src", "server.ts"), "utf8");

  assert.match(cnServerSource, /loungeApiPlugin[\s\S]*`\$\{apiPrefix\}\/lounge`/);
  assert.match(legacyServerSource, /loungeApiPlugin[\s\S]*`\$\{apiPrefix\}\/lounge`/);

  console.log("lounge get_list tests passed");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
