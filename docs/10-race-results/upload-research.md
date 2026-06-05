# Research — Copa Valle PDF Upload UI

**Date**: 2026-05-20
**Strategy**: deep
**To inform**: /sc:design upload race-results
**Branch**: race-results-v2-foundation

---

## Current ingestion state

### Deterministic F1.7 pipeline ready to wrap in HTTP

The service layer is **self-sufficient** and decoupled from the CLI. The consumer only needs to replicate what `scripts/ingest_race.py` does step by step.

`backend/app/services/race/ingestor.py:138-402` — `RaceIngestor.ingest_event(...)`:

- **Inputs**: `EventMeta`, `results_by_category: dict[str, list[ResultsRow]]`, `general_by_category` (optional), `match_decisions: dict[str, Optional[int]]`, `pdf_results_sha256`, `pdf_general_sha256`, `ingested_by_user_id`.
- **Output**: `IngestReport` (`event_id, series_id, competitors_created, competitors_updated, results_inserted, results_skipped, tyr_count, warnings: list[str]`).
- **Transactionality**: a single `await self.db.commit()` at the end of the method (`ingestor.py:378`); any exception triggers `rollback()` (`ingestor.py:400-402`).
- **Idempotency**: if `RaceImport` already exists with `status=committed` and same `sha256`, aborts without writing rows and returns `IngestReport` with `results_inserted=0` and explanatory warning (`ingestor.py:220-238`).
- **No auto-assign**: applies `athlete_id` only if the coach confirmed it in `match_decisions` (inviolable rule — `ingestor.py:298-310`).

`backend/app/services/race/pdf_parser.py:211-302` and `:340-435` — `parse_results_pdf(Path) -> dict[code, list[ResultsRow]]` and `parse_general_pdf(Path) -> dict[code, list[GeneralRow]]`:

- Accept **disk paths** (not buffers). This requires writing the upload to tmp before parsing, or refactoring the signature to accept `BinaryIO` (decision for `/sc:design`).
- `parse_event_header(Path)` extracts `valida_num + location + event_date` auto-completing 80% of `EventMeta`.
- Expected size: real fixtures `valida_iv_2026_resultados.pdf` = 246 KB (10 pages, 26 categories, 227 riders), `valida_iv_2026_general.pdf` = 160 KB (12 pages, 339 rows). Any Federation PDF fits comfortably in 1-2 MB.

`backend/scripts/ingest_race.py:266-330` — `ingest` command:

- Interactive flow (default): parse → auto header → prompts (weather, temp, surface, altitude, notes) → top-3 per TyR → confirm → execute.
- `--non-interactive` mode: reads `--event-meta YAML` + `--match-decisions YAML` for CI/deterministic tests.
- **Does NOT exist** a separate `ingest validate` subcommand. The "dry-run" concept has `RaceImportStatus.dry_run` enum (`race_import.py:36-48`) but the code never emits it — always does `pending → committed`. Need to expose a real dry-run from the ingestor (important for wizard preview).

`backend/app/services/race/normalizer.py` + `matcher.py`:

- `is_trocha_y_ruta(club, threshold=85)` decides if a competitor belongs to the club (hybrid fuzzy `ratio`/`partial_ratio` with length guard — `normalizer.py:176-208`).
- `match_athletes(competitor_name, competitor_club, competitor_category, athletes, threshold=90)` returns top-3 `MatchCandidate(athlete_id, full_name, score, age_decimal, reason)`. **Does not touch DB** (`matcher.py:131-227`); the caller pre-loads athletes.
- Typical outputs: 100% match (~score 95 with age boost), no candidate (empty list), homonyms (2-3 candidates with close scores → coach decides tie-breaker).

---

## SFTP storage — viable?

**Short answer**: yes, with caveats. The existing wrapper works almost without changes but there are limitations to document.

### What works

`backend/app/services/training/storage_sftp.py`:

- **Not real SFTP**: despite the name, it is **FTPS** (FTP over TLS, port 21) — Hostinger Shared does not expose SFTP/SSH on port 22 (`storage_sftp.py:1-16`).
- Generic public API: `upload_bytes(content: bytes, relative_path: str) -> tuple[storage_path, storage_url]` and `delete_object(storage_path)`.
- **Does not discriminate by extension** — uploads any `bytes`. PDFs work the same as JPGs.
- **Automatic local fallback**: if `HOSTINGER_SFTP_*` envs are missing, writes to `static/uploads/media/` and builds URL `/static/uploads/media/...` (mounted in `main.py:53-55`). Zero configuration for dev/tests.

