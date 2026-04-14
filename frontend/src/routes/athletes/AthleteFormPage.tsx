interface AthleteFormPageProps {
  mode: "create" | "edit";
}

export function AthleteFormPage({ mode }: AthleteFormPageProps) {
  return (
    <section>
      <h1 className="mb-2 text-2xl font-bold">
        {mode === "create" ? "Nuevo atleta" : "Editar atleta"}
      </h1>
      <p className="text-sm text-slate-600">
        Vista placeholder para formulario de atleta (Paso 7).
      </p>
    </section>
  );
}
