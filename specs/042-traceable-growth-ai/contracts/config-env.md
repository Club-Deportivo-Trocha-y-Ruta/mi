# Contract — new/changed `Settings`, validators, env matrix

**Module**: `backend/app/config.py` (existing file, extended — W1).
**Related contracts**: `llm-transport.md` (how `AI_USE_LANGCHAIN`/`AI_ANALYST_MODEL`/
`AI_CRITIC_MODEL` are consumed), `trace-metadata-allowlist.md` §1 (how
`LANGFUSE_STRUCTURAL_METADATA` gates the mask).
**Requirements covered**: FR-020, FR-021, FR-025, FR-037.

---

## 0. The one-way inheritance rule — restated, not changed

`app/services/ai/` (including the new `app/services/ai/anthro/` pipeline) may read `AI_*`
variables only, never `RACE_AI_*`. `app/services/race/` may read `RACE_AI_*` and, only when a
`RACE_AI_*` variable is empty, inherit the matching `AI_*` value. This feature adds new `AI_*`
variables to the app-stack side and touches zero `RACE_AI_*` defaults or fallback chains. The
anthropometry pipeline's own per-role model resolution (`AI_ANALYST_MODEL`/`AI_CRITIC_MODEL`)
lives in the `AI_*` namespace precisely so this rule needs no exception (`config.py:353-376` is
the existing enforcement point and gains no new `race_ai_*` field).

## 1. New / changed `Settings` fields

```python
class Settings(BaseSettings):
    # ... existing fields unchanged ...

    # -------------------------------------------------------------------
    # AI transport migration (feature 042)
    # -------------------------------------------------------------------
    # True (default) routes the five bridged use cases (session assistant
    # clarify/draft, monthly report, monthly report blocks, newsletter v2)
    # through the new LangChainProvider adapter. False routes them through
    # the legacy hand-rolled SDK providers unchanged — rollback switch for
    # the migration window, not a long-lived feature flag. Does NOT affect
    # the anthropometry pipeline, which never used the legacy providers to
    # begin with (it calls the shared factory directly — llm-transport.md §3).
    ai_use_langchain: bool = True

    # Per-role model overrides for the anthropometry pipeline (llm-transport.md
    # §3). Empty string falls back to AI_MODEL — a fresh checkout needs zero
    # new required configuration. Deliberately NOT reusing RACE_AI_ANALYST_MODEL/
    # RACE_AI_CRITIC_MODEL (§0) — same reasoning CLAUDE.md already documents for
    # why RACE_AI_* inherits AI_* and not the reverse.
    ai_analyst_model: str = ""
    ai_critic_model: str = ""

    # Prompt version for the anthropometry analyst/critic pair — mirrors
    # RACE_AI_PROMPT_VERSION's rollback purpose (change this, not a deploy,
    # to fall back to a previous prompt if a new one regresses).
    ai_anthro_prompt_version: str = "anthropometry_analyst_v1"

    # -------------------------------------------------------------------
    # Langfuse structural metadata (feature 042) — trace-metadata-allowlist.md
    # -------------------------------------------------------------------
    # False (default) preserves today's redact-always behaviour byte for
    # byte. True additionally sends the audited operational-only allow-list
    # (trace-metadata-allowlist.md §2) as trace metadata. FORBIDDEN in
    # production regardless of LANGFUSE_ENABLED's own value — belt and
    # suspenders, in case a future refactor decouples the two flags.
    langfuse_structural_metadata: bool = False

    # -------------------------------------------------------------------
    # Bug fix bundled with the factory extraction (llm-transport.md §4):
    # `_build_google_llm`/`_build_openai_llm` in the pre-042 `race/agents/
    # _llm.py` fall back to `settings.ai_temperature` (the APP stack's own
    # setting) even when serving the RACE stack — there was no race-owned
    # temperature knob at all. Default matches `ai_temperature`'s default,
    # so any deployment relying on defaults sees no behaviour change; a
    # deployment that had customised AI_TEMPERATURE was silently leaking
    # that customisation into race and now must set this explicitly too.
    # Empty is not a legal state here (unlike RACE_AI_PROVIDER) — this is a
    # float, not a string, so "inherits AI_TEMPERATURE" is expressed as
    # "equal to its default", not as an empty-string sentinel.
    race_ai_temperature: float = 0.4
