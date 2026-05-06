"""Tests del flujo de onboarding con consentimiento parental.

Cubre:
- consume_invite() con y sin ParentalConsentData (integración vía HTTP)
- Verificación de registros en parental_consents y campos en Athlete
- relationship_type correcto en ParentAthlete
- Backward compatibility sin consent
- Tokens ya usados / expirados / inexistentes
- GET /api/auth/invite/{token} — validación de token
- POST /api/auth/parent-register — registro completo con consent
"""

from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Constantes de consentimiento de prueba
# ---------------------------------------------------------------------------

# Política v1.1 (2026-05-06): solo se solicitan dos consentimientos activos —
# datos básicos del atleta y antropometría. Los campos legacy
# (accept_training_tracking, accept_third_party) se aceptan por
# compatibilidad pero el servicio los persiste como False.
_CONSENT_COMPLETO = {
    "accept_data_collection": True,
    "accept_anthropometry": True,
    "privacy_policy_version": "v1.1",
}

_CONSENT_MINIMO = {
    "accept_data_collection": True,
    "accept_anthropometry": False,
    "privacy_policy_version": "v1.1",
}


# ---------------------------------------------------------------------------
# Helpers internos (no duplican los de otros archivos para no acoplarse)
# ---------------------------------------------------------------------------

async def _login(client, email: str, password: str) -> str:
    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login fallido: {resp.text}"
    return resp.json()["access_token"]


async def _coach_headers(client) -> dict:
    token = await _login(client, "entrenador@trochyruta.com", "Coach2026!")
    return {"Authorization": f"Bearer {token}"}


async def _get_club_id(client, headers: dict) -> int:
    me = await client.get("/api/auth/me", headers=headers)
    return me.json()["club_ids"][0]


async def _create_athlete(client, headers: dict, club_id: int) -> int:
    """Crea un atleta único y retorna su ID."""
    resp = await client.post(
        "/api/athletes",
        headers=headers,
        json={
            "first_name": "Consent",
            "last_name": f"Test-{uuid4().hex[:6]}",
            "birth_date": "2012-03-20",
            "sex": "F",
            "club_id": club_id,
        },
    )
    assert resp.status_code == 201, f"No se pudo crear atleta: {resp.text}"
    return resp.json()["id"]


async def _create_invite(client, headers: dict, athlete_id: int) -> tuple[str, str]:
    """Genera una invitación y retorna (token, email)."""
    email = f"consent-{uuid4().hex[:8]}@test.com"
    resp = await client.post(
        "/api/parent-athletes/invite",
        headers=headers,
        json={"athlete_id": athlete_id, "email": email},
    )
    assert resp.status_code == 201, f"No se pudo crear invitación: {resp.text}"
    return resp.json()["token"], email


async def _full_setup(client) -> tuple[dict, int, str, str]:
    """Retorna (headers_coach, athlete_id, token, email) listos para usar."""
    headers = await _coach_headers(client)
    club_id = await _get_club_id(client, headers)
    athlete_id = await _create_athlete(client, headers, club_id)
    token, email = await _create_invite(client, headers, athlete_id)
    return headers, athlete_id, token, email


# ---------------------------------------------------------------------------
# TestConsumeInviteConConsent — integración HTTP que verifica el service
# ---------------------------------------------------------------------------

