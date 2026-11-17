/** Admin shell (Phase 1): operator surfaces arrive with their phases. */
const surfaces = [
  { name: "Registries", phase: 4 }, { name: "Pins", phase: 4 }, { name: "Budgets", phase: 5 }, { name: "Kill switches", phase: 14 },
];

export default function Admin() {
  return (
    <div className="mx-auto grid max-w-4xl gap-12 px-6 py-12">
      <header className="grid gap-3">
        <p className="text-sm text-muted">RevenueOS</p>
        <h1 className="text-3xl font-semibold">Admin</h1>
      </header>
      <ul className="grid gap-3 sm:grid-cols-2">
        {surfaces.map((s) => (
          <li key={s.name} className="rounded-lg border border-border bg-surface p-4">
            <h2 className="font-medium">{s.name}</h2>
            <p className="mt-1 text-sm text-muted">Empty: available from phase {s.phase}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