```

## 2. New validators

```python
@field_validator("langfuse_structural_metadata")
@classmethod
def forbid_langfuse_structural_metadata_in_prod(cls, v: bool, info) -> bool:
    env = info.data.get("app_env", "development")
    if env == "production" and v:
        raise ValueError(
            "LANGFUSE_STRUCTURAL_METADATA=true PROHIBIDO en producción "
            "(privacidad de menores)."
        )
    return v


@field_validator("ai_anthro_prompt_version")
@classmethod
def validate_ai_anthro_prompt_version(cls, v: str, info) -> str:
    allowed = {"anthropometry_analyst_v1"}   # grows by one entry per shipped prompt revision
    normalized = v.lower().strip()
    if normalized not in allowed:
        raise ValueError(
            f"AI_ANTHRO_PROMPT_VERSION='{v}' inválido. Permitidos: {sorted(allowed)}."
        )
    return normalized


@model_validator(mode="after")
def _forbid_claude_cli_in_prod(self) -> "Settings":
    """FR-037 — closes a gap the audit found: nothing enforced claude-cli's
    local-only status today, only convention plus the package's absence
    from requirements.txt. Covers BOTH stacks: a bare AI_PROVIDER=claude-cli
    (app stack) and the effective race provider after the AI_PROVIDER
    inheritance (empty RACE_AI_PROVIDER falls back to AI_PROVIDER, so the
    check must resolve the fallback, not just read the raw field)."""
    if self.app_env != "production":
        return self
    effective_race_provider = self.race_ai_provider or self.ai_provider
    if self.ai_provider == "claude-cli" or effective_race_provider == "claude-cli":
        raise ValueError(
            "AI_PROVIDER='claude-cli' PROHIBIDO en producción para cualquiera de los "
            "dos stacks (suscripción personal del desarrollador; los términos de "
            "consumo de Anthropic no permiten usarlo para servir a usuarios finales)."
        )
    return self
```

This validator is added to the existing `_forbid_default_jwt_secret_in_prod` model-validator
block (`config.py:442-467`) or as a sibling `@model_validator(mode="after")` — either placement is
equivalent since Pydantic v2 runs all `after` validators in declaration order after every
`field_validator` has already normalised `ai_provider`/`race_ai_provider` to lower-case.

## 3. Bundled hygiene items touching this file (LD-13, not new fields)

- `Settings.ai_provider`'s existing `validate_ai_provider` validator (`config.py:353-362`) and
  `race_ai_provider`'s `validate_race_ai_provider` (`config.py:364-376`) are **unchanged** — both
  already accept `"claude-cli"` as a legal *value*; §2's new validator is what makes it illegal
  *in production specifically*, layered on top, not a replacement.
- `tests/test_ai_factory.py::test_factory_openai_not_implemented` (red on `main`, per
  `architecture.md` §1.5) is fixed in the same wave that touches `app/services/ai/factory.py` —
  full detail in `llm-transport.md` §5, not restated here since it is a factory-module fix, not a
  `Settings` change.
- CLAUDE.md's Alembic-head line moves `2a8baa967cc6` → `45cd705c6b54` → this feature's own new
  revision id, in the W4 docs wave (`data-model.md` §5).

## 4. Env matrix — representative scenarios

All four scenarios show only the variables relevant to provider/model resolution; every other
`Settings` field keeps its documented default.

| Scenario | `AI_PROVIDER` | `AI_MODEL` | `AI_ANALYST_MODEL` | `AI_CRITIC_MODEL` | `AI_USE_LANGCHAIN` | `RACE_AI_PROVIDER` | Effective anthro analyst model | Effective bridged-use-case provider |
|---|---|---|---|---|---|---|---|---|
| **Fresh checkout** (documented default) | `google` | `gemini-3.1-flash-lite` | *(empty)* | *(empty)* | `true` | *(empty → inherits `google`)* | `gemini-3.1-flash-lite` (falls back to `AI_MODEL`, no per-role override set) | LangChain adapter, `google` |
| **Local `claude-cli`** (developer's own subscription, app stack only) | `claude-cli` | `claude-sonnet-5` | *(empty)* | *(empty)* | `true` | *(empty → inherits `claude-cli`, only if the developer also wants race on it — usually left `google` explicitly instead to decouple)* | `claude-sonnet-5` via the CLI (lazy import; `ChatClaudeCli` ignores `temperature`/`max_output_tokens`) | LangChain adapter still applies — `AI_USE_LANGCHAIN` does not special-case `claude-cli`; the adapter dispatches to the same lazy-imported `ChatClaudeCli` builder either way |
| **Anthropic** (no temperature forwarded) | `anthropic` | `claude-sonnet-5` | *(empty)* | *(empty)* | `true` | *(empty)* | `claude-sonnet-5`; `ProviderConfig.temperature` never reaches `ChatAnthropic(...)` — hard rule, `llm-transport.md` §4 | Adapter's `ChatAnthropic` builder, same omission |
| **Ollama** (OpenAI dialect via `base_url`) | `openai` | `qwen3.5:latest` | *(empty)* | *(empty)* | `true` | *(empty)* | `qwen3.5:latest`, `AI_BASE_URL=http://host.docker.internal:11434/v1`, dummy `AI_API_KEY` | Adapter's `ChatOpenAI` builder, `base_url` forwarded |
| **Anthro on a stronger model than the rest of the stack** | `google` | `gemini-3.1-flash-lite` | `gemini-3.8-flash` | *(empty → falls back to `AI_MODEL`)* | `true` | *(empty)* | Analyst: `gemini-3.8-flash`; Critic: `gemini-3.1-flash-lite` | Unaffected — bridged use cases still resolve `AI_MODEL`, per-role overrides are anthro-specific |

