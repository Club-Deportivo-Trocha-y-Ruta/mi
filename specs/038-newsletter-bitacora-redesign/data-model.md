# Data model — feature 038

## 1. StageLog (Pydantic, `app/services/training/stage_log.py`; TS mirror `frontend/src/types/stageLog.types.ts`, Zod `schemas/stageLog.ts`)

```python
class WaypointKind(str, Enum): first_session, race, streak, badge, best_session, next_race
class BlockState(str, Enum): ai, edited, static, hidden, empty
class SummitKind(str, Enum): race, training

class Waypoint(BaseModel):
    kind: WaypointKind
    date: date
    label: str              # "Válida 3 · P2", "Racha de 10", "Asistencia 100 %"
    sublabel: str | None    # "La Cumbre", "+4,1 % al P1" (own gap only)
    icon: str               # lucide name: flag | award | flame | star | map-pin | compass
    is_future: bool = False

class EffortWeek(BaseModel):
    week_label: str         # "1–7 jun"
    sessions_planned: int
    sessions_attended: int
    mean_rpe: float | None

class Summit(BaseModel):
    kind: SummitKind
    title: str              # "P2 en la Válida 3"
    detail: str | None      # "Copa Valle · Prejuvenil A Femenino · +4,1 % al P1"
    caption: str | None     # AI / static, ≤ 25 words
    date: date | None

class Observation(BaseModel):
    claim: str              # ≤ 35 words
    evidence: str           # ≤ 20 words, ≥ 1 number present in the prompt context
    block_ref: Literal["attendance", "technical", "race", "badges", "streak"]

class AnalystReading(BaseModel):
    headline_family: str    # ≤ 30 words
    action_family: str      # ≤ 30 words
    valida_label: str       # "Válida 3 · Copa Valle"
    source_insight_id: int  # coach DTO only — stripped by to_parent_dto()

class NextRace(BaseModel):
    label: str; date: date; venue: str | None; priority_label: str | None

class NextSegment(BaseModel):
    focus_groups: list[str]         # ≤ 4, skill families (024 grouping)
    next_race: NextRace | None
    text: str | None                # AI / static, ≤ 40 words

class FamilyCompass(BaseModel):
    conversation_question: str      # ≤ 30 words, ends with "?"
    monthly_challenge: str          # ≤ 30 words, process-based, no supplements / calories
    what_to_watch: str              # ≤ 30 words, tied to the next segment

class BadgeView(BaseModel):
    code: str; label: str; icon: str; earned_at: date | None

class PhotoView(BaseModel):
    thumbnail_url: str; caption: str | None

class StageLog(BaseModel):
    schema_version: Literal[2] = 2
    stage_number: int               # months since the season's first session (1-based)
    period_label: str               # "Junio 2026"
    is_current_month: bool
    athlete_first_name: str         # rendered only; never sent to the provider
    athlete_reference: str          # "su hija" | "su hijo" | "su deportista"
    stage_title: str                # ≤ 20 words
    trail: list[Waypoint]           # 3..6
    summit: Summit | None
    observations: list[Observation] # exactly 3 with narrative; 0..3 static otherwise
    analyst_reading: AnalystReading | None
    effort_profile: list[EffortWeek]
    next_segment: NextSegment | None
    family_compass: FamilyCompass | None
    badges: list[BadgeView]
    photos: list[PhotoView]
    coach_note: str | None          # ≤ 60 words
    block_states: dict[str, BlockState]   # coach DTO only
    grounding_violations: list[str]       # coach DTO only
```

`to_parent_dto(stage_log, hidden_blocks) -> dict`: same shape minus `block_states`, `grounding_violations`, `analyst_reading.source_insight_id`; hidden blocks become `None` / `[]`. A test asserts the exact key set (allow-list, not deny-list).

## 2. StageNarrative (LLM output, `use_cases/athlete_monthly_newsletter_v2.py`)

