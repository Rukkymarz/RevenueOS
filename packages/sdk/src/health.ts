import { HealthResponse, health as contractsHealth } from "@revenueos/contracts";

/** Package self-check (spec 1.1): the contracts the client validates against are loaded and sound. */
export function health() {
  const c = contractsHealth();
  return HealthResponse.parse({ service: "@revenueos/sdk", status: c.status, version: "0.1.0", checks: { contracts: c.status } });
}
