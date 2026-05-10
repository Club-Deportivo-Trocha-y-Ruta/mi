import { useNavigate, useParams, useSearchParams, Link } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { EventForm } from "@/components/calendar/EventForm";
import { useCalendarEvent } from "@/api/calendar";

interface EventFormPageProps {
  mode: "create" | "edit";
}

export function EventFormPage({ mode }: EventFormPageProps) {
  const navigate = useNavigate();
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const eventId = id ? Number(id) : null;
  const prefillDate = searchParams.get("date") ?? undefined;

  const isEdit = mode === "edit";
  const eventQuery = useCalendarEvent(isEdit ? eventId : null);

  function handleSuccess() {
    navigate("/calendar");
  }

  function handleCancel() {
    navigate("/calendar");
  }

  if (isEdit && eventQuery.isLoading) {
    return (
      <AppShell>
        <section className="space-y-3">
          <div className="h-6 w-52 animate-pulse rounded bg-light-gray" />
          <div className="h-80 animate-pulse rounded-xl bg-light-gray" />
        </section>
      </AppShell>
    );
  }

  if (isEdit && eventQuery.isError) {
    return (
      <AppShell>
        <section className="space-y-3">
          <h1
            className="text-2xl text-charcoal"
            style={{
              fontFamily: "'Cal Sans', system-ui, sans-serif",
              fontWeight: 600,
            }}
          >
            Editar evento
          </h1>
          <p className="text-sm text-red-700">No se pudo cargar el evento.</p>
          <Link
            to="/calendar"
            className="text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
          >
            Volver al calendario
          </Link>
        </section>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <section className="space-y-5">
        {/* Breadcrumb header */}
        <div className="flex items-start justify-between gap-3">
          <div>
            <nav aria-label="Breadcrumb" className="mb-1">
              <ol className="flex items-center gap-1 text-sm text-mid-gray">
                <li>
                  <Link
                    to="/calendar"
                    className="transition-opacity hover:opacity-70"
                  >
                    Calendario
                  </Link>
                </li>
                <li aria-hidden="true">/</li>
                <li className="text-charcoal font-medium">
                  {isEdit ? "Editar evento" : "Nuevo evento"}
                </li>
              </ol>
            </nav>
            <h1
              className="text-2xl text-charcoal"
              style={{
                fontFamily: "'Cal Sans', system-ui, sans-serif",
                fontWeight: 600,
              }}
            >
              {isEdit ? "Editar evento" : "Nuevo evento"}
            </h1>
            <p className="mt-0.5 text-sm text-mid-gray">
              {isEdit
                ? "Actualiza los datos del evento."
                : "Crea un nuevo evento en el calendario del club."}
            </p>
          </div>
          <Link
            to="/calendar"
            className="rounded-lg bg-white px-3 py-2 text-sm font-medium text-mid-gray transition-opacity hover:opacity-70"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          >
            Cancelar
          </Link>
        </div>

        <EventForm
          mode={mode}
          initialData={isEdit ? eventQuery.data : undefined}
          prefillDate={!isEdit ? prefillDate : undefined}
          onSuccess={handleSuccess}
          onCancel={handleCancel}
        />
      </section>
    </AppShell>
  );
}
