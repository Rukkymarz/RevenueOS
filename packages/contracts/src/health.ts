import { canonicalize } from "./canonical.js";
import { contracts, HealthResponse } from "./schemas.js";

/** Package self-check (spec 1.1): every contract compiles and canonicalization is RFC 8785-correct. */
export function health(): HealthResponse {
  const canonicalOk = canonicalize({ b: 1.0, a: [1e-7, "é"] }) === '{"a":[1e-7,"é"],"b":1}';
  return HealthResponse.parse({
    service: "@revenueos/contracts", status: canonicalOk ? "ok" : "degraded", version: "0.1.0",
    checks: { contracts: String(Object.keys(contracts).length), canonical: canonicalOk ? "ok" : "failed" },
  });
}
