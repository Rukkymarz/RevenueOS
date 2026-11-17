export const dynamic = "force-dynamic";
const started = Date.now();

export function GET() {
  return Response.json({
    service: "admin", status: "ok", version: process.env.REVENUEOS_VERSION ?? "0.1.0",
    uptime_s: (Date.now() - started) / 1000, checks: { render: "ok" },
  });
}