```python
class AnalystReadingText(BaseModel):
    headline_family: str; action_family: str

class StageNarrative(BaseModel):
    stage_title: str
    summit_caption: str | None
    observations: list[Observation]         # exactly 3
    next_segment_text: str | None
    family_compass: FamilyCompass
    analyst_reading: AnalystReadingText | None   # only when FamilyInsightInput was given
    model: str
    prompt_version: str                     # "athlete_monthly_newsletter_v2"
    confidence: Literal["low", "medium", "high"]
```

Persisted in `athlete_monthly_newsletters.ai_narrative` as `{"version": 2, ...}`; legacy keys (`strengths`, `area_to_develop`, `milestone`) are absent — `AiNarrativeOut` already tolerates `None`.

`FamilyInsightInput` (from `family_translation.filter_for_family`): `{headline: str, action_text: str, action_category: str, valida_label: str}` — nothing else leaves the InsightV3.

## 3. Tables

### `athlete_monthly_newsletters` (ALTER)

| Column | Type | Notes |
|---|---|---|
| `content_version` | SMALLINT NOT NULL DEFAULT 1 | 1 legacy, 2 bitácora |
| `stage_log_json` | JSON NULL | StageLog v2, re-derived on PATCH |
| `stage_overrides` | JSON NULL | `{block: value}` for `stage_title`, `summit_caption`, `observations`, `analyst_reading`, `next_segment_text`, `family_compass` |
| `hidden_blocks` | JSON NULL | subset of `["analyst_reading", "photos", "badges", "coach_note"]` |
| `coach_note` | VARCHAR(600) NULL | ≤ 60 words, name-redacted before persist |
| `read_at` | DATETIME NULL | first web read by a parent |
| `read_by_user_id` | INT NULL FK `users.id` ON DELETE SET NULL | |

### `newsletter_delivery_events` (NEW)

| Column | Type |
|---|---|
| `id` | INT PK AUTO_INCREMENT |
| `newsletter_id` | INT NOT NULL FK `athlete_monthly_newsletters.id` ON DELETE CASCADE |
| `parent_user_id` | INT NULL FK `users.id` ON DELETE SET NULL |
| `event_type` | ENUM(`sent`, `delivered`, `opened`, `clicked`, `bounced`, `web_read`) — `values_callable` per project convention |
| `provider_message_id` | VARCHAR(128) NULL, INDEX |
| `provider_event_id` | VARCHAR(128) NULL, UNIQUE (svix-id → idempotency) |
| `occurred_at` | DATETIME NOT NULL |
| `created_at` | DATETIME NOT NULL DEFAULT now |

Index `(newsletter_id, event_type)`. No emails, names, IPs or user agents are stored.

### `NewsletterStatus`

Unchanged (`draft`, `approved`, `sent`, `failed`, `outdated`). "Leído" is derived: `status == sent and read_at is not None`.

## 4. Coach DTO additions (`AthleteNewsletterRead`)

`content_version: int`, `stage_log: StageLog | None`, `stage_overrides: dict | None`, `hidden_blocks: list[str]`, `coach_note: str | None`, `read_at: datetime | None`, `delivery: list[DeliveryRow]` with `DeliveryRow = {parent_user_id: int | None, email_masked: str, has_account: bool, sent_at, delivered_at?, opened_at?, web_read_at?, bounced: bool}`.

`AthleteNewsletterPatch` gains `stage_overrides`, `hidden_blocks`, `coach_note`, `selected_race_insight_ids` (reorder only — must be a permutation of the current list).

## 5. Parent DTOs (`schemas/parent_newsletter.py`)

- `ParentNewsletterListItem = {id, athlete_id, year, month, period_label, stage_title, sent_at, read_at}`
- `ParentNewsletterOut = {id, athlete_id, year, month, period_label, sent_at, read_at, has_pdf, stage_log: <to_parent_dto>}`
- `MyAthleteOut` (existing) gains `unread_newsletters: int`.

## 6. Frontend state

- Studio: `stage_log` from the query + local `overridesDraft` merged by `applyOverrides(stageLog, overrides)` (pure, tested) for the optimistic preview; PATCH on blur / explicit save; server response replaces the cache.
- Parent page: `useMarkNewsletterRead(id)` fires once per `id` per session (`sessionStorage["bitacora-read:<id>"]`).
