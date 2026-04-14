export function DashboardPage() {
  return (
    <section>
      <h1 className="mb-4 text-2xl font-bold">Dashboard</h1>
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-sm text-slate-500">Total atletas</p>
          <p className="mt-1 text-xl font-semibold">--</p>
        </article>
        <article className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-sm text-slate-500">Última evaluación</p>
          <p className="mt-1 text-xl font-semibold">--</p>
        </article>
        <article className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-sm text-slate-500">Estado PHV</p>
          <p className="mt-1 text-xl font-semibold">--</p>
        </article>
      </div>
    </section>
  );
}
