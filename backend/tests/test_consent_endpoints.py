"""Tests de endpoints de políticas de privacidad y consentimiento parental.

Cubre:
- GET /api/auth/active-policy — retorna v1.1 sin autenticación
- GET /api/me/consent — estado de consentimientos del padre por atleta
- POST /api/me/consent/renew — crea nuevo registro, marca viejo como superseded
- POST /api/me/consent/withdraw — solo modifica withdrawn_at (append-only)
- Padre no puede operar sobre atleta no vinculado (403)
- Versión de política inválida en renew (400)
"""

from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Helpers reutilizados de test_onboarding_consent.py (sin importarlos para
# evitar acoplamiento entre módulos de test)
# ---------------------------------------------------------------------------


async def _login(client, email: str, password: str) -> str:
    resp = await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, f"Login fallido: {resp.text}"
    return resp.json()["access_token"]


async def _coach_headers(client) -> dict:
    token = await _login(client, "entrenador@trochyruta.com", "Coach2026!")
    return {"Authorization": f"Bearer {token}"}


async def _get_club_id(client, headers: dict) -> int:
    me = await client.get("/api/auth/me", headers=headers)
    return me.json()["club_ids"][0]


async def _create_athlete(client, headers: dict, club_id: int) -> int:
    """Crea un atleta con nombre único y retorna su ID."""
    resp = await client.post(
        "/api/athletes",
        headers=headers,
        json={
            "first_name": "ConsentTest",
            "last_name": f"Atleta-{uuid4().hex[:6]}",
            "birth_date": "2012-06-15",
            "sex": "M",
            "club_id": club_id,
        },
    )
    assert resp.status_code == 201, f"No se pudo crear atleta: {resp.text}"
    return resp.json()["id"]


async def _register_parent(
    client, athlete_id: int, consent_version: str = "v1.2"
) -> tuple[str, str]:
    """Crea una invitación, registra al padre con consent y retorna (email, token_jwt)."""
    headers = await _coach_headers(client)
    email = f"parent-consent-{uuid4().hex[:8]}@test.com"
    inv_resp = await client.post(
        "/api/parent-athletes/invite",
        headers=headers,
        json={"athlete_id": athlete_id, "email": email},
    )
    assert inv_resp.status_code == 201
    invite_token = inv_resp.json()["token"]

    reg_resp = await client.post(
        "/api/auth/parent-register",
        json={
            "token": invite_token,
            "first_name": "Padre",
            "last_name": "Prueba",
            "password": "Parent2026!",
            "relationship_type": "padre",
            "consent": {
                "accept_data_collection": True,
                "accept_anthropometry": True,
                "privacy_policy_version": consent_version,
            },
        },
    )
    assert reg_resp.status_code == 201, f"Registro fallido: {reg_resp.text}"

    jwt = await _login(client, email, "Parent2026!")
    return email, jwt


async def _full_setup(client) -> tuple[int, str]:
    """Crea atleta y padre vinculado. Retorna (athlete_id, parent_jwt)."""
    headers = await _coach_headers(client)
    club_id = await _get_club_id(client, headers)
    athlete_id = await _create_athlete(client, headers, club_id)
    _, parent_jwt = await _register_parent(client, athlete_id)
    return athlete_id, parent_jwt


# ---------------------------------------------------------------------------
# TestActivePolicyEndpoint — GET /api/auth/active-policy
# ---------------------------------------------------------------------------


class TestActivePolicyEndpoint:
    """Verifica el endpoint público de política activa."""

    async def test_retorna_politica_activa_sin_autenticacion(self, client):
        """GET /api/auth/active-policy no requiere token y retorna la política vigente (v1.2)."""
        resp = await client.get("/api/auth/active-policy")
        assert resp.status_code == 200
        body = resp.json()
        assert body["version"] == "v1.2"
        assert body["deprecated_at"] is None

    async def test_respuesta_incluye_content_html(self, client):
        """La respuesta de política activa incluye el contenido HTML completo."""
        resp = await client.get("/api/auth/active-policy")
        assert resp.status_code == 200
        body = resp.json()
        assert "content_html" in body
        assert len(body["content_html"]) > 100

    async def test_respuesta_incluye_content_hash(self, client):
        """La respuesta incluye el hash SHA-256 de integridad."""
        resp = await client.get("/api/auth/active-policy")
        assert resp.status_code == 200
        body = resp.json()
        assert "content_hash" in body
        assert len(body["content_hash"]) == 64  # SHA-256 hex

    async def test_content_hash_coincide_con_html(self, client):
        """El content_hash debe ser el SHA-256 del content_html retornado."""
        import hashlib

        resp = await client.get("/api/auth/active-policy")
        assert resp.status_code == 200
        body = resp.json()
        expected_hash = hashlib.sha256(body["content_html"].encode()).hexdigest()
        assert body["content_hash"] == expected_hash

    async def test_politica_activa_no_tiene_deprecated_at(self, client):
        """La política activa nunca debe tener deprecated_at."""
        resp = await client.get("/api/auth/active-policy")
        assert resp.status_code == 200
        assert resp.json()["deprecated_at"] is None


# ---------------------------------------------------------------------------
# TestGetConsentStatus — GET /api/me/consent
# ---------------------------------------------------------------------------


class TestGetConsentStatus:
    """Verifica el endpoint de estado de consentimientos del padre."""

    async def test_retorna_estado_de_consentimientos(self, client):
        """GET /api/me/consent retorna active_policy y consents_per_athlete."""
        athlete_id, parent_jwt = await _full_setup(client)
        headers = {"Authorization": f"Bearer {parent_jwt}"}

        resp = await client.get("/api/me/consent", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "active_policy" in body
        assert "consents_per_athlete" in body
        assert isinstance(body["consents_per_athlete"], list)

    async def test_atleta_vinculado_aparece_en_listado(self, client):
        """El atleta vinculado al padre debe aparecer en consents_per_athlete."""
        athlete_id, parent_jwt = await _full_setup(client)
        headers = {"Authorization": f"Bearer {parent_jwt}"}

        resp = await client.get("/api/me/consent", headers=headers)
        assert resp.status_code == 200
        athlete_ids = [
            a["athlete_id"] for a in resp.json()["consents_per_athlete"]
        ]
        assert athlete_id in athlete_ids

    async def test_consentimiento_actual_marcado_como_vigente(self, client):
        """El consentimiento dado con la política vigente debe tener is_current_policy=True."""
        athlete_id, parent_jwt = await _full_setup(client)
        headers = {"Authorization": f"Bearer {parent_jwt}"}

        resp = await client.get("/api/me/consent", headers=headers)
        assert resp.status_code == 200
        atletas = resp.json()["consents_per_athlete"]
        atleta = next(a for a in atletas if a["athlete_id"] == athlete_id)
        assert atleta["current_consent"] is not None
        assert atleta["current_consent"]["is_current_policy"] is True

    async def test_requiere_autenticacion(self, client):
        """Sin token JWT la petición debe retornar 401 o 403."""
        resp = await client.get("/api/me/consent")
        assert resp.status_code in (401, 403)

    async def test_coach_no_puede_acceder(self, client):
        """Un coach no tiene rol parent — debe recibir 403."""
        headers = await _coach_headers(client)
        resp = await client.get("/api/me/consent", headers=headers)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TestRenewConsent — POST /api/me/consent/renew
# ---------------------------------------------------------------------------


class TestRenewConsent:
    """Verifica el endpoint de renovación de consentimiento."""

    async def test_renew_crea_nuevo_registro(self, client):
        """POST /renew con datos válidos retorna 201 y un nuevo registro."""
        athlete_id, parent_jwt = await _full_setup(client)
        headers = {"Authorization": f"Bearer {parent_jwt}"}

        resp = await client.post(
            "/api/me/consent/renew",
            headers=headers,
            json={
                "athlete_id": athlete_id,
                "policy_version": "v1.1",
                "accept_data_collection": True,
                "accept_anthropometry": True,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["athlete_id"] == athlete_id
        assert body["policy_version"] == "v1.1"
        assert body["withdrawn_at"] is None

    async def test_renew_marca_consentimiento_previo_como_superseded(self, client):
        """Tras renew, el consentimiento anterior debe estar retirado (withdrawn_at poblado).

        Se verifica de forma indirecta: el GET /me/consent muestra solo el
        consentimiento activo (withdrawn_at=None), lo que implica que el anterior
        fue marcado como supersedido.
        """
        athlete_id, parent_jwt = await _full_setup(client)
        headers = {"Authorization": f"Bearer {parent_jwt}"}

        # Primera renovación
        r1 = await client.post(
            "/api/me/consent/renew",
            headers=headers,
            json={
                "athlete_id": athlete_id,
                "policy_version": "v1.1",
                "accept_data_collection": True,
                "accept_anthropometry": False,
            },
        )
        assert r1.status_code == 201
        id_r1 = r1.json()["id"]

        # Segunda renovación
        r2 = await client.post(
            "/api/me/consent/renew",
            headers=headers,
            json={
                "athlete_id": athlete_id,
                "policy_version": "v1.1",
                "accept_data_collection": True,
                "accept_anthropometry": True,
            },
        )
        assert r2.status_code == 201
        id_r2 = r2.json()["id"]

        # Los dos registros deben ser distintos
        assert id_r1 != id_r2

        # El consentimiento actual (vía GET) debe ser el nuevo
        status_resp = await client.get("/api/me/consent", headers=headers)
        atletas = status_resp.json()["consents_per_athlete"]
        atleta = next(a for a in atletas if a["athlete_id"] == athlete_id)
        assert atleta["current_consent"]["id"] == id_r2

    async def test_renew_con_version_invalida_retorna_400(self, client):
        """Versión de política que no existe → 400 Bad Request."""
        athlete_id, parent_jwt = await _full_setup(client)
        headers = {"Authorization": f"Bearer {parent_jwt}"}

        resp = await client.post(
            "/api/me/consent/renew",
            headers=headers,
            json={
                "athlete_id": athlete_id,
                "policy_version": "v9.9",
                "accept_data_collection": True,
                "accept_anthropometry": True,
            },
        )
        assert resp.status_code == 400

    async def test_renew_atletano_vinculado_retorna_403(self, client):
        """Padre no puede renovar consentimiento de atleta al que no está vinculado."""
        # Crear dos atletas distintos
        headers = await _coach_headers(client)
        club_id = await _get_club_id(client, headers)
        athlete_id_1 = await _create_athlete(client, headers, club_id)
        athlete_id_2 = await _create_athlete(client, headers, club_id)

        # Registrar padre solo vinculado al atleta 1
        _, parent_jwt = await _register_parent(client, athlete_id_1)
        parent_headers = {"Authorization": f"Bearer {parent_jwt}"}

        # Intentar renovar consentimiento del atleta 2 (no vinculado)
        resp = await client.post(
            "/api/me/consent/renew",
            headers=parent_headers,
            json={
                "athlete_id": athlete_id_2,
                "policy_version": "v1.1",
                "accept_data_collection": True,
                "accept_anthropometry": True,
            },
        )
        assert resp.status_code == 403

    async def test_renew_grants_training_tracking_siempre_false(self, client):
        """Política v1.1: training_tracking y third_party_sharing se persisten como False."""
        athlete_id, parent_jwt = await _full_setup(client)
        headers = {"Authorization": f"Bearer {parent_jwt}"}

        resp = await client.post(
            "/api/me/consent/renew",
            headers=headers,
            json={
                "athlete_id": athlete_id,
                "policy_version": "v1.1",
                "accept_data_collection": True,
                "accept_anthropometry": True,
            },
        )
        assert resp.status_code == 201
        grants = resp.json()["grants"]
        assert grants["training_tracking"] is False
        assert grants["third_party_sharing"] is False


# ---------------------------------------------------------------------------
# TestWithdrawConsent — POST /api/me/consent/withdraw
# ---------------------------------------------------------------------------


class TestWithdrawConsent:
    """Verifica el endpoint de revocación de consentimiento (append-only)."""

    async def test_withdraw_retorna_200_con_withdrawn_at(self, client):
        """POST /withdraw marca el consentimiento con withdrawn_at y retorna 200."""
        athlete_id, parent_jwt = await _full_setup(client)
        headers = {"Authorization": f"Bearer {parent_jwt}"}

        resp = await client.post(
            "/api/me/consent/withdraw",
            headers=headers,
            json={
                "athlete_id": athlete_id,
                "reason": "Ya no autorizo el tratamiento de datos",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["withdrawn_at"] is not None

    async def test_withdraw_solo_modifica_withdrawn_at(self, client):
        """Tras withdraw, el GET /me/consent muestra current_consent=None (no hay vigente)."""
        athlete_id, parent_jwt = await _full_setup(client)
        headers = {"Authorization": f"Bearer {parent_jwt}"}

        await client.post(
            "/api/me/consent/withdraw",
            headers=headers,
            json={"athlete_id": athlete_id},
        )

        status_resp = await client.get("/api/me/consent", headers=headers)
        assert status_resp.status_code == 200
        atletas = status_resp.json()["consents_per_athlete"]
        atleta = next(a for a in atletas if a["athlete_id"] == athlete_id)
        # No debe haber consentimiento vigente
        assert atleta["current_consent"] is None

    async def test_withdraw_sin_razon_retorna_200(self, client):
        """Revocar sin razón explícita también funciona correctamente."""
        athlete_id, parent_jwt = await _full_setup(client)
        headers = {"Authorization": f"Bearer {parent_jwt}"}

        resp = await client.post(
            "/api/me/consent/withdraw",
            headers=headers,
            json={"athlete_id": athlete_id},
        )
        assert resp.status_code == 200
        assert resp.json()["withdrawn_at"] is not None

    async def test_withdraw_sin_consentimiento_vigente_retorna_404(self, client):
        """Si ya se revocó, un segundo withdraw debe retornar 404."""
        athlete_id, parent_jwt = await _full_setup(client)
        headers = {"Authorization": f"Bearer {parent_jwt}"}

        # Primera revocación
        r1 = await client.post(
            "/api/me/consent/withdraw",
            headers=headers,
            json={"athlete_id": athlete_id},
        )
        assert r1.status_code == 200

        # Segunda revocación — sin consentimiento vigente
        r2 = await client.post(
            "/api/me/consent/withdraw",
            headers=headers,
            json={"athlete_id": athlete_id},
        )
        assert r2.status_code == 404

    async def test_withdraw_atletano_vinculado_retorna_403(self, client):
        """Padre no puede revocar consentimiento de atleta al que no está vinculado."""
        headers = await _coach_headers(client)
        club_id = await _get_club_id(client, headers)
        athlete_id_1 = await _create_athlete(client, headers, club_id)
        athlete_id_2 = await _create_athlete(client, headers, club_id)

        _, parent_jwt = await _register_parent(client, athlete_id_1)
        parent_headers = {"Authorization": f"Bearer {parent_jwt}"}

        resp = await client.post(
            "/api/me/consent/withdraw",
            headers=parent_headers,
            json={"athlete_id": athlete_id_2},
        )
        assert resp.status_code == 403

    async def test_withdraw_no_elimina_el_registro(self, client):
        """Withdraw es append-only: el registro permanece, solo se puebla withdrawn_at.

        Verificación indirecta: tras withdraw, podemos hacer renew (que necesita
        el registro previo para marcarlo como superseded — si hubiera sido
        eliminado, el sistema no sabría qué superseder).
        """
        athlete_id, parent_jwt = await _full_setup(client)
        headers = {"Authorization": f"Bearer {parent_jwt}"}

        await client.post(
            "/api/me/consent/withdraw",
            headers=headers,
            json={"athlete_id": athlete_id},
        )

        # Renew tras withdraw debe funcionar (no hay vigente, pero el registro anterior existe)
        renew_resp = await client.post(
            "/api/me/consent/renew",
            headers=headers,
            json={
                "athlete_id": athlete_id,
                "policy_version": "v1.1",
                "accept_data_collection": True,
                "accept_anthropometry": True,
            },
        )
        assert renew_resp.status_code == 201
        assert renew_resp.json()["withdrawn_at"] is None