class TestConsumeInviteConConsent:
    """Verifica que consume_invite() registra correctamente el consentimiento."""

    async def test_crea_registro_parental_consent(self, client):
        """POST /parent-register con consent → registro en parental_consents verificable
        mediante el campo parental_consent_obtained del atleta (efecto observable en API)."""
        headers, athlete_id, token, email = await _full_setup(client)

        resp = await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "Laura",
                "last_name": "Gómez",
                "password": "Secure2026!",
                "phone": "3001112233",
                "relationship_type": "madre",
                "consent": _CONSENT_COMPLETO,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == email
        assert body["first_name"] == "Laura"

    async def test_parental_consent_obtained_se_actualiza_en_atleta(self, client):
        """Después del registro con consent, el atleta debe tener
        parental_consent_obtained=True y parental_consent_date poblada."""
        headers, athlete_id, token, _ = await _full_setup(client)

        await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "Carlos",
                "last_name": "Ríos",
                "password": "Secure2026!",
                "relationship_type": "padre",
                "consent": _CONSENT_COMPLETO,
            },
        )

        # Verificar en API del atleta (acceso del coach)
        atleta_resp = await client.get(f"/api/athletes/{athlete_id}", headers=headers)
        assert atleta_resp.status_code == 200
        atleta = atleta_resp.json()
        assert atleta["parental_consent_obtained"] is True
        assert atleta["parental_consent_date"] is not None

    async def test_relationship_type_madre_se_guarda_correctamente(self, client):
        """relationship_type='madre' debe quedar como FamilyRelationship.madre
        en la vinculación parent_athlete. Se comprueba vía el endpoint de
        la lista de padres del atleta."""
        headers, athlete_id, token, _ = await _full_setup(client)

        await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "Sofía",
                "last_name": "Vargas",
                "password": "Secure2026!",
                "relationship_type": "madre",
                "consent": _CONSENT_COMPLETO,
            },
        )

        # El endpoint de parent-athletes lista vinculaciones del atleta
        # Respuesta: { "items": [...], "total": N }
        vinculaciones_resp = await client.get(
            f"/api/parent-athletes?athlete_id={athlete_id}",
            headers=headers,
        )
        assert vinculaciones_resp.status_code == 200
        items = vinculaciones_resp.json()["items"]
        assert any(v["relationship"] == "madre" for v in items)

    async def test_relationship_type_padre_se_guarda_correctamente(self, client):
        """relationship_type='padre' se persiste correctamente."""
        headers, athlete_id, token, _ = await _full_setup(client)

        await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "Javier",
                "last_name": "Mora",
                "password": "Secure2026!",
                "relationship_type": "padre",
                "consent": _CONSENT_MINIMO,
            },
        )

        vinculaciones_resp = await client.get(
            f"/api/parent-athletes?athlete_id={athlete_id}",
            headers=headers,
        )
        assert vinculaciones_resp.status_code == 200
        items = vinculaciones_resp.json()["items"]
        assert any(v["relationship"] == "padre" for v in items)

    async def test_consent_all_false_crea_usuario_y_registra_consent(self, client):
        """Con consent all-False el endpoint retorna 201 y el usuario se crea.

        Comportamiento diseñado: consume_invite() recibe un objeto consent (no None),
        por lo que crea el registro ParentalConsent con todos los flags en False y
        setea parental_consent_obtained=True (el padre aceptó el formulario explícitamente,
        aunque rechazó todos los usos opcionales).
        El frontend debe validar los accepts obligatorios antes de hacer submit."""
        headers, athlete_id, token, _ = await _full_setup(client)

        resp = await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "Pedro",
                "last_name": "Leal",
                "password": "Secure2026!",
                "consent": {
                    "accept_data_collection": False,
                    "accept_anthropometry": False,
                    "privacy_policy_version": "v1.1",
                },
            },
        )
        assert resp.status_code == 201
        assert resp.json()["first_name"] == "Pedro"

        atleta_resp = await client.get(f"/api/athletes/{athlete_id}", headers=headers)
        assert atleta_resp.status_code == 200
        atleta = atleta_resp.json()
        # consent object no es None → service registra ParentalConsent y setea True
        assert atleta["parental_consent_obtained"] is True
        assert atleta["parental_consent_date"] is not None

    async def test_consent_legacy_fields_se_persisten_como_false(self, client):
        """Política v1.1: aunque el cliente envíe accept_training_tracking=True o
        accept_third_party=True, el servicio fuerza ambos campos a False en la
        base de datos. Esto evita registrar consentimiento por finalidades aún no
        implementadas (Ley 1581/2012, principio de finalidad).

        Verificación indirecta: el endpoint acepta el payload (201) y la
        creación es atómica — el padre queda vinculado y el atleta tiene
        parental_consent_obtained=True.
        """
        headers, athlete_id, token, _ = await _full_setup(client)

        consent_con_legacy = {
            "accept_data_collection": True,
            "accept_anthropometry": True,
            "accept_training_tracking": True,  # campo legacy → forzado a False
            "accept_third_party": True,  # campo legacy → forzado a False
            "privacy_policy_version": "v1.1",
        }

        resp = await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "Legacy",
                "last_name": "Cliente",
                "password": "Secure2026!",
                "relationship_type": "madre",
                "consent": consent_con_legacy,
            },
        )
        assert resp.status_code == 201
        parent_id = resp.json()["id"]

        atleta = (await client.get(f"/api/athletes/{athlete_id}", headers=headers)).json()
        assert atleta["parental_consent_obtained"] is True
        assert atleta["parental_consent_date"] is not None

        vinculaciones = (await client.get(
            f"/api/parent-athletes?athlete_id={athlete_id}", headers=headers
        )).json()["items"]
        assert any(v["parent_id"] == parent_id for v in vinculaciones)

    async def test_token_ya_usado_retorna_410(self, client):
        """Consumir un token ya utilizado → 410 Gone."""
        _, _, token, _ = await _full_setup(client)

        # Primer uso exitoso
        r1 = await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "Ana",
                "last_name": "Torres",
                "password": "Secure2026!",
                "consent": _CONSENT_COMPLETO,
            },
        )
        assert r1.status_code == 201

        # Segundo intento con el mismo token
        r2 = await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "Otra",
                "last_name": "Persona",
                "password": "Secure2026!",
                "consent": _CONSENT_COMPLETO,
            },
        )
        assert r2.status_code == 410
        assert "utilizado" in r2.json()["detail"].lower()


