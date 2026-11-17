#!/bin/sh
# Generate pydantic v2 models from the zod-derived JSON Schema bundle.
# Input:  packages/contracts/generated/contracts.schema.json  (pnpm --filter @revenueos/contracts build)
# Output: packages/contracts/python/revenueos_contracts/models.py
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
datamodel-codegen \
  --input "$ROOT/packages/contracts/generated/contracts.schema.json" \
  --input-file-type jsonschema \
  --output "$ROOT/packages/contracts/python/revenueos_contracts/models.py" \
  --output-model-type pydantic_v2.BaseModel \
  --target-python-version 3.12 \
  --field-constraints \
  --use-annotated \
  --use-double-quotes \
  --disable-timestamp \
  --enum-field-as-literal all
echo "generated $ROOT/packages/contracts/python/revenueos_contracts/models.py"
