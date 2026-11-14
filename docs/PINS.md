# Pins

Every upstream project, how it is resolved, and the evidence. Rules are in spec
section 4: a repo URL or commit SHA is written here only after it has been
resolved and its license file read. CI re-resolves every pin.

Status as of Phase 1 (2026-11-14): **no upstream code is vendored yet.** Phase 1
is the in-repo database, contracts, and test harness. Pinning happens in Phase 4.

| Project | Component | Open source | License | Resolution | Repo | Commit SHA |
| --- | --- | --- | --- | --- | --- | --- |
| PostgreSQL 16 | C12 | yes | PostgreSQL | upstream (image) | postgres:16-alpine | digest pinned at Phase 4 |
| OpenBao | C17 | yes | MPL-2.0 | upstream (image) | openbao/openbao | digest pinned at Phase 4 |
| OpenTelemetry Collector | C18 | yes | Apache-2.0 | upstream (image) | otel/opentelemetry-collector-contrib:0.115.0 | digest pinned at Phase 4 |

All other components are listed in `config/components.yaml`. Those marked
`oss: verify` and `license: verify-at-pin` have not yet been confirmed and will
be pinned or resolved `native` in Phase 4.