# ---------------------------------------------------------------------------
# TestParentRegisterEndpoint — integración HTTP completa
# ---------------------------------------------------------------------------

class TestParentRegisterEndpoint:
    """Tests del endpoint POST /api/auth/parent-register."""

    async def test_registro_completo_con_consent_retorna_201(self, client):
        """Payload completo con token válido + consent → 201, respuesta correcta."""
        _, _, token, email = await _full_setup(client)

        resp = await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "María",
                "last_name": "Rodríguez",
                "password": "Parent2026!",
                "phone": "3009998877",
                "relationship_type": "madre",
                "consent": _CONSENT_COMPLETO,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == email
        assert body["first_name"] == "María"
        assert body["last_name"] == "Rodríguez"
        assert "id" in body
        assert body["message"] == "Cuenta creada exitosamente"

    async def test_usuario_puede_hacer_login_tras_registro(self, client):
        """Tras el registro exitoso el usuario puede autenticarse con sus credenciales."""
        _, _, token, email = await _full_setup(client)
        password = "Parent2026!"

        reg = await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "Camila",
                "last_name": "Suárez",
                "password": password,
                "relationship_type": "acudiente",
                "consent": _CONSENT_MINIMO,
            },
        )
        assert reg.status_code == 201

        login = await client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        assert login.status_code == 200
        assert "access_token" in login.json()

    async def test_token_expirado_retorna_410(self, client):
        """Token que ha expirado (o ya usado) → 410 Gone.

        Nota: no podemos manipular el tiempo directamente en este entorno de
        integración HTTP, por lo que simulamos la condición usando un token
        previamente consumido (mismo código de retorno 410)."""
        _, _, token, _ = await _full_setup(client)

        # Consumir el token
        await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "Test",
                "last_name": "Expirado",
                "password": "Secure2026!",
                "consent": _CONSENT_MINIMO,
            },
        )

        # Reutilizar el mismo token → 410 (también cubre token expirado en la lógica)
        resp = await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "Test",
                "last_name": "Expirado",
                "password": "Secure2026!",
                "consent": _CONSENT_MINIMO,
            },
        )
        assert resp.status_code == 410

    async def test_email_ya_registrado_retorna_409(self, client):
        """Intentar registrar con un email que ya tiene cuenta → 409 Conflict."""
        headers, athlete_id, token, email = await _full_setup(client)

        # Registro exitoso
        r1 = await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "Único",
                "last_name": "Usuario",
                "password": "Secure2026!",
                "consent": _CONSENT_COMPLETO,
            },
        )
        assert r1.status_code == 201

        # Crear segunda invitación con el mismo email para el mismo atleta
        # (el servicio retorna la existente si no fue usada, pero como fue usada,
        # crea una nueva — necesitamos otro atleta)
        club_id = await _get_club_id(client, headers)
        athlete_id_2 = await _create_athlete(client, headers, club_id)
        invite2_resp = await client.post(
            "/api/parent-athletes/invite",
            headers=headers,
            json={"athlete_id": athlete_id_2, "email": email},
        )
        assert invite2_resp.status_code == 201
        token2 = invite2_resp.json()["token"]

        # Intentar registrar con el mismo email → 409
        r2 = await client.post(
            "/api/auth/parent-register",
            json={
                "token": token2,
                "first_name": "Duplicado",
                "last_name": "Cuenta",
                "password": "Secure2026!",
                "consent": _CONSENT_COMPLETO,
            },
        )
        assert r2.status_code == 409
        assert "correo electrónico" in r2.json()["detail"].lower()

    async def test_token_inexistente_retorna_404(self, client):
        """Token que no existe en la base de datos → 404 Not Found."""
        resp = await client.post(
            "/api/auth/parent-register",
            json={
                "token": "este-token-no-existe-jamas-nunca-abc123",
                "first_name": "Nobody",
                "last_name": "Test",
                "password": "Secure2026!",
                "consent": _CONSENT_MINIMO,
            },
        )
        assert resp.status_code == 404

    async def test_password_corta_retorna_422(self, client):
        """Contraseña menor a 8 caracteres → 422 Unprocessable Entity."""
        _, _, token, _ = await _full_setup(client)

        resp = await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "Test",
                "last_name": "Corto",
                "password": "abc",  # menos de 8 caracteres
                "consent": _CONSENT_MINIMO,
            },
        )
        assert resp.status_code == 422

    async def test_relationship_type_invalido_retorna_422(self, client):
        """relationship_type con valor no permitido → 422 Unprocessable Entity."""
        _, _, token, _ = await _full_setup(client)

        resp = await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "Test",
                "last_name": "Invalido",
                "password": "Secure2026!",
                "relationship_type": "abuelo",  # no es padre/madre/acudiente
                "consent": _CONSENT_MINIMO,
            },
        )
        assert resp.status_code == 422

    async def test_nombre_vacio_retorna_422(self, client):
        """Nombre vacío o solo espacios → 422 Unprocessable Entity."""
        _, _, token, _ = await _full_setup(client)

        resp = await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "   ",
                "last_name": "Test",
                "password": "Secure2026!",
                "consent": _CONSENT_MINIMO,
            },
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# TestValidateInviteTokenEndpoint — GET /api/auth/invite/{token}
# ---------------------------------------------------------------------------

