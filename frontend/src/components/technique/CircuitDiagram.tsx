/**
 * CircuitDiagram — presentational inline-SVG renderer for GymkhanaLayout.
 *
 * Pure presentational: no TanStack Query, no server calls, no new runtime
 * dependency (Phase A: inline SVG only).
 *
 * Renders the seven controlled element kinds from feature 019:
 *   cone · line · gate · mine · beam · ring · arrow
 *
 * Accessibility (FR-017 / WCAG 2.1 AA):
 *   - role="img" on the <svg> with aria-labelledby → <title> + <desc>
 *   - Every kind is distinguished by SHAPE/PATTERN as well as color;
 *     color is NEVER the sole visual cue.
 *
 * Legend (FR-004 / FR-020):
 *   - Spanish legend rendered for each kind PRESENT in elements.
 *   - Suppressed when elements is empty (spec edge-case).
 *
 * Privacy (FR-019 / O-5):
 *   - No minor PII anywhere; element labels are a controlled vocabulary set
 *     (kind name only). Free-text labels are deferred to Phase B.
 */

import { useId } from "react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import type { GymkhanaLayout, CircuitElement } from "@/types/technique.types";

// ---------------------------------------------------------------------------
// Public props
// ---------------------------------------------------------------------------

export interface CircuitDiagramProps {
  /** Validated GymkhanaLayout to render. Empty elements array is valid. */
  layout: GymkhanaLayout;
  /**
   * Text alternative for screen readers.
   * Derive from exercise.layout_alt. Falls back to a generic Spanish string.
   */
  altText?: string;
  /** Optional extra CSS classes for the outer container div. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Color palette — Tailwind default hex values.
// Shapes are ALSO distinguished by form; color is supplementary.
// ---------------------------------------------------------------------------

const COLORS = {
  cone:  { fill: "#F59E0B", stroke: "#92400E" },            // amber
  line:  { stroke: "#475569" },                              // neutral gray
  gate:  { fill: "#0EA5E9", stroke: "#0369A1" },            // sky
  mine:  { fill: "#F43F5E", stroke: "#9F1239", x: "#FFFFFF" }, // rose + white cross
  beam:  { fill: "#D97706", stroke: "#78350F", hatch: "#92400E" }, // amber-dark + hatch
  ring:  { stroke: "#7C3AED" },                             // violet
  arrow: { fill: "#10B981", stroke: "#065F46" },            // emerald
} as const;

// ---------------------------------------------------------------------------
// Spanish legend labels (FR-004 / FR-020)
// "line" splits into two legend entries: dashed vs solid.
// ---------------------------------------------------------------------------

type LegendKey =
  | "cone"
  | "line-dashed"
  | "line-solid"
  | "gate"
  | "mine"
  | "beam"
  | "ring"
  | "arrow";

const LEGEND_LABELS: Record<LegendKey, string> = {
  cone:          "Cono",
  "line-dashed": "Trayecto libre",
  "line-solid":  "Trayecto técnico",
  gate:          "Puerta",
  mine:          "Mina",
  beam:          "Equilibrio",
  ring:          "Círculo de la muerte",
  arrow:         "Dirección de recorrido",
};

// ---------------------------------------------------------------------------
// Element size helper
// ---------------------------------------------------------------------------

/**
 * Returns a base radius R in canvas units, proportional to the canvas.
 * Clamped to [2.5, 7] canvas units so elements are always visible but
 * never dominate on large canvases.
 */
function computeR(layout: GymkhanaLayout): number {
  const smallest = Math.min(layout.width, layout.height);
  return Math.max(2.5, Math.min(smallest * 0.05, 7));
}

// ---------------------------------------------------------------------------
// Shape renderers — each centered at SVG origin (0, 0).
// Parent <g> applies translate(x, y) rotate(deg) before rendering.
// ---------------------------------------------------------------------------

/** ▲ Cone — triangle with flat base.  Shape cue: triangle. */
function ConeShape({ R }: { R: number }) {
  const pts = `0,${-R * 1.45} ${-R},${R * 0.65} ${R},${R * 0.65}`;
  return (
    <polygon
      points={pts}
      fill={COLORS.cone.fill}
      stroke={COLORS.cone.stroke}
      strokeWidth={R * 0.14}
      strokeLinejoin="round"
    />
  );
}

/** ─ ─  Line segment.  Shape cue: dashed vs solid stroke pattern. */
function LineShape({ R, style }: { R: number; style: "dashed" | "solid" }) {
  const L = R * 4.5;
  return (
    <line
      x1={-L / 2}
      y1={0}
      x2={L / 2}
      y2={0}
      stroke={COLORS.line.stroke}
      strokeWidth={R * 0.38}
      strokeDasharray={style === "dashed" ? `${R * 1.1} ${R * 0.65}` : undefined}
      strokeLinecap="round"
    />
  );
}

/** || Gate — two vertical posts with crossbar.  Shape cue: double-post H form. */
function GateShape({ R }: { R: number }) {
  const postW = R * 0.45;
  const postH = R * 2;
  const gap = R * 0.75; // half-gap between posts (passage width)
  return (
    <g>
      {/* Left post */}
      <rect
        x={-gap - postW}
        y={-postH / 2}
        width={postW}
        height={postH}
        fill={COLORS.gate.fill}
        stroke={COLORS.gate.stroke}
        strokeWidth={R * 0.1}
        rx={R * 0.1}
      />
      {/* Right post */}
      <rect
        x={gap}
        y={-postH / 2}
        width={postW}
        height={postH}
        fill={COLORS.gate.fill}
        stroke={COLORS.gate.stroke}
        strokeWidth={R * 0.1}
        rx={R * 0.1}
      />
      {/* Top crossbar connecting posts */}
      <line
        x1={-gap - postW / 2}
        y1={-postH / 2}
        x2={gap + postW / 2}
        y2={-postH / 2}
        stroke={COLORS.gate.stroke}
        strokeWidth={R * 0.25}
      />
    </g>
  );
}

/** ⊗ Mine / hazard — filled circle with X cross.  Shape cue: circle + cross pattern. */
function MineShape({ R }: { R: number }) {
  const xr = R * 0.52;
  const sw = R * 0.32;
  return (
    <g>
      <circle
        r={R}
        fill={COLORS.mine.fill}
        stroke={COLORS.mine.stroke}
        strokeWidth={R * 0.12}
      />
      {/* X cross — pattern cue distinct from color alone (FR-017) */}
      <line
        x1={-xr} y1={-xr}
        x2={xr}  y2={xr}
        stroke={COLORS.mine.x}
        strokeWidth={sw}
        strokeLinecap="round"
      />
      <line
        x1={xr}  y1={-xr}
        x2={-xr} y2={xr}
        stroke={COLORS.mine.x}
        strokeWidth={sw}
        strokeLinecap="round"
      />
    </g>
  );
}

/** ═══ Beam (viga) — wide flat rectangle with diagonal hatch.  Shape cue: flat bar + hatch pattern. */
function BeamShape({ R }: { R: number }) {
  const bw = R * 5.2;
  const bh = R * 0.65;
  const numHatches = 5;
  const step = bw / (numHatches + 1);

  const hatches: ReactNode[] = [];
  for (let i = 1; i <= numHatches; i++) {
    const hx = -bw / 2 + step * i;
    hatches.push(
      <line
        key={i}
        x1={hx}
        y1={-bh / 2}
        x2={hx - R * 0.45}
        y2={bh / 2}
        stroke={COLORS.beam.hatch}
        strokeWidth={R * 0.14}
        strokeLinecap="round"
        opacity={0.75}
      />,
    );
  }

  return (
    <g>
      <rect
        x={-bw / 2}
        y={-bh / 2}
        width={bw}
        height={bh}
        rx={R * 0.12}
        fill={COLORS.beam.fill}
        stroke={COLORS.beam.stroke}
        strokeWidth={R * 0.1}
      />
      {hatches}
    </g>
  );
}

/** ○ Ring (círculo de la muerte) — open circle (stroke only).  Shape cue: open circle vs mine (filled). */
function RingShape({ R }: { R: number }) {
  return (
    <circle
      r={R * 1.15}
      fill="none"
      stroke={COLORS.ring.stroke}
      strokeWidth={R * 0.44}
    />
  );
}

/** ➤ Arrow — chevron polygon.  Shape cue: pointed directional arrow. */
function ArrowShape({ R }: { R: number }) {
  // Chevron pointing right (east) when rotation = 0.
  // rotation is applied by the parent <g> transform.
  const pts = [
    [-R * 0.55, -R * 0.42],
    [ R * 0.18, -R * 0.42],
    [ R * 0.18, -R * 0.82],
    [ R * 1.15,  0],
    [ R * 0.18,  R * 0.82],
    [ R * 0.18,  R * 0.42],
    [-R * 0.55,  R * 0.42],
  ]
    .map(([x, y]) => `${x},${y}`)
    .join(" ");
  return (
    <polygon
      points={pts}
      fill={COLORS.arrow.fill}
      stroke={COLORS.arrow.stroke}
      strokeWidth={R * 0.1}
      strokeLinejoin="round"
    />
  );
}

// ---------------------------------------------------------------------------
// Single element renderer
// ---------------------------------------------------------------------------

function CircuitElementNode({ el, R }: { el: CircuitElement; R: number }) {
  // SVG rotate(deg) is clockwise; rotation=0 is element's natural orientation.
  const rotation = el.rotation ?? 0;
  const transform = `translate(${el.x}, ${el.y}) rotate(${rotation})`;

  return (
    <g data-kind={el.kind} transform={transform}>
      {el.kind === "cone"  && <ConeShape R={R} />}
      {el.kind === "line"  && <LineShape R={R} style={el.style ?? "dashed"} />}
      {el.kind === "gate"  && <GateShape R={R} />}
      {el.kind === "mine"  && <MineShape R={R} />}
      {el.kind === "beam"  && <BeamShape R={R} />}
      {el.kind === "ring"  && <RingShape R={R} />}
      {el.kind === "arrow" && <ArrowShape R={R} />}
    </g>
  );
}

// ---------------------------------------------------------------------------
// Legend swatch — a tiny inline SVG preview for each legend entry.
// ---------------------------------------------------------------------------

const SWATCH_R  = 4.5;
const SWATCH_W  = 36;
const SWATCH_H  = 22;
const SWATCH_CX = SWATCH_W / 2;
const SWATCH_CY = SWATCH_H / 2;

function LegendSwatch({ legendKey }: { legendKey: LegendKey }) {
  const R = SWATCH_R;
  let shape: ReactNode = null;

  switch (legendKey) {
    case "cone":
      shape = <ConeShape R={R} />;
      break;
    case "line-dashed":
      shape = <LineShape R={R} style="dashed" />;
      break;
    case "line-solid":
      shape = <LineShape R={R} style="solid" />;
      break;
    case "gate":
      shape = <GateShape R={R} />;
      break;
    case "mine":
      shape = <MineShape R={R} />;
      break;
    case "beam":
      shape = <BeamShape R={R} />;
      break;
    case "ring":
      shape = <RingShape R={R} />;
      break;
    case "arrow":
      shape = <ArrowShape R={R} />;
      break;
  }

  return (
    <svg
      viewBox={`0 0 ${SWATCH_W} ${SWATCH_H}`}
      width={SWATCH_W}
      height={SWATCH_H}
      aria-hidden="true"
      className="shrink-0"
    >
      <g transform={`translate(${SWATCH_CX}, ${SWATCH_CY})`}>{shape}</g>
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Legend key derivation from element list
// ---------------------------------------------------------------------------

/**
 * Returns the ordered list of legend keys that correspond to the element kinds
 * actually present in the layout (de-duplicated, in first-occurrence order).
 * Line kind is split into 'line-dashed' and 'line-solid' if both styles appear.
 */
function buildLegendKeys(elements: CircuitElement[]): LegendKey[] {
  const seen = new Set<LegendKey>();
  const ordered: LegendKey[] = [];

  for (const el of elements) {
    let key: LegendKey;
    if (el.kind === "line") {
      key = el.style === "solid" ? "line-solid" : "line-dashed";
    } else {
      // All other kinds map 1:1 to a LegendKey.
      key = el.kind as LegendKey;
    }
    if (!seen.has(key)) {
      seen.add(key);
      ordered.push(key);
    }
  }

  return ordered;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * Renders a GymkhanaLayout as a responsive, accessible inline-SVG circuit diagram.
 *
 * Usage:
 *   <CircuitDiagram layout={exercise.layout_json} altText={exercise.layout_alt ?? undefined} />
 *
 * When layout.elements is empty, renders a bounded empty canvas with the legend
 * suppressed (per spec edge-case).
 */
export function CircuitDiagram({ layout, altText, className }: CircuitDiagramProps) {
  const uid = useId();
  const titleId = `${uid}-title`;
  const descId  = `${uid}-desc`;

  const R        = computeR(layout);
  const isEmpty  = layout.elements.length === 0;
  const legendKeys = buildLegendKeys(layout.elements);
  const finalAlt = altText?.trim() || "Diagrama del circuito de gymkhana";

  return (
    <div className={cn("space-y-3", className)}>
      {/* SVG canvas — responsive via width="100%", aspect-ratio preserved */}
      <div className="overflow-x-auto rounded-lg border border-border-gray bg-white">
        <svg
          role="img"
          aria-labelledby={`${titleId} ${descId}`}
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          width="100%"
          preserveAspectRatio="xMidYMid meet"
          style={{ display: "block", maxHeight: "480px" }}
        >
          {/* Accessibility text alternative (FR-017 / WCAG 1.1.1).
              <title> carries the meaningful alt text (from layout_alt);
              <desc> stays a non-empty structural note. */}
          <title id={titleId}>{finalAlt}</title>
          <desc  id={descId}>Diagrama vectorial del circuito de gymkhana.</desc>

          {/* Canvas background */}
          <rect width={layout.width} height={layout.height} fill="#F8FAFC" />

          {/* Canvas border */}
          <rect
            width={layout.width}
            height={layout.height}
            fill="none"
            stroke="#CBD5E1"
            strokeWidth={R * 0.12}
          />

          {/* Element layer — rendered in declaration order (later = on top in SVG) */}
          {layout.elements.map((el, idx) => (
            // eslint-disable-next-line react/no-array-index-key
            <CircuitElementNode key={idx} el={el} R={R} />
          ))}
        </svg>
      </div>

      {/* Legend — matches CircuitLayout's visual style; suppressed for empty layouts */}
      {!isEmpty && legendKeys.length > 0 && (
        <div className="rounded-lg border border-border-gray bg-light-gray p-3">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-mid-gray">
            Leyenda del circuito
          </p>
          <ul className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {legendKeys.map((key) => (
              <li key={key} className="flex items-center gap-2 text-xs text-mid-gray">
                <LegendSwatch legendKey={key} />
                <span>{LEGEND_LABELS[key]}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default CircuitDiagram;
