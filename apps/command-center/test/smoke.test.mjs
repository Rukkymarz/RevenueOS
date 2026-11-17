// Runs after `next build`: the production build must contain the rendered shell and the health route.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";

test("next build produced the shell page and health route", () => {
  assert.ok(existsSync(".next/standalone"), "standalone output missing");
  const html = readFileSync(".next/server/app/index.html", "utf8");
  assert.match(html, /RevenueOS/);
  assert.ok(existsSync(".next/server/app/api/health/route.js"), "health route missing");
});

test("the roster view is built", () => {
  assert.ok(existsSync(".next/server/app/roster/page.js"), "roster page missing");
});
