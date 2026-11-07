# Oracle launch and recovery work record

Owner authorization: proceed toward production, prompt for owner-only account
steps, retain the strict $0 budget. This is a deployment candidate, not evidence
of a live or production-ready service.

## Pending owner step

Sign in or register at https://signup.cloud.oracle.com/ and complete verification
privately. Keep the account on Free Tier. No Pay As You Go upgrade, paid shapes,
or trial-only resources are authorized. If signup requires payment or card
verification is unacceptable, stop that path and report the blocker.

Record the actual home region and available Always Free A1 capacity. The current
Oracle documentation describes 2 OCPUs and 12 GB RAM for Always Free tenancies,
not the 4 OCPU / 24 GB frequently quoted in old guides. Verify the console's
Always Free label, storage and networking allocation before provisioning.
Capacity is not guaranteed and idle instances can be reclaimed.

Source: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm

## First deploy candidate

Start with the existing `compose.prod.yaml` on an isolated RevenueOS host. This
preserves PostgreSQL, restricted runtime roles, Redis and OIDC/PKCE/Keycloak.
Oracle A1 uses ARM64: verify every image and locally built dependency supports
ARM64, and build on the actual architecture before connecting public DNS.
Do not force amd64 emulation and describe it as tested ARM64 support.

Proposed names, not deployed URLs:

- `revenueos.petporsh.com`: browser interface and same-origin `/api`.
- `revenueos-auth.petporsh.com`: Keycloak authentication.

Only the reverse proxy exposes 80/443. Restrict SSH to owner administration.
Databases and Redis must have no public port mappings. Restrict Keycloak's
administration surface before launch. Configure SMTP and verify an owner account
with TOTP; do not disable email verification to get through onboarding.

Netlify remains an optional frontend destination. Supabase remains a candidate
for managed PostgreSQL/auth/storage. Neither is a drop-in replacement for this
topology: Supabase Auth requires a deliberately tested identity migration, and
external storage requires replacing local media writes. Do not split these
components until their security and failure behavior is verified.

## Encrypted backup candidate

`scripts/backup_production.py` backs up both application and identity databases,
media, the private environment and generated realm. It pauses the running app
writers during maintenance and restarts them in a `finally` block. It encrypts
the final archive with age and refuses to overwrite an existing output.

Install age from the operating system's official package repository. Generate
the recovery identity on the owner's trusted recovery machine, keep the private
identity OFF the deployment host, and send only its public recipient to the host.
See https://github.com/FiloSottile/age for key generation and recovery commands.

On the deployment host, after replacing the recipient and filename:

```sh
python3 scripts/backup_production.py create \
  --recipient AGE_PUBLIC_RECIPIENT \
  --output /var/backups/revenueos/UNIQUE_TIMESTAMP.tar.gz.age
```

The command creates a private temporary plaintext staging directory. Use an
encrypted filesystem or a sufficiently large private tmpfs via `TMPDIR`, and
account for staging space. A process crash or machine failure can leave private
temporary files behind; restrict host access and inspect leftovers privately.
Copy encrypted archives off-host. Do not put recovery files or private keys in
GitHub, CI artifacts or chat. Schedule backups only after a manual backup works;
log success/failure without secrets and configure alerts.

## Restore drill, before customer launch

Use an isolated scratch host, never a running customer deployment. Decrypt with
the owner's off-host age identity into a private directory (umask 077), then:

```sh
python3 scripts/backup_production.py verify recovery.tar.gz
```

This validates the member allowlist and checksums without extracting files or
executing SQL. It is not a database-restore test. After validation, review and
extract the trusted archive only in that private recovery directory. Restore the
environment/realm to a fresh checkout and initialize a fresh database volume with
the original generated roles/passwords. With app and Keycloak stopped, restore
`revenueos.dump` and `keycloak.dump` using PostgreSQL 16 `pg_restore`, preserving
ownership and grants. Restore media to its dedicated volume with API UID 10001
ownership. Validate migrations, FORCE RLS, both tenant boundaries, login/TOTP,
exports and representative media before any DNS cutover. Capture recovery time,
data cutoff, command results and failure handling. Securely dispose of scratch
plaintext after the drill. No restore drill has been executed yet.

## Release evidence still required

- Actual capacity, ARM builds, HTTPS and isolated hosting configuration.
- Live OIDC/MFA/email and authenticated PostgreSQL tenant isolation.
- Backup creation, off-host copy and an actual restore drill.
- Monitoring and tested alert delivery, deletion/retention procedures.
- Required external providers, verified free quotas and remaining feature work
  listed in `RELEASE_ACCEPTANCE.md`.

No DNS changes, infrastructure creation, paid services or customer launch have
been performed by this runbook.
