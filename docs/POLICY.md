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

Agents run in the Bubblewrap sandbox with no network of their own. Their one route out is a
per-session Unix socket to the sandbox supervisor, whose forwarder strips any identity headers
the agent sent and stamps the request with the session, agent, task and time, signed with
`keychain://egress-identity-hmac`. Envoy (`infra/egress/envoy.yaml`) asks the decision service
(`infra/egress/revenueos_egress_authz`) about every request. It is allowed only if:

- the stamp is authentic, at most 5 minutes old, and its session is open and belongs to that
  agent and task (identity pinning; an agent cannot speak as another agent or task);
- the host is in the agent's rules in Postgres `egress_rules`, agent-wide or for that task;
- every secret bound to the host (`secret_bindings`, by reference) resolves and is header-safe.

Anything else is denied, and any error fails closed. Each decision is an append-only
`egress_log` row and an audit entry (agent, task, host, reason; never secret values). CONNECT
tunnels are refused: encrypted tunnels cannot be inspected or have secrets injected.

## Approvals

High and critical tool calls need a human approval bound to the SHA-256 of the canonical
arguments; it expires, is single-use, and the requester cannot approve their own request
(`consume_approval`, `approvals_check`, `tool_call_approval_guard`, mcp-common `Receipts`).

## Secrets

Secrets are addressed only by reference (`keychain://` or `vault://`); literal values are
refused by the database (`agent_identities_secret_ref_check`, `credential_status`) and by the
secret resolver, scanned for in CI (gitleaks + `tests/threats`), and redacted from previews and
audit payloads.
