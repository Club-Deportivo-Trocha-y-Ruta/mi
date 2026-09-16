/**
 * CourseSummary — tarjeta de reconocimiento de pista, de solo lectura
 * (feature 043 — perfil de circuito, US5, T058).
 *
 * Compartida textualmente por tres superficies: la pestaña Circuito del
 * coach (`CourseTab`) y las dos páginas de padres
 * (`ParentCompetitionResultsPage`, `ParentEventDetailPage`) — de ahí que
 * `athleteNamesById` sea opcional: el coach nunca lo pasa (siempre cae en el
 * rótulo neutral "Categoría de tu atleta" si `myCategories` no está vacío),
 * mientras que cada página de padres resuelve el nombre de sus propios
 * hijos antes de pasarlo. El componente es puramente prop-driven — nunca
 * busca ni infiere un nombre por su cuenta (misma disciplina que
 * `VariantsCard`/`CategorySetupTable`/`CourseDescriptionCard` en este mismo
 * módulo).
 *
 * `CourseMap`/`ElevationProfile` se montan lazy (Leaflet/Recharts no deben
 * pesar el chunk inicial de la pestaña Circuito). El esquema permite varias
 * variantes de circuito, pero en la práctica casi siempre hay una sola — por
 * eso el mapa/perfil de elevación se muestran solo para la PRIMERA variante;
 * el resto únicamente aporta su línea de cifras. Esto evita instanciar
 * varios mapas Leaflet en una sola tarjeta de reconocimiento.
 */
import { lazy, Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  KEY_SECTOR_LABELS,
  TERRAIN_TYPE_LABELS,
} from "@/types/raceCourse.types";
import type {
  CourseDescription,
  CourseSetup,
  CourseVariant,
  MyCategory,
  TerrainType,
} from "@/types/raceCourse.types";

const CourseMap = lazy(() =>
  import("@/components/race/course/CourseMap").then((m) => ({
    default: m.CourseMap,
  })),
);

const ElevationProfile = lazy(() =>
  import("@/components/race/course/ElevationProfile").then((m) => ({
    default: m.ElevationProfile,
  })),
);

// ---------------------------------------------------------------------------
// Catálogos locales de UI
// ---------------------------------------------------------------------------

/** Mismas etiquetas que `CourseDescriptionCard`/`EditCourseDescriptionDialog`
 * (no exportadas desde ahí — se duplican aquí, igual que ese mismo patrón
 * tri-estado ya establecido en este módulo). */
const DIFFICULTY_LABELS: Record<number, string> = {
  1: "1 — Muy fácil",
  2: "2 — Fácil",
  3: "3 — Media",
  4: "4 — Técnico",
  5: "5 — Muy técnico",
};

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface CourseSummaryProps {
  hasCourseData: boolean;
  variants: CourseVariant[];
  setups: CourseSetup[];
  description: CourseDescription;
  /** `[]` para coach/admin, o cuando no se resolvió nada para un padre. */
  myCategories: MyCategory[];
  /** Solo lo pasan las páginas de padres con sus propios hijos — la pestaña
   * del coach lo omite por completo. */
  athleteNamesById?: Record<number, string>;
  compact?: boolean;
  /** Solo mapa + perfil de la primera variante: la pestaña del coach ya
   * muestra cifras, vueltas y descripción en sus tarjetas editables. */
  mapOnly?: boolean;
}

// ---------------------------------------------------------------------------
// Helpers de formato
// ---------------------------------------------------------------------------

function formatTerrain(v: TerrainType | null): string {
  if (v == null) return "";
  return TERRAIN_TYPE_LABELS[v] ?? v;
}

function formatDifficulty(v: number | null): string {
  if (v == null) return "";
  return DIFFICULTY_LABELS[v] ?? String(v);
}

function formatSectors(v: CourseDescription["key_sectors"]): string {
  if (!v || v.length === 0) return "";
  return v.map((s) => KEY_SECTOR_LABELS[s] ?? s).join(", ");
}

/** Vueltas distintas (orden ascendente) que algún setup asigna a esta
 * variante — `[]` si ningún setup la referencia (la palabra "vueltas" se
 * omite por completo en ese caso). */
function lapsForVariant(setups: CourseSetup[], variantId: number): number[] {
  const laps = new Set<number>();
  for (const s of setups) {
    if (s.variant_id === variantId) laps.add(s.laps);
  }
  return Array.from(laps).sort((a, b) => a - b);
}

