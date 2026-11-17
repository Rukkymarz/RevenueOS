/**
 * Command Center shell (Phase 1). Each view lands in its phase; until then the
 * shell shows the view with an explicit empty state rather than invented data.
 */
const views: { name: string; phase: number; href?: string }[] = [
  { name: "Agent roster", phase: 5, href: "/roster" }, { name: "Projects", phase: 5 }, { name: "Task board", phase: 5 },
  { name: "Approvals inbox", phase: 2 }, { name: "Registries", phase: 4 }, { name: "Lead pipeline", phase: 10 },
  { name: "Timelines", phase: 11 }, { name: "Insights", phase: 11 }, { name: "Skills", phase: 12 },
  { name: "Audit", phase: 11 }, { name: "Takeover console", phase: 14 }, { name: "Design studio", phase: 9 },
];

export default function Home() {
  return (
    <div className="mx-auto grid max-w-6xl gap-12 px-6 py-12">
      <header className="grid gap-3">
        <p className="text-sm text-muted">RevenueOS</p>
        <h1 className="text-3xl font-semibold">Command center</h1>
        <p className="max-w-2xl text-muted">
          Agents, projects, approvals and evidence in one place. Views come online phase by phase; each one shows
          live data or an empty state, never placeholder numbers.
        </p>
      </header>
      <nav aria-label="Views" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {views.map((v) => (
          <section key={v.name} className="rounded-lg border border-border bg-surface p-4">
            <h2 className="font-medium">{v.name}</h2>
            {v.href ? (
              <a className="mt-1 inline-block rounded-sm text-sm underline" href={v.href}>Open</a>
            ) : (
              <p className="mt-1 rounded-sm text-sm text-muted">Empty: available from phase {v.phase}</p>
            )}
          </section>
        ))}
      </nav>
    </div>
  );
}
