import { BadRequestException, Body, Controller, Get, HttpCode, Module, Post, Res } from "@nestjs/common";
import { context, propagation, trace } from "@opentelemetry/api";
import { HealthResponse, ProbeRequest, ProbeResponse } from "@revenueos/contracts";
import type { Response } from "express";
import pg from "pg";

const started = Date.now();
const ORCHESTRATOR = process.env.ORCHESTRATOR_URL ?? "http://orchestrator:8101";

async function postgresOk(): Promise<string> {
  if (!process.env.PGHOST) return "not configured";
  const client = new pg.Client({ connectionTimeoutMillis: 2000 });
  try {
    await client.connect();
    await client.query("SELECT 1");
    return "ok";
  } catch (e) {
    return `error: ${(e as Error).message}`;
  } finally {
    await client.end().catch(() => undefined);
  }
}

@Controller()
export class HealthController {
  @Get("health")
  async health(@Res() res: Response) {
    const db = await postgresOk();
    const healthy = db === "ok" || db === "not configured";
    const body = HealthResponse.parse({
      service: "api", status: healthy ? "ok" : "degraded", version: process.env.REVENUEOS_VERSION ?? "0.1.0",
      uptime_s: (Date.now() - started) / 1000, checks: { postgres: db },
    });
    res.status(healthy ? 200 : 503).json(body);
  }
}

@Controller("v1")
export class ProbeController {
  /** End-to-end trace probe: api -> orchestrator -> MCP server, all spans carrying the four standard attributes. */
  @Post("probe")
  @HttpCode(200)
  async probe(@Body() body: unknown) {
    const parsed = ProbeRequest.safeParse(body);
    if (!parsed.success) throw new BadRequestException({ error: "contract violation", issues: parsed.error.issues });
    const req = parsed.data;
    return trace.getTracer("api").startActiveSpan("api.probe", {
      attributes: { task_id: req.task_id, agent_id: req.agent_id, tool: "probe_echo", risk_class: "low" },
    }, async (span) => {
      try {
        const headers: Record<string, string> = { "content-type": "application/json" };
        propagation.inject(context.active(), headers);
        const r = await fetch(`${ORCHESTRATOR}/v1/probe`, { method: "POST", headers, body: JSON.stringify(req) });
        if (!r.ok) throw new BadRequestException({ error: `orchestrator returned ${r.status}` });
        return ProbeResponse.parse(await r.json());
      } finally {
        span.end();
      }
    });
  }
}

@Module({ controllers: [HealthController, ProbeController] })
export class AppModule {}
