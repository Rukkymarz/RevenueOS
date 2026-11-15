/**
 * Emit one JSON Schema bundle (draft 2020-12) with every contract under $defs and a
 * root object that references them, so datamodel-code-generator produces one
 * pydantic model per contract with the contract's name.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { z } from "zod";
import { contracts } from "../src/schemas.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const outDir = join(root, "generated");
mkdirSync(outDir, { recursive: true });

const defs: Record<string, unknown> = {};
for (const [name, schema] of Object.entries(contracts)) {
  const js = z.toJSONSchema(schema, { target: "draft-2020-12", unrepresentable: "throw" }) as Record<string, unknown>;
  delete js.$schema;
  defs[name] = js;
  writeFileSync(join(outDir, `${name}.schema.json`), JSON.stringify({ $schema: "https://json-schema.org/draft/2020-12/schema", ...js }, null, 2));
}

const bundle = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  title: "RevenueOSContracts",
  type: "object",
  properties: Object.fromEntries(Object.keys(defs).map((n) => [n, { $ref: `#/$defs/${n}` }])),
  $defs: defs,
};
writeFileSync(join(outDir, "contracts.schema.json"), JSON.stringify(bundle, null, 2));
console.log(`generated ${Object.keys(defs).length} contracts -> ${outDir}`);
