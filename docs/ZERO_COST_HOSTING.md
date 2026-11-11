# RevenueOS: strict $0 hosting constraint

The owner selected **$0 — no paid services**. Do not enable paid plans,
card-backed trials, overage billing, paid model calls, paid databases or domains.
Do not upgrade Vercel or provision the paid production topology.

A custom domain is not required. Hosts assign HTTPS service URLs.

## What can be hosted for free

Netlify Free allows commercial frontend projects, has a 300-credit monthly cap,
and pauses projects at the limit. It is a potential replacement for Vercel in a
free pilot, while preserving the existing Next.js source. The backend remains a
separate service; publishing a sign-in setup page alone is not a functioning app.

Sources checked 2026-11-06:
- https://www.netlify.com/pricing/
- https://www.netlify.com/blog/introducing-netlify-free-plan/
- https://www.netlify.com/pricing/faq/

## Why the current production topology is not verified at $0

The existing backend needs persistent PostgreSQL, Keycloak, Redis and artifact
storage as well as the FastAPI service. Render explicitly says its Free instances
are not for production. Web services sleep after 15 idle minutes, local files are
lost on restart/sleep, free PostgreSQL expires after 30 days, and all free web
services share 750 instance-hours per month. With a payment method present, some
overages can be billed: do not assume selecting Free alone enforces a $0 budget.

Koyeb's Free instance is also documented as a testing/hobby option, not a
production service. No free instance has been provisioned on either host.

Sources:
- https://render.com/docs/free
- https://www.koyeb.com/docs/reference/instances

## Supported next steps

1. **Limited free hosted pilot:** connect an appropriate free hosting account and
   select only plans with enforced no-overage limits. Use persistent free external
   databases/storage where supported, verify expiry and quota behavior, and retain
   the production security controls. It must be labeled a pilot until live
   identity, tenant isolation, storage, recovery and provider checks pass.
2. **Existing hardware:** run the original stack on an already available machine
   with Docker, using the supplied recipes and dedicated credentials. Any public
   tunnel/ingress needs a stable issuer/callback URL, HTTPS and restricted network
   exposure. There is no hosted availability guarantee when that machine is off.

No account connection, existing suitable host, or complete persistent free
backend is currently available to this build. There is no verified public app
URL. Keep cloud deployment blocked rather than replacing authentication, using
an expiring database for customer data, or pretending a static preview is the app.

Provider-backed lead discovery, AI image/video, social publishing, email delivery
and billing also need implemented adapters, configured accounts and enforceable
free quotas. The current app keeps unconfigured capabilities unavailable.
