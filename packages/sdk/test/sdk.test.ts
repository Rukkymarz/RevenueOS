import assert from "node:assert/strict";
import { test } from "node:test";
import { RevenueOSClient } from "../src/index.js";

const fake = (status: number, body: unknown): typeof fetch =>
  (async () => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } })) as typeof fetch;

test("health response is validated against the contract", async () => {
  const ok = new RevenueOSClient("http://api", fake(200, { service: "api", status: "ok", version: "0.1.0", checks: {} }));
  assert.equal((await ok.health()).status, "ok");
  const bad = new RevenueOSClient("http://api", fake(200, { service: "api", status: "great", version: "0.1.0", checks: {} }));
  await assert.rejects(bad.health());
});

test("probe request is rejected before it leaves the client when invalid", async () => {
  const c = new RevenueOSClient("http://api", fake(200, {}));
  await assert.rejects(c.probe({ task_id: "nope", agent_id: "nope", message: "hi" }));
});