`RACE_AI_*` never appears as an input to any cell above with a non-empty, non-inherited value in
this table — every scenario that needs the race stack on a *different* provider than the app stack
sets `RACE_AI_PROVIDER` explicitly, decoupling the two, exactly as CLAUDE.md already documents for
the pre-042 stack. This feature adds no new coupling in either direction.

## 5. `.env.example` additions (names only, per repo convention — never values)

```text
# --- AI transport migration (feature 042) ---
AI_USE_LANGCHAIN=
AI_ANALYST_MODEL=
AI_CRITIC_MODEL=
AI_ANTHRO_PROMPT_VERSION=

# --- Langfuse structural metadata (feature 042, local-only, prod-forbidden) ---
LANGFUSE_STRUCTURAL_METADATA=
```

## 6. Tests

- `test_langfuse_structural_metadata_forbidden_in_production` — `APP_ENV=production` +
  `LANGFUSE_STRUCTURAL_METADATA=true` raises at `Settings()` construction.
- `test_claude_cli_forbidden_in_production_both_stacks` — four cases: `AI_PROVIDER=claude-cli`
  alone; `RACE_AI_PROVIDER=claude-cli` alone; both; and the inherited case
  (`RACE_AI_PROVIDER=""`, `AI_PROVIDER=claude-cli"`) — all four raise under
  `APP_ENV=production`; none raise under `APP_ENV=development`.
- `test_ai_anthro_prompt_version_validator` — an unknown value raises; the documented default
  passes.
- `test_ai_analyst_critic_model_fallback_to_ai_model` — both empty → both resolve to `AI_MODEL`
  (exercised through `llm-transport.md`'s `resolve_app_config`, not re-tested at the `Settings`
  level beyond "the field exists and defaults to empty string").
- Regression: `test_provider_inheritance_matrix` (already required by `llm-transport.md` §5) is
  parametrised to include `claude-cli` among the providers it walks, so the production-forbidden
  validator and the inheritance resolver are exercised together, not just each in isolation.
- `test_race_temperature_no_longer_reads_ai_temperature` — set `AI_TEMPERATURE` to a
  non-default value and leave `RACE_AI_TEMPERATURE` at its default; assert
  `resolve_race_config()` resolves `race_ai_temperature`'s own default, never the app's value
  (the regression guard for the bug fix above).
