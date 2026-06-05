# Quickstart: Implement & Verify RPE OMNI Label Refactor

## What you're changing

One file's two constants, plus its test. ~15 lines. No backend, no migration.

## Step 1 — Edit `frontend/src/components/training/RubricSliders.tsx`

Replace the `RPE_LABELS` array (currently `Moderado` at index 3) with the validated mapping from [research.md](./research.md):

```ts
// OMNI-RPE 0–10 verbal anchors (español neutro). "Moderado" is centered at 5,
// matching the validated OMNI scale (Robertson) and the modern 0–10 training scale.
// See specs/002-rpe-omni-scale-labels/research.md.
const RPE_LABELS = [
  "Reposo",      // 0
  "Muy fácil",   // 1
  "Fácil",       // 2
  "Ligero",      // 3
  "Algo fácil",  // 4
  "Moderado",    // 5
  "Algo duro",   // 6
  "Duro",        // 7
  "Muy duro",    // 8
  "Muy muy duro",// 9
  "Máximo",      // 10
];
```

Then check `RPE_FACES`: confirm index 5 reads neutral/moderate (not "tired"). Keep the array length at 11; adjust only the glyph(s) that contradict the new wording.

Do **not** touch: the slider's `min/max/aria-*` wiring, the `field.onChange`, the 1–5 rubric sliders, or `RUBRIC_LABELS`.

## Step 2 — Update `frontend/src/components/training/RubricSliders.test.tsx`

Add assertions for the contract guarantees (see [contracts/rpe-omni-labels.md](./contracts/rpe-omni-labels.md)). Example:

```ts
it("muestra 'Moderado' en el valor 5, no en el 3 (RPE OMNI)", () => {
  render(<Wrapper defaultValues={{ rpe_omni: 5 }} />);
  expect(screen.getByText(/5 — Moderado/)).toBeInTheDocument();
});

it("el valor 3 ya no es 'Moderado'", () => {
  render(<Wrapper defaultValues={{ rpe_omni: 3 }} />);
  expect(screen.queryByText(/3 — Moderado/)).not.toBeInTheDocument();
});

it("extremos: 0 = Reposo, 10 = Máximo", () => {
  const { rerender } = render(<Wrapper defaultValues={{ rpe_omni: 0 }} />);
  expect(screen.getByText(/0 — Reposo/)).toBeInTheDocument();
  rerender(/* wrapper with rpe_omni: 10 */);
  expect(screen.getByText(/10 — Máximo/)).toBeInTheDocument();
});
```

(The existing `rpe_omni: 3` aria test at line 53–59 still passes — it asserts `aria-valuenow`, not the label.)

## Step 3 — Verify

```bash
cd frontend
npx vitest run src/components/training/RubricSliders.test.tsx src/components/training/RubricSliders.a11y.test.tsx
npx tsc --noEmit
npx eslint src/components/training/RubricSliders.tsx
```

Manual check (coach tablet view): open a session → attendance → drag the RPE OMNI slider; confirm "Moderado" appears at 5, wording rises smoothly 0→10, and the highlighted face matches the word.

## Definition of done

- [ ] `RPE_LABELS` redistributed; `Moderado` at index 5.
- [ ] `RPE_FACES` midpoint reads neutral; length still 11.
- [ ] Tests assert G1–G4 from the contract; full `RubricSliders` + a11y suites green.
- [ ] `tsc --noEmit` and `eslint` clean.
- [ ] No backend/schema/migration change in the diff.
