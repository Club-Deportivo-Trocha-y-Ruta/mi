"""Tests del transporte de trazas compartido (feature 042 T022).

Cubre ``app/services/llm/observability.py`` (cliente Langfuse singleton, mask
redact-always, degradación a no-op, session id con clave) y
``app/services/llm/observability_metadata.py`` (allow-list cerrado de
metadata + tipo sentinela ``StructuralMetadata``).

Offline: no se abre ningún cliente Langfuse real — ``_create_client`` se
monkeypatchea para simular éxito/fallo sin red, siguiendo el mismo patrón que
``tests/services/race/test_observability.py``. Los textos de prueba son
sintéticos — ningún dato real de menores.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib
import logging

import pytest

from app.config import settings
from app.services.llm import observability
from app.services.llm.observability import REDACTED
from app.services.llm.observability_metadata import (
    ALLOWED_METADATA_KEYS,
    StructuralMetadata,
    build_mask,
    build_structural_metadata,
)

NAME_SENTINEL = "SENTINELA_NOMBRE_MENOR"


# ---------------------------------------------------------------------------
# 1. Mask redact-always — input/output/metadata sin envolver, en cualquier
#    configuración de LANGFUSE_STRUCTURAL_METADATA (FR-018).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("structural_metadata_flag", [False, True])
def test_mask_none_stays_none_in_every_configuration(monkeypatch, structural_metadata_flag):
    monkeypatch.setattr(settings, "langfuse_structural_metadata", structural_metadata_flag)
    mask = build_mask(REDACTED)

    assert mask(data=None) is None


@pytest.mark.parametrize("structural_metadata_flag", [False, True])
def test_mask_redacts_bare_prompt_and_response_regardless_of_flag(
    monkeypatch, structural_metadata_flag
):
    """No existe ninguna configuración en la que un prompt o una respuesta
    puedan pasar sin redactar (FR-018): ni siquiera con el switch de metadata
    estructural encendido, porque ``input``/``output`` nunca se envuelven en
    ``StructuralMetadata`` — ese tipo existe solo para el canal ``metadata``.
    """
    monkeypatch.setattr(settings, "langfuse_structural_metadata", structural_metadata_flag)
    mask = build_mask(REDACTED)

    assert mask(data=f"Analiza el progreso de {NAME_SENTINEL}") == REDACTED
    assert mask(data=[{"role": "user", "content": NAME_SENTINEL}]) == REDACTED
    assert mask(data={"prompt": NAME_SENTINEL, "model": "gemini-3.8-flash"}) == REDACTED


@pytest.mark.parametrize("structural_metadata_flag", [False, True])
def test_mask_redacts_bare_dict_shaped_like_metadata_regardless_of_flag(
    monkeypatch, structural_metadata_flag
):
    """Un dict pelado -- incluido uno con claves que SÍ están en el
    allow-list -- cae siempre a ``REDACTED`` si no llegó envuelto en
    ``StructuralMetadata``: la decisión de allow-list ocurre al construir el
    objeto, nunca por la forma de los datos (contrato §1, regla 4).
    """
    monkeypatch.setattr(settings, "langfuse_structural_metadata", structural_metadata_flag)
    mask = build_mask(REDACTED)

    auto_populated_by_langchain = {"model": "gemini-3.8-flash", "tokens_in": 11}
    assert mask(data=auto_populated_by_langchain) == REDACTED


def test_mask_passes_through_only_explicit_structural_metadata_fields(monkeypatch):
    monkeypatch.setattr(settings, "langfuse_structural_metadata", True)
    mask = build_mask(REDACTED)

    wrapped = StructuralMetadata(model="gemini-3.8-flash", tokens_in=11)
    assert mask(data=wrapped) == {"model": "gemini-3.8-flash", "tokens_in": 11}


def test_module_mask_instance_matches_build_mask_contract():
    """``observability._mask`` (la instancia real cableada al cliente
    Langfuse) es exactamente lo que produce ``build_mask(REDACTED)`` -- misma
    prueba de humo que ``race/test_observability.py::test_mask_always_redacts_content``
    pero sobre el módulo canónico movido en T011.
    """
    assert observability._mask(data=None) is None
    assert observability._mask(data={"prompt": NAME_SENTINEL}) == REDACTED
    assert observability._mask(data=NAME_SENTINEL) == REDACTED
    assert observability._mask(data=StructuralMetadata(model="google")) == {"model": "google"}


# ---------------------------------------------------------------------------
# 2. Snapshot del allow-list -- si alguien agrega una clave, esta prueba debe
#    fallar y forzarlo a volver a la auditoría de privacidad
#    (contracts/trace-metadata-allowlist.md §0/§2). NO agregues una clave acá
#    solo para que la prueba pase: primero hay que releer ese contrato
#    completo y, si corresponde, actualizar la tabla de la fuente de verdad
#    (privacy.md §2) -- este test existe precisamente para bloquear ese
#    atajo silencioso.
# ---------------------------------------------------------------------------


def test_allowed_metadata_keys_snapshot():
    expected = sorted(
        [
            "athlete_id_hash",
            "record_id_hash",
            "user_id_hash",
            "club_id",
            "delta_height_significant",
            "delta_weight_significant",
            "weeks_since_prev_measurement_bucket",
            "num_previous_measurements_bucket",
            "guardrail_rule_ids",
            "guardrail_scrub_count",
            "precheck_rule_ids",
            "precheck_violation_count",
            "critic_verdict",
            "cache_outcome",
            "use_case",
            "model",
            "provider",
            "prompt_version",
            "role",
            "tokens_in",
            "tokens_out",
            "tokens_total",
            "latency_ms",
            "cost_usd",
        ]
    )

    assert sorted(ALLOWED_METADATA_KEYS) == expected


def test_quasi_identifiers_are_not_on_the_allow_list():
    """Los cuatro cuasi-identificadores del club (§0) nunca deben aparecer en
    el allow-list bajo ningún alias -- ver la regla de combinación §2.1."""
    assert ALLOWED_METADATA_KEYS.isdisjoint({"sex", "age_group", "maturation_status", "category"})


# ---------------------------------------------------------------------------
# 3. build_structural_metadata -- apagado por defecto, y fallo ruidoso (no
#    descarte silencioso) ante una clave fuera del allow-list.
# ---------------------------------------------------------------------------


def test_build_structural_metadata_returns_none_when_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "langfuse_structural_metadata", False)

    assert build_structural_metadata(model="google", tokens_in=11) is None


def test_build_structural_metadata_returns_wrapped_fields_when_flag_on(monkeypatch):
    monkeypatch.setattr(settings, "langfuse_structural_metadata", True)

    result = build_structural_metadata(model="google", tokens_in=11)

    assert isinstance(result, StructuralMetadata)
    assert result.as_dict() == {"model": "google", "tokens_in": 11}


@pytest.mark.parametrize(
    "forbidden_field,forbidden_value",
    [
        ("sex", "F"),
        ("age_decimal", 12.5),
        ("category", "sub15"),
        ("maturation_status", "pre-PHV"),
        ("phv_offset", -0.3),
        ("months_from_phv", -4),
        ("growth_velocity_cm_per_year", 8.2),
        ("delta_height_cm", 1.4),
        ("delta_weight_kg", 0.6),
        ("nutritional_status", "riesgo"),
        ("crossed_phv_phase", True),
        ("training_implications", "aumentar volumen aeróbico"),
        ("session_title", "Salida larga club"),
        ("session_date", "2026-09-01"),
    ],
)
def test_forbidden_fields_are_rejected_not_silently_dropped(
    monkeypatch, caplog, forbidden_field, forbidden_value
):
    """Ninguno de los campos prohibidos de ``trace-metadata-allowlist.md`` §2
    sobrevive al allow-list, y el fallo es ruidoso (``ValueError``), no un
    descarte silencioso: ``StructuralMetadata.__init__`` está deliberadamente
    diseñado para fallar fuerte -- una clave de traza descartada-y-olvidada
    sería una falsa sensación de seguridad sobre qué salió del proceso
    (observability_metadata.py, docstring de ``build_mask``). Además, el
    valor prohibido nunca debe terminar en ningún log emitido durante el
    intento.
    """
    monkeypatch.setattr(settings, "langfuse_structural_metadata", True)

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ValueError, match=forbidden_field):
            build_structural_metadata(**{forbidden_field: forbidden_value})

    for record in caplog.records:
        assert str(forbidden_value) not in record.getMessage()


def test_structural_metadata_constructor_rejects_unknown_key_directly():
    with pytest.raises(ValueError, match="unknown_key"):
        StructuralMetadata(unknown_key="x")


# ---------------------------------------------------------------------------
# 4. keyed_session_id -- estable, no enumerable sin la clave, separado por
#    dominio del anonimizador de pseudónimos de atletas de race.
# ---------------------------------------------------------------------------


def test_keyed_session_id_stable_across_calls(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret_key", "fixed-secret-0123456789abcdef01234567")
    raw = "athlete-42:record-7"

    assert observability.keyed_session_id(raw) == observability.keyed_session_id(raw)


def test_keyed_session_id_stable_across_simulated_process_restart(monkeypatch):
    """``jwt_secret_key`` se lee perezosamente en cada llamada (nunca
    cacheada a nivel de módulo, ver docstring de ``keyed_session_id``) -- no
    hay ningún salt por-proceso escondido que un "reinicio" pudiera
    resetear. Lo probamos recargando el módulo de verdad, no solo llamando
    la función de nuevo, para descartar ese estado oculto.
    """
    monkeypatch.setattr(settings, "jwt_secret_key", "fixed-secret-0123456789abcdef01234567")
    raw = "athlete-42:record-7"
    before_reload = observability.keyed_session_id(raw)

    reloaded = importlib.reload(observability)
    try:
        after_reload = reloaded.keyed_session_id(raw)
    finally:
        # Restaura la identidad de módulo para el resto de la suite: otros
        # módulos (p. ej. el shim de race) importaron los objetos función
        # originales y no deben quedar huérfanos de un reload a mitad de
        # sesión de tests.
        importlib.reload(observability)

    assert before_reload == after_reload


def test_keyed_session_id_differs_for_different_raw_input(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret_key", "fixed-secret-0123456789abcdef01234567")

    assert observability.keyed_session_id("raw-a") != observability.keyed_session_id("raw-b")


def test_keyed_session_id_changes_with_jwt_secret_key(monkeypatch):
    raw = "same-raw-input"
    monkeypatch.setattr(settings, "jwt_secret_key", "secret-one-0123456789abcdef0123456789")
    with_first_key = observability.keyed_session_id(raw)

    monkeypatch.setattr(settings, "jwt_secret_key", "secret-two-abcdef0123456789abcdef0123")
    with_second_key = observability.keyed_session_id(raw)

    assert with_first_key != with_second_key


def test_keyed_session_id_not_equal_to_plain_anonymous_session_id(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret_key", "fixed-secret-0123456789abcdef01234567")
    raw = "chat-session-99"

    assert observability.keyed_session_id(raw) != observability.anonymous_session_id(raw)


def test_keyed_session_id_not_enumerable_without_key_unlike_anonymous_session_id(monkeypatch):
    """Contraste de regresión (FR-024): sobre un espacio de fuerza bruta
    realista para el tamaño del club (~20 atletas x unos cientos de
    registros), ``anonymous_session_id`` SÍ es recuperable por cualquiera
    con el volumen de Langfuse y la base de datos -- por eso
    ``keyed_session_id`` es su reemplazo. Con la clave, ningún hash plano
    (sha256 truncado) sobre esas combinaciones recupera jamás
    ``keyed_session_id``.
    """
    monkeypatch.setattr(settings, "jwt_secret_key", "super-secret-key-value-0123456789abcd")
    raw = "atleta:7:registro:42"

    def brute_force_space():
        return (
            hashlib.sha256(f"atleta:{athlete_id}:registro:{record_id}".encode()).hexdigest()[:16]
            for athlete_id in range(1, 21)
            for record_id in range(1, 501)
        )

    assert observability.keyed_session_id(raw) not in brute_force_space()
    # anonymous_session_id SÍ cae dentro del mismo espacio de fuerza bruta --
    # es exactamente la debilidad documentada que keyed_session_id corrige.
    assert observability.anonymous_session_id(raw) in brute_force_space()


def test_keyed_session_id_domain_separated_from_race_anonymizer():
    """El dominio de separación de ``keyed_session_id``
    (``_KEYED_SESSION_ID_DOMAIN``) es distinto del salt del anonimizador de
    pseudónimos de atletas de race (``race/ai/anonymizer.py``), para que la
    filtración de una derivación no debilite a la otra (docstring del
    módulo, contracts/trace-metadata-allowlist.md §4).
    """
    from app.services.race.ai.anonymizer import _DEFAULT_SALT

    assert observability._KEYED_SESSION_ID_DOMAIN
    assert observability._KEYED_SESSION_ID_DOMAIN != _DEFAULT_SALT.encode("utf-8")

    # Y el dominio realmente participa del cómputo -- no es un valor
    # decorativo sin efecto: usar el salt del anonimizador de race como
    # dominio, con la misma clave y el mismo raw, produce un valor distinto.
    key = settings.jwt_secret_key.encode("utf-8")
    raw = "athlete-1:record-1"
    with_wrong_domain = hmac.new(
        key, _DEFAULT_SALT.encode("utf-8") + b":" + raw.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:16]
    assert observability.keyed_session_id(raw) != with_wrong_domain


# ---------------------------------------------------------------------------
# 5. Degradación a no-op -- tracing nunca rompe una corrida.
# ---------------------------------------------------------------------------


def test_langfuse_disabled_imports_nothing(monkeypatch):
    """Con ``LANGFUSE_ENABLED=false`` no se intenta construir ningún
    cliente -- ``langfuse`` nunca se importa (ver
    ``test_module_never_imports_langfuse_at_top_level`` en la suite de race
    para la prueba estática equivalente sobre el import a nivel de módulo).
    """
    calls: list = []
    monkeypatch.setattr(settings, "langfuse_enabled", False)
    monkeypatch.setattr(observability, "_client", None)
    monkeypatch.setattr(observability, "_create_client", lambda **kw: calls.append(kw))

    assert observability.get_callbacks() == []
    assert observability.trace_id_for("seed-1") is None
    with observability.llm_tracing(trace_name="anthro-analyst", session_id="s-1") as tracing:
        assert tracing == {}
    observability.shutdown()

    assert calls == []


def test_missing_keys_degrades_to_no_op_with_single_warning_across_repeated_calls(
    monkeypatch, caplog
):
    monkeypatch.setattr(settings, "langfuse_enabled", True)
    monkeypatch.setattr(settings, "langfuse_public_key", "")
    monkeypatch.setattr(settings, "langfuse_secret_key", "")
    monkeypatch.setattr(observability, "_client", None)
    monkeypatch.setattr(observability, "_warned_missing_keys", False)
    monkeypatch.setattr(observability, "_create_client", lambda **kw: pytest.fail("no debe llamarse"))

    with caplog.at_level(logging.WARNING, logger="app.services.llm.observability"):
        assert observability.get_callbacks() == []
        assert observability.get_callbacks() == []
        with observability.llm_tracing(trace_name="anthro-analyst", session_id="s-2") as tracing:
            assert tracing == {}

    warnings = [r for r in caplog.records if "LANGFUSE_PUBLIC_KEY" in r.getMessage()]
    assert len(warnings) == 1


def test_client_construction_failure_degrades_to_no_op(monkeypatch):
    """Con ``LANGFUSE_ENABLED=true`` y el cliente fallando al construirse
    (Langfuse inalcanzable), ``get_callbacks`` degrada a ``[]`` y
    ``llm_tracing`` degrada a ``{}`` -- tracing nunca rompe una corrida.
    """
    monkeypatch.setattr(settings, "langfuse_enabled", True)
    monkeypatch.setattr(settings, "langfuse_public_key", "pk-test")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk-test")
    monkeypatch.setattr(observability, "_client", None)

    def _boom(**kwargs):
        raise RuntimeError("langfuse inalcanzable")

    monkeypatch.setattr(observability, "_create_client", _boom)

    assert observability.get_callbacks() == []
    with observability.llm_tracing(trace_name="anthro-analyst", session_id="s-3") as tracing:
        assert tracing == {}


def test_client_construction_failure_warns_exactly_once_per_process(monkeypatch, caplog):
    """FR-021: "como máximo UNA advertencia por proceso", también cuando el
    Langfuse local está caído y ``_create_client()`` lanza.

    Esta prueba nació en rojo: la rama de excepción de ``_get_client``
    llamaba ``logger.exception(...)`` en CADA llamada, sin deduplicar (una
    sola corrida de ``llm_tracing`` ya invoca ``_get_client`` dos veces, así
    que un Langfuse caído inundaba el log). Se corrigió agregando
    ``_warned_construction_failed``, análogo a ``_warned_missing_keys``.
    No debilitar este assert: es la garantía de "sin tormenta de reintentos"
    del edge case de ``spec.md``.
    """
    monkeypatch.setattr(settings, "langfuse_enabled", True)
    monkeypatch.setattr(settings, "langfuse_public_key", "pk-test")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk-test")
    monkeypatch.setattr(observability, "_client", None)

    def _boom(**kwargs):
        raise RuntimeError("langfuse inalcanzable")

    monkeypatch.setattr(observability, "_create_client", _boom)
    # El flag es estado de proceso: otra prueba del archivo que también hace
    # fallar la construcción ya lo habría consumido. monkeypatch lo restaura
    # al salir, así que el aislamiento vale en ambas direcciones.
    monkeypatch.setattr(observability, "_warned_construction_failed", False)

    with caplog.at_level(logging.WARNING, logger="app.services.llm.observability"):
        assert observability.get_callbacks() == []
        assert observability.get_callbacks() == []
        with observability.llm_tracing(trace_name="anthro-analyst", session_id="s-4") as tracing:
            assert tracing == {}

    assert len(caplog.records) == 1


def test_handler_creation_failure_degrades_to_untraced_run(monkeypatch, caplog):
    """Cliente construido con éxito pero el ``CallbackHandler`` falla al
    crearse (contraparte de ``race/test_observability.py``'s
    ``test_handler_creation_failure_degrades_to_untraced_run``, sobre el
    módulo canónico) -- degrada a no-op sin propagar la excepción.
    """
    monkeypatch.setattr(observability, "_client", object())

    def _broken_handler_class():
        raise RuntimeError("handler roto")

    monkeypatch.setattr(observability, "_handler_class", _broken_handler_class)

    with caplog.at_level(logging.ERROR, logger="app.services.llm.observability"):
        assert observability.get_callbacks() == []
