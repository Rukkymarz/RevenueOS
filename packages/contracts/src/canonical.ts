/**
 * RFC 8785 JSON Canonicalization Scheme. Byte-identical to Python's
 * revenueos_common.canonical.canonical_json, so an approval bound to an argument hash
 * in one language verifies in the other (INV-06). Shared vectors: fixtures-canonical/vectors.json.
 */
import { createHash } from "node:crypto";

export function canonicalize(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error("non-finite number cannot be canonicalized");
    return JSON.stringify(value);
  }
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalize).join(",")}]`;
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj).filter((k) => obj[k] !== undefined).sort(); // default sort = UTF-16 code units
    return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalize(obj[k])}`).join(",")}}`;
  }
  throw new Error(`unsupported type ${typeof value}`);
}

export function argsHash(value: unknown): string {
  return createHash("sha256").update(canonicalize(value), "utf8").digest("hex");
}
