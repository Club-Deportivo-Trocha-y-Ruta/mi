/**
 * CompetitionImportsPage — «Cargas e identidades» (feature 045, US3).
 *
 * Ruta: /competitions/imports?seccion=cargas|identidades|sin-enlazar[&import=<id>]
 * Acceso: coach + admin.
 *
 * Una sola bandeja para lo que hay que atender tras cargar resultados:
 *  - «Cargas»: imports en curso y cargados (retomar / descartar / confirmar).
 *  - «¿Es la misma persona?»: decisiones de identidad de competidores.
 *  - «Sin enlazar»: competidores sin deportista del club.
 *
 * La sección activa vive en `?seccion=` (enlazable, sobrevive a recargar);
 * un valor ausente o desconocido cae en «Cargas». `?import=<id>` lo escribe el
 * bloqueo de una carga (`409 identity_pending`): en «¿Es la misma persona?»
 * muestra «Volver a la carga» para retomarla sin volver a subir el archivo.
 *
 * Reemplaza a `/competitions/history`, `/competitions/identity-review` y
 * `/competitions/unlinked`, que ahora redirigen aquí (`contracts/ui-routes.md`).
 */
import { lazy, Suspense } from "react";
import { useSearchParams } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PageHeader } from "@/components/shared/PageHeader";
import { LoadsSection } from "@/components/competitions/imports/LoadsSection";
import { useImportsHistory } from "@/hooks/ai/useRaceImports";
import { useIdentitySummary } from "@/hooks/race/useIdentityReview";

// Identidad y «Sin enlazar» son las secciones más pesadas: solo se descargan
// cuando el coach las abre (Radix desmonta el contenido inactivo).
const IdentitySection = lazy(() =>
  import("@/components/competitions/imports/IdentitySection").then((m) => ({
    default: m.IdentitySection,
  })),
);
const UnlinkedSection = lazy(() =>
  import("@/components/competitions/imports/UnlinkedSection").then((m) => ({
    default: m.UnlinkedSection,
  })),
);

export const IMPORTS_SECTIONS = ["cargas", "identidades", "sin-enlazar"] as const;
export type ImportsSection = (typeof IMPORTS_SECTIONS)[number];

const SECTION_LABELS: Record<ImportsSection, string> = {
  cargas: "Cargas",
  identidades: "¿Es la misma persona?",
  "sin-enlazar": "Sin enlazar",
};

function parseSection(value: string | null): ImportsSection {
  return (IMPORTS_SECTIONS as readonly string[]).includes(value ?? "")
    ? (value as ImportsSection)
    : "cargas";
}

function SectionFallback() {
  return (
    <div
      className="flex min-h-[20vh] items-center justify-center text-sm text-mid-gray"
      role="status"
      aria-live="polite"
    >
      Cargando sección...
    </div>
  );
}

function CountBadge({ count, label }: { count: number; label: string }) {
  if (count <= 0) return null;
  // Texto oculto en vez de `aria-label` (un <span> sin rol no admite nombre).
  return (
    <Badge variant="warning">
      <span aria-hidden="true">{count}</span>
      <span className="sr-only">{label}</span>
    </Badge>
  );
}

export function CompetitionImportsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const section = parseSection(searchParams.get("seccion"));
  const importId = searchParams.get("import");

  // Mismas queries que las secciones (misma key → una sola petición).
  const identitySummary = useIdentitySummary();
  const importsHistory = useImportsHistory({ limit: 100 });

  const identityPending = identitySummary.data?.pending ?? 0;
  const inProgress = (importsHistory.data?.items ?? []).filter(
    (i) => i.status === "pending" || i.status === "dry_run",
  ).length;

  function handleSectionChange(next: string) {
    const nextSection = parseSection(next);
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        params.set("seccion", nextSection);
        // `import` solo tiene sentido dentro de «¿Es la misma persona?».
        if (nextSection !== "identidades") params.delete("import");
        return params;
      },
      { replace: true },
    );
  }

  return (
    <section className="mx-auto max-w-4xl space-y-5 px-4 py-6">
      <PageHeader
        title="Cargas e identidades"
        subtitle="Cargas de resultados en curso, decisiones de identidad y competidores sin enlazar."
        backTo={{ to: "/competitions", label: "Volver a competencias" }}
      />

      <Tabs value={section} onValueChange={handleSectionChange}>
        <TabsList aria-label="Secciones de cargas e identidades">
          <TabsTrigger value="cargas" data-testid="seccion-cargas">
            {SECTION_LABELS.cargas}
            <CountBadge
              count={inProgress}
              label={`${inProgress} carga${inProgress === 1 ? "" : "s"} en curso`}
            />
          </TabsTrigger>
          <TabsTrigger value="identidades" data-testid="seccion-identidades">
            {SECTION_LABELS.identidades}
            <CountBadge
              count={identityPending}
              label={
                identityPending === 1
                  ? "1 decisión pendiente"
                  : `${identityPending} decisiones pendientes`
              }
            />
          </TabsTrigger>
          <TabsTrigger value="sin-enlazar" data-testid="seccion-sin-enlazar">
            {SECTION_LABELS["sin-enlazar"]}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="cargas">
          <LoadsSection />
        </TabsContent>
        <TabsContent value="identidades">
          <Suspense fallback={<SectionFallback />}>
            <IdentitySection importId={importId} />
          </Suspense>
        </TabsContent>
        <TabsContent value="sin-enlazar">
          <Suspense fallback={<SectionFallback />}>
            <UnlinkedSection />
          </Suspense>
        </TabsContent>
      </Tabs>
    </section>
  );
}

export default CompetitionImportsPage;
