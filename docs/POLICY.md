# Policy

Rules enforced in code. Each line names the control that enforces it.

## Component selection

| Rule | Enforced by |
| --- | --- |
| Every spec-named project is the primary implementation, pinned to a commit (R03/R04) | `tests/connectivity/test_component_graph.py::test_named_components_are_primary_and_blocks_are_explained` |
| Add-ons beyond the spec need >= 10,000 stars, an OSI license, and a commit within 90 days at pin time (Addendum B) | `test_every_extension_repo_clears_the_star_gate` |
| Licenses must be one of MIT, Apache-2.0, BSD-2/3-Clause, MPL-2.0, LGPL-2.1, GPL-2.0, GPL-3.0, AGPL-3.0, PostgreSQL | `test_open_source_node_is_backed_by_pinned_repos` |
| Closed or hosted services may only be fallbacks for a confirmed open-source primary | `test_open_source_rule` |
| Experimental-only tools (D5: KeeLead and similar) can never be approved | `test_named_components_are_primary_and_blocks_are_explained` |

**D1 (amended R04).** Where a named tool has no usable public repo or license, the documented
functional equivalent is the official implementation. The named tool is re-evaluated each build
cycle and, if usable, replaces the add-on and the add-on becomes the fallback.

**D3.** Named tools under 1,000 stars sit behind a RevenueOS-owned adapter: the tool is the
default implementation and swapping it is a configuration change. The verifier interface
(Addendum G) is the first instance, landing in Phase 8.

## Free-tier preference order

1. Open-source, self-hosted.
2. Free hosted tier.
3. Paid, only with an explicit human approval (INV-06).

## Install policy (MCP servers, Phase 4)

Install lands as `experimental`; promotion to `approved` needs an approver (DB check
`tool_installations_check`) and a passing policy score (license, maintenance, security posture,
supply chain: pinned version, checksum, provenance). `production` follows a 7-day health
observation (14 days for api-anything, Addendum F). Only `approved`/`production` servers run in
production tasks (INV-10).

## Egress

All agent egress goes through Envoy (`infra/egress/envoy.yaml`). Each request needs an agent
identity; the decision service (`infra/egress/revenueos_egress_authz`) allows only hosts on that
agent's allowlist (`infra/egress/policy.yaml`, moving to Postgres in Phase 2), injects bound
secrets by reference, fails closed on any policy or secret error, and writes every decision to
the audit ledger without secret values.

## Approvals

High and critical tool calls need a human approval bound to the SHA-256 of the canonical
arguments; it expires, is single-use, and the requester cannot approve their own request
(`consume_approval`, `approvals_check`, `tool_call_approval_guard`, mcp-common `Receipts`).

## Secrets

Secrets are addressed only by reference (`keychain://` or `vault://`); literal values are
refused by the database (`agent_identities_secret_ref_check`, `credential_status`) and by the
secret resolver, scanned for in CI (gitleaks + `tests/threats`), and redacted from previews and
audit payloads.