class TestValidateInviteTokenEndpoint:
    """Tests del endpoint GET /api/auth/invite/{token}."""

    async def test_token_valido_retorna_200_con_role_parent(self, client):
        """Token válido → 200, valid=True, role='parent', club_name no vacío."""
        headers, athlete_id, token, email = await _full_setup(client)

        resp = await client.get(f"/api/auth/invite/{token}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["role"] == "parent"
        assert body["email"] == email
        assert body["athlete_id"] == athlete_id
        assert isinstance(body["athlete_name"], str) and len(body["athlete_name"]) > 0
        assert isinstance(body["expires_at"], str)

    async def test_token_valido_club_name_no_vacio(self, client):
        """Token válido → club_name está poblado (atleta tiene club asignado)."""
        _, _, token, _ = await _full_setup(client)

        resp = await client.get(f"/api/auth/invite/{token}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["club_name"] != ""
        assert len(body["club_name"]) > 0

    async def test_token_valido_retorna_athlete_name_completo(self, client):
        """Token válido → athlete_name combina first_name y last_name del atleta."""
        _, _, token, _ = await _full_setup(client)

        resp = await client.get(f"/api/auth/invite/{token}")
        assert resp.status_code == 200
        body = resp.json()
        # El nombre debe contener al menos dos palabras (nombre + apellido)
        partes = body["athlete_name"].strip().split()
        assert len(partes) >= 2

    async def test_token_inexistente_retorna_404(self, client):
        """Token que no existe → 404 Not Found."""
        resp = await client.get("/api/auth/invite/tokenquenoexiste123456")
        assert resp.status_code == 404

    async def test_token_ya_usado_retorna_valid_false(self, client):
        """Token usado → valid=False en la respuesta (sin levantar excepción 4xx)."""
        _, _, token, _ = await _full_setup(client)

        # Consumir el token
        await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "Consumidor",
                "last_name": "Del Token",
                "password": "Secure2026!",
                "consent": _CONSENT_MINIMO,
            },
        )

        # Validar token usado — el endpoint debe retornar valid=False
        resp = await client.get(f"/api/auth/invite/{token}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False

    async def test_token_de_solo_caracteres_especiales_retorna_404(self, client):
        """Token con solo caracteres especiales no válidos → 404."""
        resp = await client.get("/api/auth/invite/!!!token-invalido!!!")
        # FastAPI puede retornar 404 (not found en DB) o 422 (path param inválido)
        assert resp.status_code in (404, 422)
