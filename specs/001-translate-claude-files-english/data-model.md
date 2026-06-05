# Phase 1 Data Model: Translation Corpus, Glossary & Token Taxonomy

This feature has no database entities. The "data model" here is the structured description of the translation work: the file inventory, the token-class taxonomy that drives preserve-vs-translate decisions, and the canonical glossary.

## Entity: Translatable File

| Field | Description |
|---|---|
| `path` | Repo-relative path (stable; never renamed). |
| `kind` | `claude-root` \| `agent` \| `doc` \| `constitution`. |
| `has_frontmatter` | `true` for agent files (YAML), else `false`. |
| `prose_segments` | Spans translated to English. |
| `preserved_segments` | Spans kept byte-identical (see Token Taxonomy). |
| `verified` | Set true only when all six gates (contracts) pass. |

### Inventory

| Set | Count | Paths | Frontmatter | Priority |
|---|---|---|---|---|
| CLAUDE.md | 1 | `CLAUDE.md` | no | P1 |
| Agents | 28 | `.claude/agents/*.md` | yes (translate `description` only) | P2 |
| Docs | 34 | `docs/**/*.md` | varies | P3 |
| Constitution | 1 | `.specify/memory/constitution.md` | no | amendment (with P3 or last) |
| **Total content** | **64** | — | — | — |

**Excluded (must remain byte-identical)**: `.claude/skills/**`, `.claude/settings.json`, `.specify/**` except `constitution.md`, and all binary/fixture assets — `docs/Plan_Entrenamiento_XCO_Copa_Valle_2026.docx`, `docs/**/snapshots/*.{pdf,yml}`, images.

## Entity: Token Class (preserve vs. translate)

| Class | Action | Examples |
|---|---|---|
| Narrative prose | **Translate** | Section descriptions, rationale, notes, instructions. |
| Headings (prose) | **Translate** | `## Identidad` → `## Identity`. |
| File/dir paths | **Preserve** | `docs/01-marco-teorico.md`, `backend/app/services/permissions.py`. |
| Code identifiers | **Preserve** | `relationship_type`, `can_view_session`, `selectinload`. |
| Env vars + example values | **Preserve** | `AI_LOG_PROMPTS`, `JWT_ALGORITHM = HS256`. |
| Enum stored values | **Preserve** | `Pre-PHV`, `Circa-PHV`, `Post-PHV`. |
| Template / event names | **Preserve** | `training_session_invite`, `athlete_monthly_newsletter_v1`. |
| URLs / emails | **Preserve** | `https://mi-2yzi.onrender.com`, `entrenador@trochyruta.com`. |
| Commands / code blocks | **Preserve** (translate inline comments only) | `alembic upgrade head`; `# Activar entorno` → `# Activate venv`. |
| Dates / numbers | **Preserve** | `2026-05-19`, `p95 ≤ 500 ms`. |
| Status emoji + word | **Mixed** | `✅ Completo 2026-05-19` → `✅ Complete 2026-05-19`. |
| Proper nouns | **Preserve** | Trocha y Ruta, Sevilla, Ginebra, Valle del Cauca. |
| Output-format markers | **Preserve markers, translate labels** | `🚴 SESIÓN:` → `🚴 SESSION:`; `CALENTAMIENTO` → `WARM-UP`. |
| Deliberately-Spanish copy | **Preserve** | Product end-user strings referenced from code (out of scope anyway). |

## Entity: Glossary (canonical Spanish → English)

Apply uniformly across all files. Parenthetical acronyms are preserved (PHV, LTAD, RPE, RBAC, XCO, PMBIA).

| Spanish | English |
|---|---|
| entrenador / coach | coach |
| atleta / ciclista juvenil | athlete / youth rider |
| padre / madre / acudiente | parent / guardian |
| club deportivo | sports club |
| sesión de entrenamiento | training session |
| asistencia | attendance |
| rúbrica | rubric |
| antropometría | anthropometry |
| informe / reporte mensual | monthly report |
| boletín mensual | monthly newsletter |
| insignia | badge |
| convocatoria / convocado | call-up / called-up (roster) |
| carrera / válida | race / round (Copa Valle round) |
| podio / gap podio | podium / podium gap |
| corredor | rider |
| ranking de club | club ranking |
| proyección | projection |
| consentimiento | consent |
| privacidad de menores | minors' privacy |
| dosificación de carga | load dosing / training load |
| ventanas de entrenabilidad | windows of trainability |
| Pico de Velocidad de Crecimiento | Peak Height Velocity (PHV) |
| edad biológica / cronológica | biological / chronological age |
| brote de crecimiento | growth spurt |
| cadencia | cadence |
| diversión primero | fun first |
| habilidades > condición física | skills > fitness |
| principios no negociables | non-negotiable principles |
| marco teórico | theoretical framework |
| flujo de trabajo (workflow) | workflow |
| migración | migration |
| pruebas / tests | tests |
| auditoría de privacidad | privacy audit |
| despliegue | deploy / deployment |
| estado de implementación | implementation status |
| Completo / Completada / Pendiente | Complete / Completed / Pending |
| portada institucional | institutional cover page |
| distribución restringida | restricted distribution |
| señales de alerta | warning signs |
| vuelta a la calma | cool-down |
| calentamiento | warm-up |
| parte principal | main set |
| nutrición / suplementos | nutrition / supplements |
| prevención de lesiones | injury prevention |
| tapering (mini-tapering) | tapering (mini-taper) — keep "tapering" |

**Terms intentionally NOT translated** (English already, or domain-standard): tapering, XCO, gap, podio→podium but venue names stay, FastAPI/SQLAlchemy/Alembic/Pydantic/etc., shadcn/ui, TanStack Query, Zustand, Vite, Render, Hostinger, Resend, Gemini, Strava, Intervals.icu, Spond, Kinovea.

## State Transitions (per file)

```
untranslated → translated (prose pass + glossary)
            → verified (all six contract gates pass)
            → spot-checked (bilingual user sign-off; P1/P2 files)
            → merged
```

A file may not advance to `verified` if any gate fails; it returns to `translated` for correction.
