# Feature Specification: Translate Claude/AI Instruction & Documentation Files to English

**Feature Branch**: `001-translate-claude-files-english`

**Created**: 2026-06-05

**Status**: Draft

**Input**: User description: "Convert to english each claude files, from @CLAUDE.md , .claude folder, agents instructions, etc Because the better prompt engineer is in English than Spanish"

## Clarifications

### Session 2026-06-05

- Q: How should the output-language directives be handled when translating the instruction files to English? → A: Translate everything to English — input and output. Directives that currently say "respond in Spanish" become "respond in English," and the assistant should operate (reason and reply to the developer) in English. *(Note: this overrides the existing "Idioma: responder siempre en español" directive in CLAUDE.md. It governs only the AI development assistant's working language and these instruction/doc files — it does NOT change the production end-user product copy that lives in backend Jinja templates and frontend source, which remains Spanish per Constitution Principle III and is out of scope here.)*
- Q: Which files are in scope for the translation? → A: CLAUDE.md + all `.claude/agents/*.md` + all `docs/**/*.md`.
- Q: How to resolve the conflict between the new English directive and the constitution (Principle III) + CLAUDE.md "Idioma" rule that mandate Spanish? → A: Amend both — update constitution Principle III and rewrite the CLAUDE.md "Idioma/Language" section to codify a single coherent policy: AI dev-assistant working language = English; product end-user copy (emails/PDF/UI in code) = Spanish. This pulls `.specify/memory/constitution.md` into scope (Principle III only) so no contradiction remains after translation. **Process note**: the Principle III change MUST be executed as a standalone constitution update (via `/speckit-constitution`) sequenced before implementation, not folded into the feature's translation commits.
- Q: Who/what performs the semantic-fidelity verification (SC-005)? → A: AI self-verifies every file; the bilingual user spot-checks the P1/P2 sample (CLAUDE.md + agents) before merge. Definition of Done = automated gates green + user sign-off (Option A).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Central runtime guidance reads natively in English (Priority: P1)

As the developer working with Claude Code on this project, I open `CLAUDE.md` and find the entire runtime guidance — identity, stack, data model, implementation status, non-negotiable principles, age-group differentiation, and the session format — written in clear, natural English, so that the AI assistant reasons over higher-quality English prompts and I can maintain a single authoritative guidance file in one language.

**Why this priority**: `CLAUDE.md` is the single most-loaded context file; it is injected into every session and steers all assistant behavior. Translating it delivers the largest prompt-engineering benefit per line and is independently valuable even if nothing else is touched.

**Independent Test**: Open the translated `CLAUDE.md`, confirm there is no remaining Spanish prose, confirm every section from the original is present and semantically equivalent, and confirm all structural/technical tokens (table layouts, code blocks, file paths, identifiers, env-var names, calendar data, dates) are unchanged. Start a fresh Claude Code session and confirm the assistant operates correctly using the English guidance.

**Acceptance Scenarios**:

1. **Given** the original Spanish `CLAUDE.md`, **When** the translation is applied, **Then** every heading, table, list item, and note appears in English with the same meaning and the same document structure/order.
2. **Given** the "Idioma / Language" directive, **When** translated, **Then** it instructs the assistant to operate and respond in English (replacing the prior "responder siempre en español" instruction).
3. **Given** code blocks, file paths, table schemas, environment variable names, command snippets, URLs, dates, and the Copa Valle calendar, **When** the file is translated, **Then** those tokens are preserved verbatim (only their surrounding descriptive prose is translated).
4. **Given** domain terms with established English equivalents (e.g., "Pico de Velocidad de Crecimiento (PHV)"), **When** translated, **Then** the term is rendered in English with the acronym preserved ("Peak Height Velocity (PHV)").

---

### User Story 2 - All agent instruction files operate in English (Priority: P2)

As the developer relying on the project's specialized subagents, I want each of the 28 agent definition files in `.claude/agents/` translated to English — both the YAML frontmatter `description` and the full instruction body — so that every agent's system prompt is in English and the agents reason and respond in English while preserving their identity, responsibilities, constraints, and output formats.

**Why this priority**: The agents are the working fleet; their prompts directly drive task quality. They depend on `CLAUDE.md` conventions (P1), so they translate cleanly after the central guidance is settled, but each agent is independently valuable.

**Independent Test**: For each agent file, confirm the body prose is English, the `name` and `model`/`memory` frontmatter keys are unchanged, the `description` is translated, all referenced file paths/identifiers/agent names are preserved, and the agent's required output format/structure is intact (translated labels where they are prose, preserved where they are literal tokens the system depends on).

**Acceptance Scenarios**:

1. **Given** an agent file's YAML frontmatter, **When** translated, **Then** the `name` value and all non-prose keys remain byte-identical and only the `description` free-text is translated to English.
2. **Given** an agent body that cross-references other agents by slug (e.g., `head-coach-lead`, `data-privacy-guard`), file paths (e.g., `docs/01-marco-teorico.md`), or code identifiers, **When** translated, **Then** every such reference is preserved exactly.
3. **Given** an agent that defines a mandatory output format containing emoji/section labels (e.g., the 🚴 session format), **When** translated, **Then** the descriptive labels are rendered in English and the structural markers/emoji are preserved.
4. **Given** all 28 agent files, **When** the translation is complete, **Then** no agent body or description contains residual Spanish prose.

---

### User Story 3 - Reference documentation reads in English (Priority: P3)

As a contributor reading the project's technical and training documentation, I want the 34 markdown files under `docs/` translated to English, preserving all diagrams, code blocks, tables, and cross-references, so that the entire knowledge base is consistent with the English-first direction.

**Why this priority**: `docs/` is large (~15k lines), human-facing reference material rather than live AI prompt scaffolding, so it has the lowest per-line impact on assistant behavior and is best done last. It is still independently valuable as a consistency and onboarding improvement.

**Independent Test**: Walk the `docs/` tree, confirm each `.md` file's prose is English with structure preserved, confirm binary and fixture files are untouched, and confirm intra-doc links and links from `CLAUDE.md`/agents still resolve (filenames unchanged).

**Acceptance Scenarios**:

1. **Given** the 34 markdown files in `docs/`, **When** translated, **Then** each file's narrative prose is English and its headings/tables/code/diagrams retain identical structure and content.
2. **Given** binary or fixture assets in `docs/` (`.docx`, `.pdf`, `.yml` snapshot fixtures, images), **When** the feature is executed, **Then** those files are left unmodified.
3. **Given** internal links between docs and references to docs from `CLAUDE.md` and agent files, **When** translation is complete, **Then** all links still resolve because filenames and anchors used as targets are preserved.

---

### Edge Cases

- **Mixed-language strings**: A line that already contains English technical terms inside Spanish prose (e.g., "Schemas Pydantic con `consent_ack` obligatorio") must become fully natural English without altering the embedded code identifiers (`consent_ack`).
- **Literal vs. descriptive tokens**: Some Spanish-looking strings are literal values the running system depends on — e.g., enum stored values `Pre-PHV`/`Circa-PHV`/`Post-PHV`, the Python attribute note `relationship_type` (alias of column `relationship`), seed emails like `entrenador@trochyruta.com`, and template names like `training_session_invite`. These MUST NOT be translated.
- **Accented identifiers**: File paths, command names, and code identifiers never carry accents; only prose does. Translation must not strip or add diacritics to non-prose tokens.
- **Implementation-status tables with dates**: Status entries like "✅ Completo 2026-05-19" must translate the status word ("✅ Complete 2026-05-19") while preserving the date and emoji.
- **Calendar and domain data**: The Copa Valle 2026 calendar (months in Spanish abbreviations, venue names like Sevilla, Ginebra) — venue proper nouns stay; descriptive labels ("Completada" → "Completed") translate.
- **Idempotency**: Re-running the translation on an already-translated file must produce no further changes (no double-translation, no drift).
- **Frontmatter integrity**: A malformed YAML frontmatter after translation (e.g., an unescaped quote introduced into `description`) would break agent loading and must be prevented.
- **Spanish kept by design**: Strings the user explicitly chose to keep Spanish (production end-user copy referenced from code, proper nouns, local circuit names) must not be "corrected" into English.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST translate the full prose content of `CLAUDE.md` from Spanish to natural, idiomatic English while preserving the document's section order, heading hierarchy, tables, and code blocks.
- **FR-002**: The system MUST translate the YAML frontmatter `description` field and the entire instruction body of all 28 files in `.claude/agents/*.md` to English.
- **FR-003**: The system MUST translate the prose of all 34 markdown files under `docs/**/*.md` to English.
- **FR-004**: The system MUST preserve, byte-for-byte, all non-prose tokens: file paths, directory names, code identifiers, function/class/variable names, environment variable names and example values, command-line snippets, URLs, email addresses, enum stored values, template names, dates, numeric values, and Markdown/YAML structural syntax.
- **FR-005**: The system MUST translate output-language directives so that the AI assistant and agents are instructed to operate and respond in English (replacing prior "respond in Spanish" instructions), per the clarified scope.
- **FR-005a**: The system MUST amend `.specify/memory/constitution.md` (Principle III, "User Experience Consistency") and rewrite the `CLAUDE.md` "Idioma/Language" section so both express one coherent, non-contradictory language policy: **AI dev-assistant working language = English; product end-user copy (backend email/PDF templates, frontend UI strings) = Spanish (Colombia)**. The constitution amendment MUST follow its own governance procedure (bump version, update the Sync Impact Report comment).
- **FR-006**: The system MUST preserve all cross-references intact — agent-to-agent slug references, document links, and code-symbol references — so that no link or reference breaks as a result of translation (filenames and anchors used as link targets MUST remain unchanged).
- **FR-007**: The system MUST preserve mandatory output-format templates' structure (e.g., the 🚴 session format, report block layouts), translating only the human-readable label prose and leaving emoji and structural markers in place.
- **FR-008**: The system MUST leave out-of-scope files unmodified: `.claude/skills/**` (third-party tooling, already English), `.claude/settings.json`, and all binary/fixture assets (`.docx`, `.pdf`, `.yml` snapshots, images). `.specify/**` is out of scope **except** `.specify/memory/constitution.md`, which is amended per FR-005a.
- **FR-009**: The system MUST keep translated files valid: Markdown renders correctly and YAML frontmatter parses correctly (agent files still load).
- **FR-010**: The system MUST render established Spanish→English domain term mappings consistently across all files (a glossary), preserving parenthetical acronyms (e.g., PHV, LTAD, RPE, RBAC).
- **FR-011**: The translation MUST be idempotent — applying it to already-translated content yields no further changes.
- **FR-012**: The system MUST NOT alter the meaning, intent, constraints, or any non-negotiable principle expressed in the source files; translation is semantically faithful, not a rewrite.
- **FR-013**: The system MUST NOT translate or "correct" strings that are deliberately kept Spanish per the user's decision (production end-user copy referenced from code, proper nouns, local place/circuit names used as identifiers).

### Key Entities *(include if feature involves data)*

- **Translatable file**: A UTF-8 Markdown file in scope (`CLAUDE.md`, an agent definition, or a `docs/` page). Attributes: path, original-language prose segments, preserved-token segments, frontmatter (if any).
- **Preserved token**: A substring that must survive translation unchanged — code identifier, path, URL, env var, enum value, date, template name, or structural markup.
- **Glossary entry**: A canonical Spanish→English mapping for a recurring domain term (e.g., "entrenador" → "coach", "atleta" → "athlete", "asistencia" → "attendance", "sesión de entrenamiento" → "training session"), used to keep terminology consistent across all files.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the 63 translation files (1 `CLAUDE.md` + 28 agent files + 34 `docs/` markdown files) are translated — plus the 1 governed constitution amendment (counted separately) — with zero in-scope files left containing untranslated Spanish prose.
- **SC-002**: Zero out-of-scope files are modified (skills, `.specify`, settings, and all binary/fixture assets remain byte-identical).
- **SC-003**: 100% of preserved tokens (paths, identifiers, env vars, URLs, enum values, dates, template names) remain byte-identical between source and translation, verified by token diff.
- **SC-004**: All 28 agent files load successfully (valid YAML frontmatter) after translation, and all referenced agent slugs/paths still resolve — 0 broken references.
- **SC-005**: A reviewer fluent in both languages confirms semantic fidelity on a sample of at least 20% of files, with 0 instances of changed meaning, dropped constraints, or altered non-negotiable principles.
- **SC-006**: Re-running the translation process on the translated output produces 0 additional changes (idempotency verified).
- **SC-007**: Every section present in each original file is present in its translation (no content loss), verified by section/heading count parity.
- **SC-008**: After the change, 0 contradictions remain between the `CLAUDE.md` language directive and the constitution: a cross-read of both confirms the single policy (English dev-assistant working language; Spanish product copy), and the constitution version + Sync Impact Report are updated.

## Assumptions

- **Working language of the AI dev assistant**: Per the clarification, after this change the Claude Code assistant operates and responds to the developer in English. This is intentional and supersedes the prior `CLAUDE.md` "responder siempre en español" directive for the development workflow.
- **Production end-user copy is out of scope**: Spanish copy delivered to coaches and families (backend Jinja email/PDF templates, frontend UI strings) lives in source code, not in these instruction/doc files, and remains Spanish per the amended Constitution Principle III. This feature does not change product-facing output.
- **Scope**: `CLAUDE.md`, `.claude/agents/*.md`, `docs/**/*.md`, **and** an amendment to `.specify/memory/constitution.md` (Principle III only, per FR-005a). The rest of `.specify/**`, `.claude/skills/**`, `.claude/settings.json`, and binary/fixture files are excluded.
- **Filenames are not renamed**: Only file contents are translated; paths stay stable so all existing links and references keep working.
- **Proper nouns stay**: The club name "Club Deportivo Trocha y Ruta", venue names (Sevilla, Ginebra, La Cumbre, Cali, Palmira, Roldanillo, Yumbo), and region names (Valle del Cauca) are preserved.
- **A shared glossary is established first** so terminology (coach, athlete, attendance, training session, anthropometry, parent/guardian, etc.) is consistent across all 63 files.
- **Standard Markdown/YAML tooling** is sufficient to verify rendering and frontmatter validity; no new dependency is required.
- **Git history is the rollback mechanism**: changes land on the feature branch `001-translate-claude-files-english`, reviewable as a diff before merge.
