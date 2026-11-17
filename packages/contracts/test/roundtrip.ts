/**
 * Contract round trip, TypeScript side. Run in three steps by CI:
 *   ts1  validate every fixture; valid -> write canonical output to out/ts; invalid must be rejected
 *   (python step: tests/test_roundtrip.py validates fixtures + out/ts, writes out/py)
 *   ts2  every out/py document must parse with zod and equal the original fixture
 */
import assert from "node:assert/strict";
import { mkdirSync, readdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { contracts, type ContractName } from "../src/schemas.js";

const pkg = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const fixtures = join(pkg, "fixtures");
const phase = process.argv[2];

function load(p: string): unknown { return JSON.parse(readFileSync(p, "utf8")); }
function sorted(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(sorted);
  if (v && typeof v === "object") return Object.fromEntries(Object.keys(v).sort().map((k) => [k, sorted((v as Record<string, unknown>)[k])]));
  return v;
}

let checked = 0;
for (const name of readdirSync(fixtures)) {
  const schema = contracts[name as ContractName];
  assert.ok(schema, `fixtures/${name} has no contract`);
  const validDir = join(fixtures, name, "valid");
  const invalidDir = join(fixtures, name, "invalid");
  if (phase === "ts1") {
    assert.ok(existsSync(validDir) && existsSync(invalidDir), `${name} needs valid/ and invalid/ fixtures`);
    for (const f of readdirSync(validDir)) {
      const parsed = schema.parse(load(join(validDir, f)));
      mkdirSync(join(pkg, "out", "ts", name), { recursive: true });
      writeFileSync(join(pkg, "out", "ts", name, f), JSON.stringify(sorted(parsed)));
      checked++;
    }
    for (const f of readdirSync(invalidDir)) {
      const r = schema.safeParse(load(join(invalidDir, f)));
      assert.equal(r.success, false, `${name}/invalid/${f} was accepted by zod`);
      checked++;
    }
  } else if (phase === "ts2") {
    for (const f of readdirSync(validDir)) {
      const fromPy = join(pkg, "out", "py", name, f);
      assert.ok(existsSync(fromPy), `python did not emit ${name}/${f}`);
      const reparsed = schema.parse(load(fromPy));
      assert.deepEqual(sorted(reparsed), sorted(schema.parse(load(join(validDir, f)))), `${name}/${f} changed crossing TS -> Py -> TS`);
      checked++;
    }
  } else {
    throw new Error("usage: roundtrip.js ts1|ts2");
  }
}
assert.ok(checked > 0, "no fixtures checked");
console.log(`contracts round trip ${phase}: ${checked} checks passed`);
