"""T031 [US4] — privacy: real athlete name never reaches the provider payload.

The interpretation context is built from scores/bands/baselines only — never
from athlete identity (FR-027, Ley 1581). This asserts the property directly on
the use case (the single path to the provider) and on the cached output.
"""
from __future__ import annotations

import json

import pytest

from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.providers.fake import FakeLLMProvider
from app.services.ai.use_cases.anxiety_interpretation import (
    AnxietyInterpretationUseCase,
)
from tests.anxiety.conftest import VALID_INTERPRETATION

REAL_NAME = "Juan Diego Garcia"


@pytest.mark.asyncio
async def test_real_name_never_in_provider_payload():
    provider = FakeLLMProvider(canned=json.dumps(VALID_INTERPRETATION))
    use_case = AnxietyInterpretationUseCase(provider, PromptRegistry())

    out = await use_case.run(
        instrument_type="csai2r",
        scores={"cognitive": 30.0, "somatic": 25.0, "selfconfidence": 28.0},
        baselines={"cognitive": 20.0, "somatic": 20.0, "selfconfidence": 30.0},
        age_group="13-15",
        event_label="Válida IV Cali",
        priority="A",
    )

    # The payload sent to the provider must not contain the athlete's name.
    sent = provider.last_request
    haystack = sent.system + " ".join(m.content for m in sent.messages)
    assert REAL_NAME not in haystack
    assert REAL_NAME.split()[0] not in haystack

    # Nor in the produced interpretation.
    blob = json.dumps(out["interpretation"], ensure_ascii=False)
    assert REAL_NAME not in blob
