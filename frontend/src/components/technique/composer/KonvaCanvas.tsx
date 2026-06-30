/**
 * KonvaCanvas — react-konva drag-and-drop circuit element editor.
 *
 * BUNDLE ISOLATION (T030): this file imports react-konva at the top level.
 * It MUST only ever be loaded via React.lazy() / dynamic import() from
 * ComposerPage so react-konva + konva stay OUT of the shared bundle.
 *
 * Renders the same element vocabulary as CircuitDiagram.tsx (Phase A static
 * renderer), using the identical color palette and shape geometry, but in an
 * interactive Konva Stage where elements are:
 *   - Placed at logical canvas coordinates (0…width × 0…height)
 *   - Draggable within canvas bounds
 *   - Selectable (click) → shows a Transformer for rotation
 *   - Rotatable via the Transformer handle
 *
 * The Stage uses scaleX/scaleY so all internal coordinates are in logical
 * canvas units (same as GymkhanaLayout) — no manual pixel↔unit conversion
 * needed in drag handlers.
 *
 * Privacy (FR-019): no athlete PII is ever rendered; labels come from
 * ComposedElement.label which is validated by piiGuard before being stored.
 */

import { useEffect, useRef, useState } from "react";
import {
  Stage,
  Layer,
  Group,
  Line,
  Rect,
  Circle,
  Text,
  Transformer,
} from "react-konva";
import type Konva from "konva";

import type { CircuitElementKind } from "@/types/technique.types";

// ---------------------------------------------------------------------------
// Internal composed element type (adds _id for React tracking)
// ---------------------------------------------------------------------------

