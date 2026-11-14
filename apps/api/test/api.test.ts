import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import type { INestApplication } from "@nestjs/common";
import { HealthResponse } from "@revenueos/contracts";
import { bootstrap } from "../src/main.js";

let app: INestApplication;
let base: string;

before(async () => {
  delete process.env.PGHOST;
  app = await bootstrap(0);
  const addr = app.getHttpServer().address();
  base = `http://127.0.0.1:${typeof addr === "object" && addr ? addr.port : 0}`;
});
after(async () => { await app.close(); });

test("GET /health returns a contract-valid body", async () => {
  const r = await fetch(`${base}/health`);
  assert.equal(r.status, 200);
  const body = HealthResponse.parse(await r.json());
  assert.equal(body.service, "api");
});

test("POST /v1/probe rejects a payload that violates the contract", async () => {
  const r = await fetch(`${base}/v1/probe`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ task_id: "not-a-uuid", agent_id: "x", message: "hi" }),
  });
  assert.equal(r.status, 400);
  const body = (await r.json()) as { error?: string; issues?: unknown[] };
  assert.equal(body.error, "contract violation");
  assert.ok(Array.isArray(body.issues) && body.issues.length > 0, "zod issues are returned to the caller");
});