// ---------------------------------------------------------------------------
// Sub-componentes
// ---------------------------------------------------------------------------

function VariantFigures({
  variant,
  setups,
}: {
  variant: CourseVariant;
  setups: CourseSetup[];
}) {
  const laps = lapsForVariant(setups, variant.id);
  const parts = [`${variant.lap_distance_km} km`];
  // `VariantBlock` ya muestra "Sin altimetría en la grabación" cuando
  // `has_elevation` es false — repetir "Desnivel: sin dato" aquí sería
  // redundante (dos avisos distintos para el mismo hecho).
  if (variant.has_elevation) {
    const elevationText =
      variant.elevation_gain_m != null ? `${variant.elevation_gain_m} m` : "sin dato";
    parts.push(`Desnivel: ${elevationText}`);
  }
  if (laps.length > 0) {
    parts.push(`${laps.join("/")} vueltas`);
  }

  return (
    <p
      className="text-xs text-mid-gray"
      data-testid={`course-summary-figures-${variant.id}`}
    >
      {parts.join(" · ")}
    </p>
  );
}

function VariantBlock({
  variant,
  setups,
  showMap,
  showFigures = true,
}: {
  variant: CourseVariant;
  setups: CourseSetup[];
  showMap: boolean;
  showFigures?: boolean;
}) {
  return (
    <div
      className="space-y-2 rounded-xl bg-white p-4 ring-1 ring-[rgba(34,42,53,0.08)]"
      data-testid={`course-summary-variant-${variant.id}`}
    >
      <p className="text-sm font-semibold text-charcoal">{variant.label}</p>
      {showFigures && <VariantFigures variant={variant} setups={setups} />}
      {showMap && (
        <>
          <Suspense fallback={<Skeleton className="h-60 w-full rounded-xl" />}>
            <CourseMap geometry={variant.geometry} label={variant.label} />
          </Suspense>
          {variant.has_elevation ? (
            <Suspense fallback={<Skeleton className="h-40 w-full rounded-xl" />}>
              {/* `has_elevation=true` garantiza un desnivel calculado en el
               * backend; el `?? 0` es solo una guarda de tipos, nunca debería
               * disparar en la práctica. */}
              <ElevationProfile
                geometry={variant.geometry}
                elevationGainM={variant.elevation_gain_m ?? 0}
              />
            </Suspense>
          ) : (
            <p className="text-xs text-mid-gray">
              Sin altimetría en la grabación
            </p>
          )}
        </>
      )}
    </div>
  );
}

interface SetupRowProps {
  setup: CourseSetup;
  variantLabel: string;
  isHighlighted: boolean;
  highlightLabel: string | null;
}

function SetupRow({
  setup,
  variantLabel,
  isHighlighted,
  highlightLabel,
}: SetupRowProps) {
  return (
    <div
      className={cn(
        "grid grid-cols-1 gap-1 rounded-lg border p-2 text-sm sm:grid-cols-[1fr_auto_1fr]",
        isHighlighted
          ? "border-blue-300 bg-blue-50"
          : "border-[rgba(34,42,53,0.08)]",
      )}
      data-testid={`course-summary-setup-row-${setup.category_id}`}
      data-highlighted={isHighlighted ? "true" : undefined}
    >
      <span className="font-medium text-charcoal">
        {setup.category_label}
        {highlightLabel && (
          <span className="ml-2 text-xs font-normal text-blue-700">
            {highlightLabel}
          </span>
        )}
      </span>
      {/* `text-text-disclaimer` (no `text-mid-gray`): sobre el fondo
       * resaltado `bg-blue-50` de la fila de la categoría del hijo/a,
       * mid-gray cae a 4.485:1 — justo por debajo del piso AA 4.5:1 para
       * texto normal (14px). `--color-text-disclaimer` es el token que ya
       * existe en el design system para exactamente este caso (texto
       * secundario chico que necesita más contraste que mid-gray — ver
       * `style.css`); se usa acá en las dos filas (resaltada y no) para no
       * introducir un tono condicional según el highlight. */}
      <span className="text-text-disclaimer">{setup.laps} vueltas</span>
      <span className="text-text-disclaimer">{variantLabel}</span>
    </div>
  );
}

