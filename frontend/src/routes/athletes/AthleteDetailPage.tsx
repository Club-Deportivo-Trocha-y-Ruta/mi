import { useParams } from "react-router-dom";

export function AthleteDetailPage() {
  const { id } = useParams();

  return (
    <section>
      <h1 className="mb-2 text-2xl font-bold">Detalle de atleta</h1>
      <p className="text-sm text-slate-600">
        Vista placeholder para atleta #{id}.
      </p>
    </section>
  );
}
