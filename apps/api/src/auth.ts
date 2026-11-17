/**
 * Bearer-token RBAC for the API (spec 2.5, separation of duties).
 *
 * Principals live in the keychain file `api-principals` (JSON list). Only sha256 digests of
 * tokens are stored, never tokens: [{ "token_sha256": "...", "principal": "human:christine",
 * "roles": ["approver", "auditor"] }]. Roles:
 *   requester - agents and services that ask for approvals and present them for consumption
 *   approver  - humans who decide approvals (never their own: the database enforces it too)
 *   auditor   - read-only access to approvals
 */
import { CanActivate, ExecutionContext, ForbiddenException, Injectable, SetMetadata, UnauthorizedException } from "@nestjs/common";
import { Reflector } from "@nestjs/core";
import { createHash, timingSafeEqual } from "node:crypto";
import { readFileSync, statSync } from "node:fs";
import { join } from "node:path";

export type Role = "requester" | "approver" | "auditor";
export interface Principal { principal: string; roles: Role[] }
interface Entry extends Principal { token_sha256: string }

export const ROLES_KEY = "roles";
export const Roles = (...roles: Role[]) => SetMetadata(ROLES_KEY, roles);

const PRINCIPAL_NAME = /^(human|agent|service):[A-Za-z0-9._@-]{1,64}$/;

export function loadPrincipals(dir = process.env.REVENUEOS_KEYCHAIN_DIR ?? "/run/revenueos/keychain"): Entry[] {
  const file = join(dir, "api-principals");
  let raw: string;
  try {
    if ((statSync(file).mode & 0o077) !== 0) throw new Error(`${file} must not be readable by group or others`);
    raw = readFileSync(file, "utf8");
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw e;
  }
  const entries = JSON.parse(raw) as Entry[];
  for (const e of entries) {
    if (!/^[0-9a-f]{64}$/.test(e.token_sha256) || !PRINCIPAL_NAME.test(e.principal)
        || !Array.isArray(e.roles) || e.roles.some((r) => !["requester", "approver", "auditor"].includes(r))) {
      throw new Error(`invalid principal entry for ${e.principal}`);
    }
  }
  return entries;
}

export function authenticate(header: string | undefined, entries: Entry[]): Principal | null {
  const m = /^Bearer ([A-Za-z0-9._~+/-]{16,})$/.exec(header ?? "");
  if (!m) return null;
  const digest = createHash("sha256").update(m[1]).digest();
  for (const e of entries) {
    if (timingSafeEqual(digest, Buffer.from(e.token_sha256, "hex"))) return { principal: e.principal, roles: e.roles };
  }
  return null;
}

@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private readonly reflector: Reflector) {}

  canActivate(ctx: ExecutionContext): boolean {
    const needed = this.reflector.getAllAndOverride<Role[]>(ROLES_KEY, [ctx.getHandler(), ctx.getClass()]);
    if (!needed) return true;
    const req = ctx.switchToHttp().getRequest();
    const who = authenticate(req.headers.authorization, loadPrincipals());
    if (!who) throw new UnauthorizedException({ error: "missing or unknown bearer token" });
    if (!needed.some((r) => who.roles.includes(r))) {
      throw new ForbiddenException({ error: `requires role ${needed.join(" or ")}`, principal: who.principal });
    }
    req.principal = who;
    return true;
  }
}