### Important caveats

1. **Public URL without auth**: `storage_url` is public (`hostinger_public_base_url/...`). For PDFs with results these are **already public information** (the Federation publishes them), but the storage is accessible by path-guessing. Mitigation: prefix with UUID (like `media_files.py:180`), do not use original filename.
2. **No TLS verification** (`storage_sftp.py:50-61`): Hostinger Shared uses a generic cert without SAN, so `check_hostname=False, verify_mode=CERT_NONE`. The session is encrypted but not authenticated. Accepted by the project for photos/videos; applies equally here.
3. **Render free tier compatibility**: the wrapper does `asyncio.to_thread(...)` to not block the event loop (`storage_sftp.py:188`). Cold start of ~50s when Render wakes up does not affect FTPS post-warmup. **Confirmed to work in production** — same wrapper used by F1.6 media.
4. **Envs required in Render** (pending step 9 of F1.6 per `CLAUDE.md`): `HOSTINGER_SFTP_HOST/PORT/USER/PASS/REMOTE_DIR` + `HOSTINGER_PUBLIC_BASE_URL`. If not configured, F1.6 media and this new upload will fall back to local — which in Render free tier is **ephemeral** (filesystem is wiped on redeploy). **Silent operational blocker** for real users if not set first.
5. **No size cap in the wrapper**. The cap comes from the caller (`media_files.py:154-166` reads `settings.media_max_photo_mb`/`max_video_mb`). For PDFs, `settings.race_max_pdf_mb` must be introduced (suggestion: 8 MB).
6. **No signed URLs**: the URL is static and permanent. For PDFs this is probably OK (they are already public).

### Reference real usage pattern

`backend/app/services/training/media_files.py:140-199` — `save_session_media`:

- Reads bytes with defensive cap (`max_bytes + 1`).
- Validates magic bytes by extension (`_check_magic_bytes`).
- Generates `base_name = uuid.uuid4().hex` → `relative_path = f"sessions/{session_id}/{base_name}{ext}"`.
- Uploads via `storage_sftp.upload_bytes`, returns `StoredMedia(storage_url, storage_path, mime_type, size_bytes, ...)`.

For PDFs the pattern simplifies (no thumbnail, no EXIF strip, no width/height). Still applies: magic bytes, size cap, UUID in path.

---

## Data model — gaps

### What `RaceImport` already has

`backend/app/models/race_import.py`:

- `id, filename(200), sha256(CHAR 64), series_id, status(enum), stats_json, error_log(text), imported_by_user_id, imported_at`.
- Indexes: `imported_at`, `sha256`, `(status, sha256)`. Adequate for fast deduplication.
- Already stores **`imported_by_user_id`** → resolves "who uploaded".
- Already stores **`filename`** (200 chars) → resolves "original name".
- Status enum includes `dry_run` — **supported in model but never used in code**.

### Gaps to fill for upload UI