export interface ComposedElement {
  _id: string;
  kind: CircuitElementKind;
  x: number;
  y: number;
  rotation?: number;
  style?: "dashed" | "solid";
  label?: string;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface KonvaCanvasProps {
  /** Logical canvas width (> 0). Default 100. */
  canvasWidth: number;
  /** Logical canvas height (> 0). Default 60. */
  canvasHeight: number;
  elements: ComposedElement[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onChange: (id: string, updates: Partial<Omit<ComposedElement, "_id" | "kind">>) => void;
}

// ---------------------------------------------------------------------------
// Color palette — matches CircuitDiagram.tsx exactly
// ---------------------------------------------------------------------------

const COLORS = {
  cone:  { fill: "#F59E0B", stroke: "#92400E" },
  line:  { stroke: "#475569" },
  gate:  { fill: "#0EA5E9", stroke: "#0369A1" },
  mine:  { fill: "#F43F5E", stroke: "#9F1239", x: "#FFFFFF" },
  beam:  { fill: "#D97706", stroke: "#78350F", hatch: "#92400E" },
  ring:  { stroke: "#7C3AED" },
  arrow: { fill: "#10B981", stroke: "#065F46" },
} as const;

// ---------------------------------------------------------------------------
// Element size (logical units) — mirrors computeR in CircuitDiagram.tsx
// ---------------------------------------------------------------------------

function computeR(w: number, h: number): number {
  const smallest = Math.min(w, h);
  return Math.max(2.5, Math.min(smallest * 0.05, 7));
}

// ---------------------------------------------------------------------------
// Shape renderers (in Konva, all coords relative to the Group origin 0,0)
// Each renderer returns an array of Konva JSX nodes.
// ---------------------------------------------------------------------------

function ConeShapes({ R }: { R: number }) {
  const pts = [0, -R * 1.45, -R, R * 0.65, R, R * 0.65];
  return (
    <Line
      points={pts}
      closed
      fill={COLORS.cone.fill}
      stroke={COLORS.cone.stroke}
      strokeWidth={R * 0.14}
    />
  );
}

function LineShapes({ R, style }: { R: number; style: "dashed" | "solid" }) {
  const L = R * 4.5;
  return (
    <Line
      points={[-L / 2, 0, L / 2, 0]}
      stroke={COLORS.line.stroke}
      strokeWidth={R * 0.38}
      dash={style === "dashed" ? [R * 1.1, R * 0.65] : undefined}
      lineCap="round"
    />
  );
}

function GateShapes({ R }: { R: number }) {
  const postW = R * 0.45;
  const postH = R * 2;
  const gap = R * 0.75;
  return (
    <>
      <Rect
        x={-gap - postW}
        y={-postH / 2}
        width={postW}
        height={postH}
        fill={COLORS.gate.fill}
        stroke={COLORS.gate.stroke}
        strokeWidth={R * 0.1}
        cornerRadius={R * 0.1}
      />
      <Rect
        x={gap}
        y={-postH / 2}
        width={postW}
        height={postH}
        fill={COLORS.gate.fill}
        stroke={COLORS.gate.stroke}
        strokeWidth={R * 0.1}
        cornerRadius={R * 0.1}
      />
      <Line
        points={[-gap - postW / 2, -postH / 2, gap + postW / 2, -postH / 2]}
        stroke={COLORS.gate.stroke}
        strokeWidth={R * 0.25}
      />
    </>
  );
}

function MineShapes({ R }: { R: number }) {
  const xr = R * 0.52;
  const sw = R * 0.32;
  return (
    <>
      <Circle
        radius={R}
        fill={COLORS.mine.fill}
        stroke={COLORS.mine.stroke}
        strokeWidth={R * 0.12}
      />
      <Line
        points={[-xr, -xr, xr, xr]}
        stroke={COLORS.mine.x}
        strokeWidth={sw}
        lineCap="round"
      />
      <Line
        points={[xr, -xr, -xr, xr]}
        stroke={COLORS.mine.x}
        strokeWidth={sw}
        lineCap="round"
      />
    </>
  );
}

function BeamShapes({ R }: { R: number }) {
  const bw = R * 5.2;
  const bh = R * 0.65;
  const numHatches = 5;
  const step = bw / (numHatches + 1);
  return (
    <>
      <Rect
        x={-bw / 2}
        y={-bh / 2}
        width={bw}
        height={bh}
        fill={COLORS.beam.fill}
        stroke={COLORS.beam.stroke}
        strokeWidth={R * 0.1}
        cornerRadius={R * 0.12}
      />
      {Array.from({ length: numHatches }, (_, i) => {
        const hx = -bw / 2 + step * (i + 1);
        return (
          <Line
            key={i}
            points={[hx, -bh / 2, hx - R * 0.45, bh / 2]}
            stroke={COLORS.beam.hatch}
            strokeWidth={R * 0.14}
            lineCap="round"
            opacity={0.75}
          />
        );
      })}
    </>
  );
}

function RingShapes({ R }: { R: number }) {
  return (
    <Circle
      radius={R * 1.15}
      fill="transparent"
      stroke={COLORS.ring.stroke}
      strokeWidth={R * 0.44}
    />
  );
}

function ArrowShapes({ R }: { R: number }) {
  const pts = [
    -R * 0.55, -R * 0.42,
    R * 0.18,  -R * 0.42,
    R * 0.18,  -R * 0.82,
    R * 1.15,   0,
    R * 0.18,   R * 0.82,
    R * 0.18,   R * 0.42,
    -R * 0.55,  R * 0.42,
  ];
  return (
    <Line
      points={pts}
      closed
      fill={COLORS.arrow.fill}
      stroke={COLORS.arrow.stroke}
      strokeWidth={R * 0.1}
    />
  );
}

// ---------------------------------------------------------------------------
// Element hit area (invisible, ensures small shapes are still clickable)
// ---------------------------------------------------------------------------

function HitArea({ R }: { R: number }) {
  const size = Math.max(R * 3, 8);
  return (
    <Rect
      x={-size / 2}
      y={-size / 2}
      width={size}
      height={size}
      fill="transparent"
      // Konva: a transparent fill still makes the rect hittable
      listening={true}
    />
  );
}

// ---------------------------------------------------------------------------
// Single element node
// ---------------------------------------------------------------------------

interface ElementNodeProps {
  el: ComposedElement;
  R: number;
  canvasWidth: number;
  canvasHeight: number;
  isSelected: boolean;
  onSelect: () => void;
  onChange: (updates: Partial<Omit<ComposedElement, "_id" | "kind">>) => void;
  groupRef: (node: Konva.Group | null) => void;
}

function ElementNode({
  el,
  R,
  canvasWidth,
  canvasHeight,
  isSelected,
  onSelect,
  onChange,
  groupRef,
}: ElementNodeProps) {
  return (
    <Group
      ref={groupRef}
      x={el.x}
      y={el.y}
      rotation={el.rotation ?? 0}
      draggable
      onClick={onSelect}
      onTap={onSelect}
      dragBoundFunc={(pos) => ({
        x: Math.max(0, Math.min(pos.x, canvasWidth)),
        y: Math.max(0, Math.min(pos.y, canvasHeight)),
      })}
      onDragEnd={(e) => {
        const pos = e.target.position();
        onChange({
          x: Math.max(0, Math.min(pos.x, canvasWidth)),
          y: Math.max(0, Math.min(pos.y, canvasHeight)),
        });
      }}
      onTransformEnd={(e) => {
        onChange({ rotation: e.target.rotation() });
      }}
    >
      <HitArea R={R} />

      {el.kind === "cone"  && <ConeShapes R={R} />}
      {el.kind === "line"  && <LineShapes R={R} style={el.style ?? "dashed"} />}
      {el.kind === "gate"  && <GateShapes R={R} />}
      {el.kind === "mine"  && <MineShapes R={R} />}
      {el.kind === "beam"  && <BeamShapes R={R} />}
      {el.kind === "ring"  && <RingShapes R={R} />}
      {el.kind === "arrow" && <ArrowShapes R={R} />}

      {el.label && (
        <Text
          text={el.label}
          x={-R * 2.5}
          y={R * 1.8}
          width={R * 5}
          fontSize={R * 1.1}
          fill="#1E293B"
          align="center"
          listening={false}
        />
      )}

      {/* Selection highlight ring */}
      {isSelected && (
        <Circle
          radius={R * 2.2}
          fill="transparent"
          stroke="#3B82F6"
          strokeWidth={R * 0.18}
          dash={[R * 0.6, R * 0.4]}
          listening={false}
        />
      )}
    </Group>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function KonvaCanvas({
  canvasWidth,
  canvasHeight,
  elements,
  selectedId,
  onSelect,
  onChange,
}: KonvaCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [stageWidth, setStageWidth] = useState(600);

  // Responsive stage width — matches container
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => setStageWidth(el.clientWidth || 600);
    update();
    const obs = new ResizeObserver(update);
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const scale = stageWidth / canvasWidth;
  const stageHeight = Math.round(canvasHeight * scale);
  const R = computeR(canvasWidth, canvasHeight);

  // Transformer refs
  const trRef = useRef<Konva.Transformer>(null);
  const groupRefs = useRef<Record<string, Konva.Group | null>>({});

  useEffect(() => {
    const tr = trRef.current;
    if (!tr) return;
    if (selectedId) {
      const node = groupRefs.current[selectedId];
      if (node) {
        tr.nodes([node]);
        tr.getLayer()?.batchDraw();
      }
    } else {
      tr.nodes([]);
      tr.getLayer()?.batchDraw();
    }
  }, [selectedId, elements]); // re-run when elements change (new refs)

  // Click on empty canvas → deselect
  function handleStageClick(e: Konva.KonvaEventObject<MouseEvent>) {
    if (e.target === e.currentTarget) {
      onSelect(null);
    }
  }

  return (
    <div
      ref={containerRef}
      className="w-full overflow-hidden rounded-lg border border-slate-200 bg-white"
      aria-hidden="true" // The accessible controls below are the a11y interface
    >
      <Stage
        width={stageWidth}
        height={stageHeight}
        scaleX={scale}
        scaleY={scale}
        onClick={handleStageClick}
        onTap={() => onSelect(null)}
      >
        <Layer>
          {/* Canvas background */}
          <Rect
            x={0}
            y={0}
            width={canvasWidth}
            height={canvasHeight}
            fill="#F8FAFC"
          />

          {/* Canvas border */}
          <Rect
            x={0}
            y={0}
            width={canvasWidth}
            height={canvasHeight}
            fill="transparent"
            stroke="#CBD5E1"
            strokeWidth={R * 0.12}
            listening={false}
          />

          {/* Grid dots for spatial reference */}
          {Array.from({ length: Math.floor(canvasWidth / 10) + 1 }, (_, col) =>
            Array.from({ length: Math.floor(canvasHeight / 10) + 1 }, (_, row) => (
              <Circle
                key={`${col}-${row}`}
                x={col * 10}
                y={row * 10}
                radius={0.3}
                fill="#CBD5E1"
                listening={false}
              />
            ))
          )}

          {/* Elements */}
          {elements.map((el) => (
            <ElementNode
              key={el._id}
              el={el}
              R={R}
              canvasWidth={canvasWidth}
              canvasHeight={canvasHeight}
              isSelected={el._id === selectedId}
              onSelect={() => onSelect(el._id)}
              onChange={(updates) => onChange(el._id, updates)}
              groupRef={(node) => {
                groupRefs.current[el._id] = node;
                // React 19 cleanup
                if (node === null) {
                  delete groupRefs.current[el._id];
                }
              }}
            />
          ))}

          {/* Transformer — rotation only, no resize */}
          <Transformer
            ref={trRef}
            rotateEnabled={true}
            resizeEnabled={false}
            rotateAnchorOffset={20}
            padding={4}
            borderStroke="#3B82F6"
            borderStrokeWidth={R * 0.12}
            anchorStroke="#3B82F6"
            anchorFill="#FFFFFF"
            anchorSize={8}
          />
        </Layer>
      </Stage>
    </div>
  );
}

export default KonvaCanvas;
