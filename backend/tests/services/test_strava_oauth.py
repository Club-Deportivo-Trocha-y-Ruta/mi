"""Tests T022 — ``services/strava/oauth.py`` (feature 025).

Cubre (spec §T022):
  - Firma/verificación de ``state`` (round-trip, firma inválida, tipo de
    token incorrecto, expiración) — protege el callback OAuth contra CSRF
    y replay (data-model.md §1).
  - ``build_authorize_url``: forma de la URL, scope fijo
    ``activity:read_all`` (research.md §4 — nunca ``activity:read``, que
    silenciosamente perdería la mayoría de las salidas).
  - ``exchange_code``/``refresh_access_token``: éxito (dict crudo de
    Strava) y error (status >=400, fallo de red) vía ``httpx`` mockeado —
    sin llamadas de red reales.
  - Rotación de refresh token: Strava rota el refresh token en cada uso;
    ``refresh_access_token`` debe devolver el valor NUEVO tal cual lo
    entregó Strava (el caller, ``services/strava/client.py``, es quien
    debe persistirlo — ver hallazgo de bug abajo).
  - Privacidad (Ley 1581 FR-016): ``code``/tokens NUNCA aparecen en logs,
    ni siquiera cuando Strava rechaza la solicitud.

Patrón httpx mockeado: se parchea ``httpx.AsyncClient`` (la referencia que
usa ``oauth.py`` internamente) por una clase falsa mínima que reproduce el
protocolo async-context-manager + ``.post()`` usado por
``_post_token_request``, devolviendo una ``httpx.Response`` real (para que
``.status_code``/``.json()`` se comporten igual que en producción) o
lanzando una excepción de transporte. No se usa ningún transporte HTTP
real ni ``respx`` (no es una dependencia del repo).

BUG ENCONTRADO (ver ``test_strava_client_refresh_rotates_tokens_end_to_end``
en ``test_strava_ingest.py``): ``refresh_access_token`` devuelve un
``dict`` (documentado explícitamente en su docstring), pero
``services/strava/client.py::_ensure_fresh_access_token`` accede al
resultado como si fuera un objeto (``result.access_token``,
``result.refresh_token``, ``result.expires_at``) — atributo, no clave de
dict. Esto revienta con ``AttributeError`` sin envolver (no
``StravaOAuthError``/``StravaAuthError``) en CADA refresh real de token,
lo cual ocurre cada ~6 horas para cualquier atleta conectado. Ver el test
xfail dedicado para la reproducción mínima.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest

from app.config import settings
from app.services.strava import oauth

# NOTE: no module-level ``pytestmark = pytest.mark.asyncio`` — pytest.ini
# sets ``asyncio_mode = "auto"`` repo-wide, so async defs are already
# auto-detected; adding the marker explicitly only triggers a PytestWarning
# on the (intentionally) synchronous unit tests in this file.


# ---------------------------------------------------------------------------
# httpx mocking helpers
# ---------------------------------------------------------------------------


def _make_fake_async_client(*, response: httpx.Response | None = None, exc: Exception | None = None):
    """Build a fake ``httpx.AsyncClient`` replacement for ``oauth.py``.

    Accepts arbitrary constructor kwargs (``oauth.py`` only passes
    ``timeout``) and reproduces the async-context-manager + ``post()``
    surface ``_post_token_request`` uses. Returns ``response`` verbatim, or
    raises ``exc`` to simulate a transport failure (``httpx.HTTPError``
    subclass).
    """

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, *exc_info: object) -> None:
            return None

        async def post(self, url: str, data: dict | None = None, **kwargs: object) -> httpx.Response:
            if exc is not None:
                raise exc
            assert response is not None
            return response

    return _FakeAsyncClient


def _json_response(status_code: int, payload: dict) -> httpx.Response:
    request = httpx.Request("POST", "https://www.strava.com/oauth/token")
    return httpx.Response(status_code, json=payload, request=request)


# ---------------------------------------------------------------------------
# state: sign/verify round-trip + failure modes
# ---------------------------------------------------------------------------


class TestSignVerifyState:
    def test_round_trip_returns_original_ids(self) -> None:
        state = oauth.sign_state(athlete_id=42, user_id=7)
        claims = oauth.verify_state(state)
        assert claims == {"athlete_id": 42, "user_id": 7}

    def test_garbage_token_raises_invalid_state(self) -> None:
        with pytest.raises(oauth.InvalidStateError):
            oauth.verify_state("not-a-valid-jwt-at-all")

    def test_wrong_signing_key_raises_invalid_state(self) -> None:
        forged = jwt.encode(
            {
                "athlete_id": 1,
                "user_id": 2,
                "nonce": "x",
                "type": "strava_oauth_state",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            "a-different-secret-not-the-app-one",
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(oauth.InvalidStateError):
            oauth.verify_state(forged)

    def test_expired_token_raises_invalid_state(self) -> None:
        expired = jwt.encode(
            {
                "athlete_id": 1,
                "user_id": 2,
                "nonce": "x",
                "type": "strava_oauth_state",
                "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
            },
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(oauth.InvalidStateError):
            oauth.verify_state(expired)

    def test_wrong_token_type_raises_invalid_state(self) -> None:
        """A token signed with the app's key but the WRONG ``type`` claim
        (e.g. a stray access/refresh JWT) must never be accepted as OAuth
        ``state`` — this is what stops the state channel and the platform's
        own auth channel from being cross-usable."""
        wrong_type = jwt.encode(
            {
                "athlete_id": 1,
                "user_id": 2,
                "nonce": "x",
                "type": "access",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(oauth.InvalidStateError):
            oauth.verify_state(wrong_type)

    def test_missing_athlete_id_raises_invalid_state(self) -> None:
        malformed = jwt.encode(
            {
                "user_id": 2,
                "nonce": "x",
                "type": "strava_oauth_state",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(oauth.InvalidStateError):
            oauth.verify_state(malformed)


# ---------------------------------------------------------------------------
# build_authorize_url
# ---------------------------------------------------------------------------


class TestBuildAuthorizeUrl:
    def test_contains_expected_query_params(self) -> None:
        url = oauth.build_authorize_url(athlete_id=10, user_id=20)
        assert url.startswith(f"{settings.strava_oauth_base_url}/authorize?")
        assert "response_type=code" in url
        assert "scope=activity%3Aread_all" in url  # never bare activity:read
        assert "state=" in url

    def test_state_embedded_in_url_verifies_to_same_ids(self) -> None:
        url = oauth.build_authorize_url(athlete_id=99, user_id=5)
        state_value = url.split("state=", 1)[1].split("&", 1)[0]
        # urlencode escapes '.' as itself but not always symmetric with
        # unquote for JWTs (they only use base64url chars + '.'), so a raw
        # split is safe here — JWTs never contain '&'.
        claims = oauth.verify_state(state_value)
        assert claims == {"athlete_id": 99, "user_id": 5}


# ---------------------------------------------------------------------------
# exchange_code
# ---------------------------------------------------------------------------


class TestExchangeCode:
    async def test_success_returns_raw_strava_token_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        token_payload = {
            "access_token": "AT_INITIAL",
            "refresh_token": "RT_INITIAL",
            "expires_at": 1_800_000_000,
            "expires_in": 21600,
            "token_type": "Bearer",
            "athlete": {"id": 555444},
        }
        monkeypatch.setattr(
            oauth.httpx,
            "AsyncClient",
            _make_fake_async_client(response=_json_response(200, token_payload)),
        )

        result = await oauth.exchange_code("one-time-code")

        assert result == token_payload
        assert result["athlete"]["id"] == 555444

    async def test_rejected_by_strava_raises_oauth_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            oauth.httpx,
            "AsyncClient",
            _make_fake_async_client(response=_json_response(400, {"message": "Bad Request"})),
        )

        with pytest.raises(oauth.StravaOAuthError):
            await oauth.exchange_code("already-used-code")

    async def test_network_failure_raises_oauth_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            oauth.httpx,
            "AsyncClient",
            _make_fake_async_client(exc=httpx.ConnectError("boom")),
        )

        with pytest.raises(oauth.StravaOAuthError):
            await oauth.exchange_code("some-code")

    async def test_never_logs_code_or_token_values(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """FR-016: neither the raw ``code`` nor any resulting token value may
        appear in any log line, including on the failure path."""
        secret_code = "SECRET_CODE_MUST_NOT_LEAK_0xdeadbeef"
        monkeypatch.setattr(
            oauth.httpx,
            "AsyncClient",
            _make_fake_async_client(response=_json_response(400, {"message": "Bad Request"})),
        )
        caplog.set_level(logging.DEBUG)

        with pytest.raises(oauth.StravaOAuthError):
            await oauth.exchange_code(secret_code)

        for record in caplog.records:
            assert secret_code not in record.getMessage()


# ---------------------------------------------------------------------------
# refresh_access_token — rotation contract
# ---------------------------------------------------------------------------


class TestRefreshAccessToken:
    async def test_success_returns_rotated_refresh_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Strava rotates the refresh token on every use — the response's
        ``refresh_token`` is a DIFFERENT value from the one that was sent,
        and callers must treat it as authoritative (module docstring)."""
        rotated_payload = {
            "access_token": "AT_ROTATED_NEW",
            "refresh_token": "RT_ROTATED_NEW",
            "expires_at": 1_900_000_000,
            "expires_in": 21600,
            "token_type": "Bearer",
        }
        monkeypatch.setattr(
            oauth.httpx,
            "AsyncClient",
            _make_fake_async_client(response=_json_response(200, rotated_payload)),
        )

        result = await oauth.refresh_access_token("RT_OLD_VALUE")

        assert result["refresh_token"] == "RT_ROTATED_NEW"
        assert result["refresh_token"] != "RT_OLD_VALUE"
        assert result["access_token"] == "AT_ROTATED_NEW"

    async def test_revoked_refresh_token_raises_oauth_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 401/400 from Strava's token endpoint on refresh (revoked or
        expired refresh token) must surface as ``StravaOAuthError`` — this
        is the signal ``services/strava/client.py`` uses to mark a
        connection ``broken`` (data-model.md §1 state transitions)."""
        monkeypatch.setattr(
            oauth.httpx,
            "AsyncClient",
            _make_fake_async_client(response=_json_response(401, {"message": "Unauthorized"})),
        )

        with pytest.raises(oauth.StravaOAuthError):
            await oauth.refresh_access_token("revoked-refresh-token")

    async def test_never_logs_refresh_token_value(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        secret_refresh_token = "SECRET_REFRESH_TOKEN_0xfeedface"
        monkeypatch.setattr(
            oauth.httpx,
            "AsyncClient",
            _make_fake_async_client(response=_json_response(401, {"message": "Unauthorized"})),
        )
        caplog.set_level(logging.DEBUG)

        with pytest.raises(oauth.StravaOAuthError):
            await oauth.refresh_access_token(secret_refresh_token)

        for record in caplog.records:
            assert secret_refresh_token not in record.getMessage()
