import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { chmodSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, test } from "node:test";
import type { INestApplication } from "@nestjs/common";
import { argsHash } from "@revenueos/contracts";
import { authenticate, loadPrincipals } from "../src/auth.js";
import { preview } from "../src/approvals.js";
import { bootstrap } from "../src/main.js";

const AGENT_TOKEN = "agent-token-0123456789abcdef";
const HUMAN_TOKEN = "human-token-0123456789abcdef";
const sha = (t: string) => createHash("sha256").update(t).digest("hex");
let app: INestApplication;
let base: string;
let keychain: string;

before(async () => {
  delete process.env.PGHOST;
  keychain = mkdtempSync(join(tmpdir(), "kc-"));
  const file = join(keychain, "api-principals");
  writeFileSync(file, JSON.stringify([
    { token_sha256: sha(AGENT_TOKEN), principal: "agent:probe", roles: ["requester"] },
    { token_sha256: sha(HUMAN_TOKEN), principal: "human:christine", roles: ["approver", "auditor"] },
  ]));
  chmodSync(file, 0o600);
  process.env.REVENUEOS_KEYCHAIN_DIR = keychain;
  app = await bootstrap(0);
  const addr = app.getHttpServer().address();
  base = `http://127.0.0.1:${typeof addr === "object" && addr ? addr.port : 0}`;
});
after(async () => { await app.close(); });

const post = (path: string, token: string | null, body: unknown) => fetch(`${base}${path}`, {
  method: "POST", body: JSON.stringify(body),
  headers: { "content-type": "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) },
});
const TASK = "7a1c2e30-0002-4000-8000-000000000001";
const create = { task_id: TASK, server: "allmail", tool: "mail_send", args: { to: "a@b.co" }, risk_class: "high" };

test("no token and unknown token are 401", async () => {
  assert.equal((await post("/v1/approvals", null, create)).status, 401);
  assert.equal((await post("/v1/approvals", "x".repeat(32), create)).status, 401);
});

test("roles are enforced: an agent cannot decide, a human cannot request", async () => {
  const id = "7a1c2e30-0009-4000-8000-000000000001";
  const r1 = await post(`/v1/approvals/${id}/decision`, AGENT_TOKEN, { approve: true });
  assert.equal(r1.status, 403);
  assert.match(((await r1.json()) as { error: string }).error, /approver/);
  assert.equal((await post("/v1/approvals", HUMAN_TOKEN, create)).status, 403);
  assert.equal((await fetch(`${base}/v1/approvals`, { headers: { authorization: `Bearer ${AGENT_TOKEN}` } })).status, 403);
});

test("contract violations are 400 before touching the database", async () => {
  const r = await post("/v1/approvals", AGENT_TOKEN, { ...create, risk_class: "low" });
  assert.equal(r.status, 400);
  assert.equal(((await r.json()) as { error: string }).error, "contract violation");
  assert.equal((await post("/v1/approvals", AGENT_TOKEN, { ...create, ttl_s: 7200 })).status, 400);
  assert.equal((await post("/v1/approvals/not-a-uuid/consume", AGENT_TOKEN, { args: {} })).status, 400);
});

test("a valid request without a database fails closed (503)", async () => {
  assert.equal((await post("/v1/approvals", AGENT_TOKEN, create)).status, 503);
});

test("principals file readable by others is refused", () => {
  const dir = mkdtempSync(join(tmpdir(), "kc-"));
  writeFileSync(join(dir, "api-principals"), "[]");
  chmodSync(join(dir, "api-principals"), 0o644);
  assert.throws(() => loadPrincipals(dir), /must not be readable/);
  assert.deepEqual(loadPrincipals(mkdtempSync(join(tmpdir(), "none-"))), []);
});

test("authenticate matches only the exact token", () => {
  const entries = loadPrincipals(keychain);
  assert.equal(authenticate(`Bearer ${HUMAN_TOKEN}`, entries)?.principal, "human:christine");
  assert.equal(authenticate(`Bearer ${HUMAN_TOKEN}x`, entries), null);
  assert.equal(authenticate(`Basic ${HUMAN_TOKEN}`, entries), null);
});

test("preview redacts secret-looking fields and truncates", () => {
  const p = preview({ to: "a@b.co", password: "hunter2", api_key: "k", body: "x".repeat(300), list: [1], n: 3 });
  assert.equal(p.password, "[redacted]");
  assert.equal(p.api_key, "[redacted]");
  assert.equal((p.body as string).length, 201);
  assert.equal(p.list, "[array]");
  assert.equal(p.n, 3);
});

test("args hash is the RFC 8785 hash shared with Python", () => {
  assert.equal(argsHash({ b: 1, a: [true, null, "x"] }), sha('{"a":[true,null,"x"],"b":1}'));
});
