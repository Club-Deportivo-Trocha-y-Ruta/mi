# Funder-Style Monthly Report — Reference Format

**Purpose:** canonical structure of the monthly technical report that the club delivers to its
funders (Imderty, allied foundations). Derived from the June 2026 and July 2026 editions, both
approved by the coach. Use this as the target format whenever generating, refactoring or
validating a monthly report — including the module's AI-generated blocks
(see [`design.md`](design.md)).

> **Privacy — read first.** The real reports contain full names, attendance and results of minors.
> This repository is **public**, so the actual files are stored locally in
> `docs/11-informe-tecnico-mensual/referencias/` and are **git-ignored on purpose**. Never commit
> them, never paste their tables into issues, commits or specs. This document is the only
> committed artifact and it is anonymized.

## Reference files (local only, not versioned)

| File | Notes |
|---|---|
| `referencias/Informe-Mensual-Tecnico-Junio-2026.pdf` | Baseline layout. Departmental Championship (Ginebra) as the competition of the month |
| `referencias/Informe-Mensual-Tecnico-Julio-2026.pdf` | Adds a GPS-evidence table (Strava) and two competitions of different nature |
| `referencias/Informe-Mensual-Tecnico-Julio-2026.docx` | Editable source of the July edition, with the coach's photos already placed |

If the folder is empty on a fresh clone, ask the coach for the last approved edition — the format
is reconstructible from this document, but the tone is best calibrated against a real one.

## Document structure

```
INFORME MENSUAL TÉCNICO DE ACTIVIDADES        ← title, dark blue, bottom rule
  Nombre del Proyecto / Entidad ejecutora / Período del informe

Actividades Ejecutadas
  GRUPO DE ALTO RENDIMIENTO
    OBJETIVO                    — 1 paragraph: what the month's training aimed at
    PLAN DE ENTRENAMIENTO       — how the plan was structured (3-4 bulleted work types)
    DESARROLLO DE ACTIVIDADES   — what actually happened, then:
        · Resumen de sesiones           (table: indicator / value)
        · Focos técnicos cubiertos      (bulleted list, "<focus> — N sesiones")
        · Detalle de sesiones ejecutadas (table: fecha, hora, foco, lugar, min, asistencia)
        · Contenido de las sesiones más representativas (optional, 5-6 bullets)
        · [PHOTO BLOCK 1]
        · Evidencia de recorridos GPS (Strava) (table, July onward)
        · Asistencia y rúbrica por atleta (table) + totals line
    PARTICIPACIÓN EN COMPETENCIA
        · Resumen del período           (table: atleta, categoría, prueba, pos., evento)
        · One sub-block per event: context paragraph + results table(s) +
          "Aspectos destacados:" paragraph
        · [PHOTO BLOCK 2]
    RESULTADOS OBTENIDOS        — 2-3 paragraphs interpreting the month
    [PHOTO BLOCK 3]
    CONCLUSIONES                — compliance, competitive read, recommendations for next cycle
  Restricted-circulation notice (Ley 1581/2012 + Decreto 1377/2013)
```

## Editorial rules

1. **Language:** español neutro (Colombia). Headings underlined and bold; section titles in caps.
2. **Every hard figure has one canonical home.** Volume, weekly average, rubric averages and RPE
   live in *Resumen de sesiones*. Later sections interpret them and refer back
   ("ver Resumen de sesiones") instead of restating the numbers. Repeating a figure three or four
   times across sections is the most common defect in drafts.
3. **Competition positions may be restated** in `RESULTADOS OBTENIDOS` / `CONCLUSIONES`. Funders
   read the closing sections standalone; this repetition is deliberate, not a defect.
4. **Attendance totals must equal the column sums** of the per-athlete table. If an adult
   companion is dropped from the table, drop them from the totals too.
5. **Never state a gap against a leader without saying which classification it refers to**
   (per-stage vs. accumulated). This produced a real error in the July draft.
6. **`Min.` in the session table is the planned block**, not GPS time. GPS may be longer
   (transfers) — the note under the Strava table must say so, and must explain why fewer sessions
   appear there than in the session table.
7. **Photo blocks are bordered empty tables** with an italic gray placeholder
   `[ ESPACIO PARA FOTOGRAFÍAS — <what goes here> ]`; the coach pastes the images in Word.
8. **Spelling of recurring terms:** `VO2 Máx`, `Zona 2` / `Zona 3`, `tapering`, `XCO`, `gymkhana`.

## Sources feeding a monthly edition

| Section | Source |
|---|---|
| Sessions, attendance, rubrics, technical focuses | `GET /api/training-sessions` + `/{id}/attendance` (month range) |
| Narrative blocks | Monthly report module (AI pre-draft, coach edits) — see `workflow.md` |
| GPS evidence | `strava_url` of each session; distance / elevation / moving time |
| Competition results | Copa Valle results module, official bulletins (PDF), club news site |
| Photos | Session media, added by the coach in Word |