1. **Does not store `storage_path` or `storage_url`** of the uploaded PDF. This means that after ingestion we cannot re-download the original PDF from the UI. Decision for `/sc:design`: add `pdf_storage_path: String(500) NULL` + `pdf_storage_url: String(500) NULL`, or not store it (always reload from coach's local).
2. **Does not distinguish RESULTS vs GENERAL**: has `filename` + `sha256` but a single record per ingestion. Today the ingestor only deduplicates on the RESULTS sha (`ingestor.py:220-238`). If we want GENERAL traceability, we need additional columns (`general_filename`, `general_sha256`, `general_storage_path`) or a `kind: enum('results','general')` pattern with two rows. **Suggested decision**: extend the single row — the GENERAL sha is already passed but only logged (`ingestor.py:175`), storing it in a column would also deduplicate that PDF.
3. **`RaceImport` does not link directly to `RaceEvent`**: only via `series_id`. The association with the specific event is discovered indirectly by `imported_at` or by `RaceResult.imported_from_id` (FK that exists in migration delta — confirmed in `ingestor.py:357`). For the UI this forces a JOIN — adding `event_id NULL` to `RaceImport` would simplify history queries.
4. **`RaceEvent.pdf_results_filename` / `pdf_general_filename`** (`race_event.py:120-121`) already exist as `String(255) NULL` and are populated in the upsert (`ingestor.py:460-461, 484-486`). **Overlap with `RaceImport.filename`** — currently both store the same thing. Not a bug, cheap redundancy.

### Model conclusion

Minimum suggested migration (to confirm in design):

```sql
ALTER TABLE race_imports
  ADD COLUMN event_id INT NULL,
  ADD COLUMN kind ENUM('results','general') NOT NULL DEFAULT 'results',
  ADD COLUMN storage_path VARCHAR(500) NULL,
  ADD COLUMN storage_url VARCHAR(500) NULL,
  ADD FOREIGN KEY (event_id) REFERENCES race_events(id) ON DELETE SET NULL;
```

If the decision is "don't store PDFs" (only process and discard), only `event_id` + `kind` are needed.

---

## Existing project patterns

### Backend — reference upload endpoint

`backend/app/routers/training_sessions.py:690-786` — `POST /training-sessions/{id}/route-file`:

Direct pattern for multipart + magic bytes + size cap + RBAC. Reusable almost 1:1:

- Signature: `file: Annotated[UploadFile, File(...)], db, current_user = Depends(require_role([admin, coach]))`.
- Extension validation: `filename.endswith(".gpx") / .fit`.
- Content-type validation (whitelist by extension).
- Defensive cap: `raw = await file.read(max_size + 1)` → if exceeded, 400.
- Magic bytes: FIT requires first byte `0x0E` + header ≥14 (`training_sessions.py:756-761`).
- Rewind for handoff to service: `file.file = io.BytesIO(raw)` (`training_sessions.py:764-765`).
- Service call: `await training_svc.route_files.save_route_file(file, session_id)`.

`backend/app/routers/training_sessions.py:835-926` — `POST /training-sessions/{id}/media`:

More complete pattern (multipart with additional fields like `athlete_ids: Form(str)`, `consent_ack: Form(bool)`). Useful if we want to upload **2 files + event meta in a single POST** or use `Form` for `match_decisions` JSON. Suspected we need **2 endpoints** (wizard step) and not a mega-POST.

### Frontend — drag-and-drop already built

`frontend/src/components/training/MediaUploadZone.tsx`:

- Native drag & drop with keyboard support (Enter/Space on `role="button"`).
- Pre-upload validation: extension + size (constants `MAX_PHOTO_MB = 10`, `MAX_VIDEO_MB = 50`).
- UI: idle dropzone → form with `pendingFile` + caption + athlete chips + consent checkbox + submit with loader.
- Consistent `data-testid` (`media-upload-dropzone`, `media-file-input`, `media-submit-button`) — facilitates E2E.
- **Reusable almost 1:1** changing: accepted types (`.pdf`), cap (8 MB), form fields (results-pdf / general-pdf / event meta).

`frontend/src/api/sessionMedia.ts:23-41` — `uploadSessionMedia(sessionId, payload)`:

Already-validated axios + `FormData` + `multipart/form-data` pattern. For 2 files: `formData.append("resultados_pdf", f1); formData.append("general_pdf", f2);`.

`frontend/src/api/raceAnalysis.ts:24-32` and `:106-136` — race-analysis-specific conventions (`/api/race-analysis/...`, authenticated blob download). **The new endpoint should live under the same prefix** for coherence (`POST /api/race-analysis/imports/...`).

### Frontend — landing to inject

`frontend/src/routes/results/RaceAnalysisPage.tsx:111-209`:

3 current tabs: `new` (New analysis), `active` (Active runs), `history` (Historical insights). Upload naturally enters as **4th tab "Load results"** (see §UX). The `history` tab is a placeholder — could also be reused for "Prior ingestions + insights" if we want to minimize tabs.

---

## PDF upload security

OWASP File Upload checklist + project state:

| Control | State in project | Note |
|---|---|---|
| **Magic bytes verification** | Pattern exists in `media_files.py:65-87` and `training_sessions.py:756`. For PDF: validate `%PDF-` (`b"%PDF-"`) in first 5 bytes. | To implement in PDF service. |
| **Maximum size** | `await file.read(max_bytes + 1)` pattern validated. Recommendation 8 MB (real fixture = 246 KB; leaves 32x margin). Render free tier accepts large uploads without explicit config; the bottleneck is HTTP timeout, not body size. | To implement; new setting `race_max_pdf_mb`. |
| **Extension whitelist** | `filename.endswith(".pdf")` pattern validated. | Trivial. |
| **Content-type whitelist** | Pattern in `_GPX_CONTENT_TYPES`. For PDFs: `application/pdf`, `application/octet-stream`. | Trivial. |
| **defusedxml for XXE** | `defusedxml>=0.7` already in `requirements.txt`. `pdfplumber` does NOT use exposed external XML; PDF is its own binary. **Not directly applicable** to this pipeline — pdfplumber processes binary streams + text extraction via PDFMiner. Low XXE risk in pdfplumber, not documented as an active vector. | OK for now; document as accepted risk. |
| **Path traversal in filename** | `uuid.uuid4().hex + ext` pattern in `media_files.py:180`. **Critical**: do not use `file.filename` to build `storage_path`. Store original in `filename_original` (separate column). | To implement. |
| **RBAC: coach + admin only** | `Depends(require_role([UserRole.admin, UserRole.coach]))` pattern consistent across all routers. Parents blocked. | To apply. |
| **Rate limiting** | **No global middleware** (verified in `app/main.py` and grep `slowapi/RateLimit`). There is ad-hoc throttle in notifications (`calendar/notifications.py`) — simple in-memory pattern. PDF upload is an infrequent operation (1-2 per month); DoS attack via upload is not realistic. **Acceptable risk without rate limit MVP**; still, consider a dumb guard: max 5 uploads/min per user_id in memory. | Optional MVP. |
| **Parsing sandbox** | `pdfplumber` runs in-process. If a malicious PDF exploits a CVE in pdfminer, it would compromise the worker. Mitigation: **broad try/except** + timeout (to evaluate — pdfplumber does not expose native timeout API, would require `asyncio.wait_for(...)` in thread). | Consider for F2 hardening. |
| **Upload auditor** | `RaceImport.imported_by_user_id` already covered. Structured log: `logger.info("race_pdf_uploaded user_id=%d filename=%s sha=%s", ...)` without PII. | To implement in service. |
| **Logs without PII** | Inviolable restriction (CLAUDE.md). Pattern already followed by ingestor (warnings use `bib + cat_code`, not names). | OK by design. |

### Identified high risks

- **Single point of failure parser**: if pdfplumber raises an unhandled exception with a malformed PDF, the endpoint must return 422 with actionable message ("Corrupt or unofficial PDF"), not 500. Verify that `parse_results_pdf` doesn't do silent `raise`.
- **Memory bloat with large PDFs**: pdfplumber loads pages into memory. With 8 MB cap and 512 MB RAM free tier in Render, the risk is theoretical — but opening 3 concurrent PDFs could overwhelm. Mitigation: serialize uploads with a lock or semaphore if the pattern becomes common (not MVP).

---

## UX reference

### Recommended decision: new "Load results" tab

In `RaceAnalysisPage.tsx`, insert as the second tab (between "New analysis" and "Active runs"). Justification:

- "New analysis" starts an agent on already-ingested data → conceptually later.
- Loading is a periodic operation (1-2 per month, after each round) and triggers the rest of the flow.
- Dedicated tab allows showing **history of prior ingestions** below (querying `RaceImport` filtered by series 2026) — small and useful feature that the CLI lacks.

Wizard structure (3 steps):

```
Step 1: Select files
  ├── RESULTS dropzone (.pdf, max 8 MB)
  ├── GENERAL dropzone (.pdf, max 8 MB, optional)
  ├── Auto-detect header → shows "Round IV · Cali · 17-May-2026"
  └── [Next]

Step 2: Confirm metadata + matches
  ├── Pre-filled EventMeta form (valida_num, location, event_date editable;
  │   climate/temperature/surface/altitude/notes optional)
  ├── TyR matches table: bib | PDF name | top-3 candidates (radio buttons) |
  │   "skip" | "new athlete"
  ├── Warnings banner (unknown categories, anomalous times)
  └── [Back] [Next]

Step 3: Preview + commit
  ├── Summary like IngestReport (categories, riders, TyR, decisions taken)
  ├── Dry-run: backend validates without writing (requires implementing real dry-run
  │   in ingestor — detected gap)
  ├── If idempotent (sha already committed): yellow banner "This PDF was
  │   ingested on YYYY-MM-DD. Re-process?" → No by default
  └── [Confirm and ingest] → loading → final IngestReport
```

### Components to reuse

- **Dropzone**: clone simplified `MediaUploadZone` (without thumbnails, athlete chips, consent).
- **Stepper**: no reusable component in `components/ui/`. `RaceAnalysisPage` uses `@radix-ui/react-tabs` for non-sequential steps — for sequential wizard the canonical shadcn pattern is custom `Stepper` or reuse `Tabs` with `disabled` on unreached steps.
- **Matches table**: clone visual pattern from `AttendanceTable.tsx` (`frontend/src/components/training/`); supports selection and inline feedback.
- **Warnings banner**: reuse `ExplainModeBanner` / shadcn banners (`Alert`).
- **Spinner / loading**: `Loader2` from `lucide-react`, pattern already used.

### States to manage

| State | UX |
|---|---|
| Idle pre-upload | Empty dropzone with CTA |
| Drag-over | Highlighted border (pattern already in MediaUploadZone) |
| Parsing (post-upload) | Spinner "Analyzing PDF..." (parsing can take 2-5s with pdfplumber) |
| Header not detected | Empty form + warning "We could parse the PDF but didn't detect the header. Complete the data manually." |
| Unknown category | Non-blocking warning in step 2 with raw code |
| Bib without top-3 match | "skip" radio pre-selected, link "→ Create new athlete" (defer creation to separate UI) |
| Dry-run OK | Green banner with prior counts before commit |
| sha duplicate | Yellow banner + "Force re-ingestion" option (not recommended; admin only) |
| Commit OK | Formatted `IngestReport` + CTA "Go to New analysis" |
| Parser error | Red banner "PDF is not in official Federation format" + collapsed technical log |
| Network error | Toast + retry button |

---

## Input validation

### Hard rules (from `EventMeta` schema and model)

- `season ∈ [2020, 2100]` (`schemas/race.py:47`).
- `valida_num ∈ [1..7] ∪ {99}` with explicit validator (`schemas/race.py:61-69`).
- `name max 200`, `location max 150`, `climate max 60`, `weather_notes` free, `pdf_results_filename max 255`, `pdf_general_filename max 255`.
- `temperature_c ∈ [-10, 50]` with validator (`schemas/race.py:71-80`).
- `altitude_msnm ∈ [0, 6000]`.
- `surface_condition` enum: `seca | humeda | barro | lluvia | mixta`.
- `RaceSeries` UNIQUE `(name, season_year)` (`race_series.py:34-36`).
- `RaceEvent` UNIQUE `(series_id, sequence_number)` (`race_event.py:80`).
- `RaceImport.sha256 CHAR(64)` — always present.

### Idempotency behavior

- Re-upload of **same PDF (same sha256)** with status `committed` → ingestor **does not write** new rows and returns report with `results_inserted=0` + warning. Operation is **safe by default**.
- Re-upload with **different valida_num** → creates/updates another `RaceEvent` (upsert by `series_id, sequence_number`). The coach can update weather/surface without touching SQL (`ingestor.py:467-487`).
- Re-upload **corrected PDF** (same round, different content → different sha) → writes additional rows. `RaceResult` has UNIQUE `(event_id, category_id, competitor_id)` → if there is already a result for that triplet, **it is skipped** with `results_skipped++`. **Limitation**: if the correction changes the time of an existing result, it is not updated — the old value remains. This is by F1.7 design (reviewing is the coach's responsibility via SQL or future `race_result_revisions` UI). Document for the coach.

### Soft rules (warnings, not blocking)

- Category in RESULTS but not in seed → `ValueError` that **does block** the transaction (`ingestor.py:276-280`). Decision: in UI capture and show "unknown category, contact admin to extend seed".
- Anomalous time (<25 min in INF/PJUV/JUN or <2 min in TET or <5 min in PRE) → warning with `bib + cat`, does not block (`ingestor.py:328-339`).
- Bib in GENERAL absent in RESULTS → no automatic warning (would be noisy). Edge case documented in `edge-cases.md §4.12`.

### Non-obvious edge cases

- **`GENERAL` is not CSV-importable**: the Federation only publishes GENERAL in PDF (`scripts/ingest_race.py:280-283`). RESULTS does accept `.csv/.tsv/.txt` (Sevilla 2026 fixture). The upload UI must allow RESULTS `.pdf` or `.csv`, GENERAL only `.pdf`. `/sc:design` decision: support CSV in MVP or only PDF?
- **Header not detected** → in CLI it asks interactively (`ingest_race.py:521-527`). In UI: manual step 2 form covers this case.
- **Series 2026 already exists**: the upsert by `(name="Copa Valle de Ciclomontañismo", season_year=2026)` is transparent (`ingestor.py:408-427`). The coach doesn't need to create series beforehand.

---

## Open questions for /sc:design

1. **Store the PDF in storage or just process it?**
   - In favor of storing: re-process without asking the coach, audit, troubleshoot parser with real cases.
   - Against: storage cost (minimal), public URL (mitigable with UUID), model gains 2 columns.
   - Research recommendation: **store** — the cost is marginal and unlocks future features (re-parse, evidence in agentic chat).

2. **Real dry-run or just client-side preview?**
   - The ingestor **does not** support dry-run today (status enum allows it but code never uses it). Implementing requires: run the full flow without commit, return fictitious `IngestReport`, do `db.rollback()` at the end. Effort ~30 LOC in service.
   - MVP alternative: skip dry-run, show step 2 with parsed data and match immediately on confirm.
   - Recommendation: **implement server-side dry-run** — the wizard becomes much safer and the pattern is reused for troubleshooting.

3. **Wizard 1 endpoint or 3 endpoints?**
   - 3 endpoints (step 1 = `POST /imports/parse` returns parsed JSON + detected event header, step 2 = `POST /imports/dry-run` with meta+decisions returns IngestReport, step 3 = `POST /imports/commit` with same body executes) → better UX, requires persisting parsed between steps (in client state or in `RaceImport.status=pending` temporarily).
   - 1 mega-endpoint (`POST /imports` with everything) → simpler, worse UX (re-parses on each step if coach edits).
   - Recommendation: **3 endpoints** — the pdfplumber parse latency (2-5s) makes repeating it impractical.

4. **"Force re-ingestion" for sha duplicate?**
   - Current behavior is safe (abort). UI needs decision: hide option or show it only to admins?
   - Recommendation: show as warning, not as primary button; require checkbox "I know this will duplicate records if it was an error".

5. **Creating `RaceCompetitor` non-TyR without athlete_id is OK?**
   - Today the ingestor always does it (`ingestor.py:284-296`). UI doesn't need to ask anything for non-TyR. Just confirm it's OK with the coach.

6. **Support CSV in UI MVP?**
   - The service already supports autodispatch by extension (`scripts/ingest_race.py:247-251`). Adding it to the endpoint costs nothing. But most PDFs will be Federation PDFs.
   - Recommendation: **yes include** — marginal effort, covers Sevilla V-I 2026 case.

7. **Allow editing PDF metadata after commit?**
   - The `RaceEvent` upsert already allows it — re-uploading the same PDF with updated meta reflects it. Do we need a dedicated "edit weather" endpoint without re-uploading?
   - Defer to F2; not MVP.

8. **Wizard position: dedicated tab or global modal?**
   - Research recommendation: **dedicated tab** "Load results". Maintains state while navigating.

9. **Polling or synchronous for commit?**
   - The ingestor is synchronous (<2s for 227 riders locally). In Render free tier with cold start it could take longer.
   - Recommendation: **synchronous with 60s timeout**. If it took longer it would be a parser bug, not normal load.

10. **Create new athlete from wizard inline or redirect?**
    - In CLI, "n(ew)" leaves `athlete_id=None` and the coach creates the athlete afterwards (`riders link` to link). Same pattern in UI: option "Pending — create athlete afterwards" + link to athletes CRUD.
    - Recommendation: **defer creation** (not inline).

---

## Final research recommendation

**Suggested approach**: implement the upload as a **3-step wizard in a new "Load results" tab** inside `RaceAnalysisPage.tsx`, backed by **3 REST endpoints** under `/api/race-analysis/imports/*` that wrap the existing F1.7 deterministic pipeline without touching it. The deterministic service layer (`RaceIngestor`, `pdf_parser`, `matcher`, `normalizer`) is **self-sufficient and well-tested (305 tests, 98% coverage)** — it only needs an HTTP wrapper, multipart upload handling with magic bytes / size cap (patterns already validated in `route-file` and `media`), transient PDF persistence in `storage_sftp` with UUID in path, and two small gaps to fill: (a) **implement real dry-run** in `RaceIngestor` (~30 LOC) so wizard step 2 can show a preview without writing, (b) **extend `RaceImport`** with `event_id`, `kind`, `storage_path`, `storage_url` for complete traceability.

**Risks to watch**: (1) `pdf_parser.parse_results_pdf` only accepts `Path` not `BinaryIO` — requires `tempfile` or a refactor (decide in design); (2) `HOSTINGER_SFTP_*` envs are still pending in Render per F1.6 step 9 — without those envs the storage falls back to local that gets wiped on redeploy, **silent operational blocker**; (3) the pattern "coach interactively confirms top-3 matches" translates poorly to UI without careful visual design of the matches table — investing here prevents the coach from abandoning the wizard. The great advantage of this path is that it **does not touch the proven business logic** — everything new is HTTP + UI + 2 trivial migrations.
