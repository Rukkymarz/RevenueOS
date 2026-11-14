import assert from "node:assert/strict";
import { test } from "node:test";
import { concentricRadius, contrastRatio, isConcentric, isSentenceCase, meetsAA, mergeDesignMd, missingStates,
  requiredPairs, scan, sentenceCase, tokens, UI_STATES } from "../src/index.js";

test("contrast: black on white is 21:1, white on white is 1:1", () => {
  assert.equal(contrastRatio("oklch(0 0 0)", "oklch(1 0 0)"), 21);
  assert.equal(contrastRatio("oklch(1 0 0)", "oklch(1 0 0)"), 1);
});

test("every required token pair meets WCAG AA", () => {
  for (const [fg, bg, kind] of requiredPairs) {
    assert.ok(meetsAA(tokens.color[fg], tokens.color[bg], kind),
      `${fg} on ${bg} is ${contrastRatio(tokens.color[fg], tokens.color[bg])}:1`);
  }
});

test("all token colors are OKLCH", () => {
  for (const v of Object.values(tokens.color)) assert.match(v, /^oklch\(/);
});

test("concentric radius: inner = max(0, outer - padding)", () => {
  assert.equal(concentricRadius(24, 8), 16);
  assert.equal(concentricRadius(6, 12), 0);
  assert.ok(isConcentric(24, 8, 16));
  assert.ok(!isConcentric(24, 8, 24), "same radius inside and out is not concentric");
  assert.throws(() => concentricRadius(-1, 0));
});

test("five mandatory UI states", () => {
  assert.deepEqual([...UI_STATES], ["empty", "loading", "error", "partial", "ideal"]);
  assert.deepEqual(missingStates(["ideal", "loading"]), ["empty", "error", "partial"]);
});

test("sentence case keeps acronyms and brand casing", () => {
  assert.equal(sentenceCase("Connect Your GitHub Account To The API"), "Connect your GitHub account to the API");
  assert.ok(isSentenceCase("Review approvals in the MCP registry"));
  assert.ok(!isSentenceCase("Review Approvals In The Registry"));
});

test("slop scanner flags a default gradient hero and raw hex", () => {
  const f = scan("Hero.tsx", '<section className="bg-gradient-to-r from-purple-500 to-pink-500" style={{color: "#fff"}}>');
  assert.deepEqual(f.map((x) => x.pattern).sort(), ["gradient-hero", "hex-color"]);
  assert.equal(scan("Hero.tsx", '<h1 className="text-fg">Book a deep clean this week</h1>').length, 0);
});

test("DESIGN.md merge adds new tokens but refuses to change committed ones", () => {
  const doc = '# Design\n\n```json design-tokens\n{"radius":{"md":10},"color":{"accent":"oklch(0.52 0.16 255)"}}\n```\n';
  const { document, result } = mergeDesignMd(doc, { radius: { md: 14, lg: 16 }, color: { accent: "oklch(0.6 0.2 30)" } });
  assert.deepEqual(result.added, ["radius.lg"]);
  assert.deepEqual(result.conflicts.map((c) => c.path).sort(), ["color.accent", "radius.md"]);
  assert.match(document, /"md": 10/);
  assert.match(document, /"lg": 16/);
  assert.doesNotMatch(document, /0\.6 0\.2 30/);
});
