import { contrastRatio, meetsAA, requiredPairs, tokens } from "./color.js";

/** Package self-check (spec 1.1): every required token pair still meets WCAG AA. */
export function health() {
  const failing = requiredPairs.filter(([fg, bg, kind]) => !meetsAA(tokens.color[fg], tokens.color[bg], kind))
    .map(([fg, bg]) => `${fg}/${bg} ${contrastRatio(tokens.color[fg], tokens.color[bg])}:1`);
  return {
    service: "@revenueos/design-system", status: failing.length ? "degraded" : "ok", version: "0.1.0",
    checks: { contrast: failing.length ? failing.join(", ") : "ok" },
  } as const;
}
