# petporsh.com connection

On November 11, 2026 the owner selected the apex `petporsh.com` for RevenueOS,
replacing its existing website destination. Netlify project `revenueos-rj` now
has this primary domain and the automatic `www.petporsh.com` alias attached.
External DNS verification and TLS issuance are pending. No DNS records or
nameservers have been changed by this task yet.

Authoritative nameservers observed: `dns1.namecheaphosting.com` and
`dns2.namecheaphosting.com`. The zone is managed in the hosting DNS controls,
typically cPanel Zone Editor; GoDaddy registration alone does not control this
active zone. Namecheap sign-in works, but the domain/hosting lists did not render
in the agent browser. The owner has been asked to open the actual DNS zone.

Netlify's domain panel gave these targets:

| Type | Name | Target |
| --- | --- | --- |
| A | @ / petporsh.com | 75.2.60.5 |
| CNAME | www | revenueos-rj.netlify.app |

For providers supporting apex ALIAS/ANAME, Netlify recommends
`apex-loadbalancer.netlify.com` instead of the fallback A record.

Existing apex A: `66.29.141.35`; existing www CNAME: `petporsh.com`.
No apex IPv6 address was returned. Preserve all mail and verification records.
MX records currently use mx1-hosting.jellyfish.systems (5),
mx2-hosting.jellyfish.systems (10), mx3-hosting.jellyfish.systems (20).

After the owner authorizes access to the zone, inspect current records, update
only website records, verify authoritative and public DNS, then provision and
validate Netlify HTTPS. Do not bypass certificate errors. Only after HTTPS is
valid, update the Supabase Site URL to https://petporsh.com and add the exact
https://petporsh.com/account/recover callback. Verify email confirmation and
recovery on the new origin; sessions are scoped to the browser origin, so users
will sign in again on the custom domain. Keep the Netlify origin as fallback
until acceptance passes. Project visibility is still private and must be
reviewed before public launch. No paid hosting is required by this setup.
