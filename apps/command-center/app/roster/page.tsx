/**
 * Agent roster (Addendum A5): renders the Agency-format roster served by the pm service, one card per
 * agent with its companion document. No invented rows: if the service is unreachable the page says so.
 */
export const dynamic = "force-dynamic";

type Agent = { id: string; division: string; service: string; component: string; role: string; companion: string; markdown: string };

async function load(): Promise<{ agents: Agent[]; error?: string }> {
  const base = process.env.PM_URL ?? "http://pm:8106";
  try {
    const r = await fetch(`${base}/v1/roster`, { cache: "no-store" });
    if (!r.ok) return { agents: [], error: `pm service answered ${r.status}` };
    return { agents: (await r.json()).agents as Agent[] };
  } catch (e) {
    return { agents: [], error: `pm service unreachable: ${(e as Error).message}` };
  }
}

export default async function Roster() {
  const { agents, error } = await load();
  const divisions = [...new Set(agents.map((a) => a.division))].sort();
  return (
    <div className="mx-auto grid max-w-6xl gap-8 px-6 py-12">
      <header className="grid gap-2">
        <h1 className="text-3xl font-semibold">Agent roster</h1>
        <p className="text-muted">{agents.length} agents in {divisions.length} divisions, from the Agency roster format.</p>
      </header>
      {error && <p role="alert" className="rounded-lg border border-border bg-surface p-4">{error}</p>}
      {divisions.map((d) => (
        <section key={d} aria-label={d} className="grid gap-3">
          <h2 className="text-xl font-medium capitalize">{d}</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {agents.filter((a) => a.division === d).map((a) => (
              <details key={a.id} className="rounded-lg border border-border bg-surface p-4" data-agent={a.id}>
                <summary className="cursor-pointer font-medium">{a.id} <span className="text-sm text-muted">{a.component} · {a.role}</span></summary>
                <pre className="mt-3 whitespace-pre-wrap text-sm">{a.markdown}</pre>
              </details>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
