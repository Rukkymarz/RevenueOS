/**
 * Approval service (INV-06, spec 2.5). A high or critical tool call needs a human approval
 * bound to the exact arguments: the API hashes them with RFC 8785 (the same bytes Python's
 * mcp-common hashes), stores only the hash and a redacted preview, and the database enforces
 * expiry, single use and separation of duties. Every refusal is recorded with its reason
 * (approval_decide / consume_approval in migration 0002).
 */
import { BadRequestException, Body, ConflictException, Controller, Get, HttpCode, Param, Post, Query, Req,
  ServiceUnavailableException, UseGuards } from "@nestjs/common";
import { ApprovalRequest, argsHash } from "@revenueos/contracts";
import pg from "pg";
import { z } from "zod";
import { Principal, Roles, RolesGuard } from "./auth.js";

const Uuid = z.uuid();
const MAX_TTL_S = 3600;
const CreateBody = z.strictObject({
  task_id: Uuid,
  server: z.string().min(1).max(128),
  tool: z.string().regex(/^[a-zA-Z0-9_-]{1,64}$/),
  args: z.record(z.string(), z.unknown()),
  risk_class: z.enum(["high", "critical"]),
  ttl_s: z.int().min(30).max(MAX_TTL_S).default(900),
});
const DecideBody = z.strictObject({ approve: z.boolean() });
const ConsumeBody = z.strictObject({ args: z.record(z.string(), z.unknown()) });
const SECRETISH = /pass|secret|token|key|auth|cookie|otp|code/i;

/** Preview shown to the approver: structure and short values, never secret-looking fields. */
export function preview(args: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(args)) {
    if (SECRETISH.test(k)) out[k] = "[redacted]";
    else if (typeof v === "string") out[k] = v.length > 200 ? `${v.slice(0, 200)}…` : v;
    else if (v === null || typeof v === "number" || typeof v === "boolean") out[k] = v;
    else out[k] = `[${Array.isArray(v) ? "array" : "object"}]`;
  }
  return out;
}

async function withDb<T>(actor: string, fn: (c: pg.Client) => Promise<T>): Promise<T> {
  if (!process.env.PGHOST) throw new ServiceUnavailableException({ error: "database not configured" });
  const c = new pg.Client({ connectionTimeoutMillis: 3000 });
  await c.connect();
  try {
    await c.query("BEGIN");
    await c.query("SELECT set_config('revenueos.actor', $1, true)", [actor]);
    const r = await fn(c);
    await c.query("COMMIT");
    return r;
  } catch (e) {
    await c.query("ROLLBACK").catch(() => undefined);
    throw e;
  } finally {
    await c.end().catch(() => undefined);
  }
}

function parse<T extends z.ZodType>(schema: T, body: unknown): z.infer<T> {
  const r = schema.safeParse(body);
  if (!r.success) throw new BadRequestException({ error: "contract violation", issues: r.error.issues });
  return r.data;
}

function dbReason(e: unknown): string {
  const msg = (e as Error).message ?? String(e);
  return msg.replace(/^INV-06:\s*/, "");
}

@Controller("v1/approvals")
@UseGuards(RolesGuard)
export class ApprovalsController {
  @Post()
  @Roles("requester")
  async create(@Body() body: unknown, @Req() req: { principal: Principal }) {
    const b = parse(CreateBody, body);
    const hash = argsHash(b.args);
    const expires = new Date(Date.now() + b.ttl_s * 1000).toISOString();
    ApprovalRequest.parse({ task_id: b.task_id, requested_by: req.principal.principal, server: b.server, tool: b.tool,
      args_hash: hash, args_preview: preview(b.args), risk_class: b.risk_class, expires_at: expires });
    return withDb(req.principal.principal, async (c) => {
      const r = await c.query(
        `INSERT INTO approvals(task_id, tool_call_args_hash, requested_by, expires_at, mcp_server, tool, args_preview, risk_class)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id, status, expires_at`,
        [b.task_id, hash, req.principal.principal, expires, b.server, b.tool, JSON.stringify(preview(b.args)), b.risk_class]);
      return { ...r.rows[0], args_hash: hash };
    });
  }

  @Get()
  @Roles("approver", "auditor")
  async list(@Query("status") status: string | undefined, @Req() req: { principal: Principal }) {
    const s = parse(z.enum(["pending", "approved", "rejected", "used", "expired"]).optional(), status);
    return withDb(req.principal.principal, async (c) => (await c.query(
      `SELECT id, task_id, requested_by, approved_by, mcp_server AS server, tool, args_preview, risk_class,
              tool_call_args_hash AS args_hash, status, expires_at, decided_at, used_at
         FROM approvals WHERE ($1::approval_status IS NULL OR status = $1) ORDER BY created_at DESC LIMIT 200`,
      [s ?? null])).rows);
  }

  @Post(":id/decision")
  @HttpCode(200)
  @Roles("approver")
  async decide(@Param("id") id: string, @Body() body: unknown, @Req() req: { principal: Principal }) {
    parse(Uuid, id);
    const b = parse(DecideBody, body);
    try {
      return await withDb(req.principal.principal, async (c) => {
        const r = await c.query("SELECT approval_decide($1, $2, $3) AS status", [id, req.principal.principal, b.approve]);
        return { id, status: r.rows[0].status, decided_by: req.principal.principal };
      });
    } catch (e) {
      throw new ConflictException({ error: "approval decision refused", reason: dbReason(e) });
    }
  }

  @Post(":id/consume")
  @HttpCode(200)
  @Roles("requester")
  async consume(@Param("id") id: string, @Body() body: unknown, @Req() req: { principal: Principal }) {
    parse(Uuid, id);
    const b = parse(ConsumeBody, body);
    const hash = argsHash(b.args);
    const out = await withDb(req.principal.principal, async (c) => {
      const ok = (await c.query("SELECT consume_approval($1, $2) AS ok", [id, hash])).rows[0].ok as boolean;
      if (ok) return { ok, reason: null as string | null };
      const why = await c.query(
        `SELECT payload->>'reason' AS reason FROM audit_log WHERE action = 'approval.consume_rejected' AND target = $1
          ORDER BY seq DESC LIMIT 1`, [id]);
      return { ok, reason: (why.rows[0]?.reason as string) ?? "refused" };
    });
    if (!out.ok) throw new ConflictException({ error: "approval refused", reason: out.reason });
    return { id, consumed: true, args_hash: hash };
  }
}
