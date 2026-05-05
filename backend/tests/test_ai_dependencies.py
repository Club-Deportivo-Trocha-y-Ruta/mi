"""Tests de las dependencies de la capa de IA."""

from __future__ import annotations

from app.dependencies import (
    get_llm_provider,
    get_phv_explainer_use_case,
    get_prompt_registry,
)
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.providers.fake import FakeLLMProvider
from app.services.ai.use_cases.phv_explainer import PHVExplainerUseCase


def test_provider_is_singleton():
    # `@lru_cache(maxsize=1)` debe garantizar la misma instancia en cada llamada.
    a = get_llm_provider()
    b = get_llm_provider()
    assert a is b


def test_provider_is_fake_when_disabled():
    """En el .env de tests `AI_ENABLED=false` → factory retorna FakeLLMProvider."""
    p = get_llm_provider()
    assert isinstance(p, FakeLLMProvider)


def test_registry_is_singleton():
    a = get_prompt_registry()
    b = get_prompt_registry()
    assert a is b
    assert isinstance(a, PromptRegistry)


def test_phv_use_case_dependency_resolves():
    provider = get_llm_provider()
    registry = get_prompt_registry()
    uc = get_phv_explainer_use_case(provider=provider, registry=registry)
    assert isinstance(uc, PHVExplainerUseCase)
