import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { argsHash, canonicalize } from "../src/canonical.js";

const vectors = JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "..", "fixtures-canonical", "vectors.json"), "utf8")) as
  Array<{ input: unknown; canonical: string; sha256: string }>;

test("RFC 8785 vectors match the Python implementation byte for byte", () => {
  assert.ok(vectors.length >= 8);
  for (const v of vectors) {
    assert.equal(canonicalize(v.input), v.canonical);
    assert.equal(argsHash(v.input), v.sha256);
  }
});

test("key order and whitespace do not change the hash; one changed byte does", () => {
  assert.equal(argsHash({ b: 1, a: [1, 2] }), argsHash({ a: [1, 2], b: 1 }));
  assert.notEqual(argsHash({ to: "a@b.co" }), argsHash({ to: "a@b.cO" }));
  assert.throws(() => canonicalize({ x: Number.NaN }));
});

test("package health self-check", async () => {
  const { health } = await import("../src/health.js");
  const h = health();
  assert.equal(h.status, "ok");
  assert.equal(h.checks.contracts, "15");
});
