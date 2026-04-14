import pytest

from app.services.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        password = "Coach2026!"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed)

    def test_wrong_password(self):
        hashed = hash_password("correct")
        assert not verify_password("wrong", hashed)


class TestJWT:
    def test_access_token_roundtrip(self):
        data = {"sub": "1", "role": "coach", "club_ids": [1]}
        token = create_access_token(data)
        payload = decode_token(token)
        assert payload["sub"] == "1"
        assert payload["role"] == "coach"
        assert payload["club_ids"] == [1]
        assert payload["type"] == "access"

    def test_refresh_token_roundtrip(self):
        data = {"sub": "2", "role": "admin", "club_ids": []}
        token = create_refresh_token(data)
        payload = decode_token(token)
        assert payload["sub"] == "2"
        assert payload["type"] == "refresh"

    def test_invalid_token(self):
        import jwt

        with pytest.raises(jwt.InvalidTokenError):
            decode_token("esto.no.es.un.token.valido")


class TestLoginEndpoint:
    async def test_login_success(self, client):
        resp = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    async def test_login_wrong_password(self, client):
        resp = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "wrong"},
        )
        assert resp.status_code == 401

    async def test_login_unknown_email(self, client):
        resp = await client.post(
            "/api/auth/login",
            json={"email": "noexiste@test.com", "password": "any"},
        )
        assert resp.status_code == 401


class TestRefreshEndpoint:
    async def test_refresh_success(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        refresh_token = login.json()["refresh_token"]

        resp = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body

    async def test_refresh_with_access_token_fails(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        access_token = login.json()["access_token"]

        resp = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": access_token},
        )
        assert resp.status_code == 401


class TestMeEndpoint:
    async def test_me_authenticated(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        token = login.json()["access_token"]

        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "admin@trochyruta.com"
        assert body["role"] == "admin"
        assert "club_ids" in body

    async def test_me_no_token(self, client):
        resp = await client.get("/api/auth/me")
        assert resp.status_code in (401, 403)

    async def test_me_invalid_token(self, client):
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer token-falso"},
        )
        assert resp.status_code == 401