function DescriptionRecap({ description }: { description: CourseDescription }) {
  const terrain = formatTerrain(description.terrain_type);
  const difficulty = formatDifficulty(description.technical_difficulty);
  const sectors = formatSectors(description.key_sectors);
  const notes =
    description.course_notes && description.course_notes.trim() !== ""
      ? description.course_notes
      : "";

  // Recap de solo lectura para familias — a diferencia de
  // `CourseDescriptionCard` (coach), no hay nada útil que mostrar si el
  // coach no registró ningún campo todavía, así que no se renderiza nada.
  if (!terrain && !difficulty && !sectors && !notes) return null;

  return (
    <div
      className="space-y-2 rounded-xl bg-white p-4 ring-1 ring-[rgba(34,42,53,0.08)]"
      data-testid="course-summary-description"
    >
      <h3 className="text-sm font-semibold text-charcoal">
        Descripción del circuito
      </h3>
      {terrain && (
        <p data-testid="course-summary-description-terrain">
          <span className="text-[11px] font-medium text-mid-gray">
            Tipo de superficie:{" "}
          </span>
          <span className="text-sm text-charcoal">{terrain}</span>
        </p>
      )}
      {difficulty && (
        <p data-testid="course-summary-description-difficulty">
          <span className="text-[11px] font-medium text-mid-gray">
            Dificultad técnica:{" "}
          </span>
          <span className="text-sm text-charcoal">{difficulty}</span>
        </p>
      )}
      {sectors && (
        <p data-testid="course-summary-description-sectors">
          <span className="text-[11px] font-medium text-mid-gray">
            Sectores clave:{" "}
          </span>
          <span className="text-sm text-charcoal">{sectors}</span>
        </p>
      )}
      {notes && (
        <p data-testid="course-summary-description-notes">
          <span className="text-[11px] font-medium text-mid-gray">
            Notas:{" "}
          </span>
          <span className="text-sm text-charcoal">{notes}</span>
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CourseSummary({
  hasCourseData,
  variants,
  setups,
  description,
  myCategories,
  athleteNamesById,
  compact,
  mapOnly = false,
}: CourseSummaryProps) {
  // Nada que resumir todavía — nunca un CTA de estado vacío, eso es de
  // `VariantsCard`/`CourseDescriptionCard`.
  if (!hasCourseData) return null;

  if (mapOnly) {
    const first = variants[0];
    if (!first) return null;
    return (
      <div className="space-y-2" data-testid="course-summary">
        <h2 className="text-sm font-semibold text-charcoal">Mapa y altimetría</h2>
        <VariantBlock
          variant={first}
          setups={setups}
          showMap
          showFigures={false}
        />
      </div>
    );
  }

  const myCategoryByCategoryId = new Map(
    myCategories.map((c) => [c.category_id, c]),
  );
  const variantLabelById = new Map(variants.map((v) => [v.id, v.label]));

  return (
    <div
      className={cn(compact ? "space-y-3" : "space-y-4")}
      data-testid="course-summary"
    >
      <h2 className="text-sm font-semibold text-charcoal">
        Reconocimiento de la pista
      </h2>

      <div className="space-y-3">
        {variants.map((variant, index) => (
          <VariantBlock
            key={variant.id}
            variant={variant}
            setups={setups}
            showMap={index === 0}
          />
        ))}
      </div>

      {setups.length > 0 && (
        <div
          className="space-y-2 rounded-xl bg-white p-4 ring-1 ring-[rgba(34,42,53,0.08)]"
          data-testid="course-summary-setups"
        >
          <h3 className="text-sm font-semibold text-charcoal">
            Vueltas por categoría
          </h3>
          <div className="space-y-2">
            {setups.map((setup) => {
              const myCategory = myCategoryByCategoryId.get(setup.category_id);
              const isHighlighted = myCategory != null;
              const highlightLabel = isHighlighted
                ? (athleteNamesById?.[myCategory.athlete_id] &&
                    `Tu hijo/a: ${athleteNamesById[myCategory.athlete_id]}`) ||
                  "Categoría de tu atleta"
                : null;

              return (
                <SetupRow
                  key={setup.category_id}
                  setup={setup}
                  variantLabel={variantLabelById.get(setup.variant_id) ?? "—"}
                  isHighlighted={isHighlighted}
                  highlightLabel={highlightLabel}
                />
              );
            })}
          </div>
        </div>
      )}

      <DescriptionRecap description={description} />
    </div>
  );
}
