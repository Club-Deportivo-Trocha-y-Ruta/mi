"""CORS debe exponer ETag y X-Request-Id, y aceptar If-Match.

Contrato: specs/041-multi-coach-governance/contracts/audit-recording.md §3.1
(bloque autoritativo), citado desde concurrency-and-approvals.md §1.3/§9 T21
y audit-log-api.md §9. Sin esto la concurrencia optimista (If-Match) degrada
silenciosamente a "sin detección de conflicto" y el frontend no puede leer
ni ETag ni X-Request-Id entre orígenes.
"""



async def test_preflight_allows_if_match_header(client):
    """Un preflight OPTIONS pidiendo enviar If-Match debe ser permitido."""
    response = await client.options(
        "/api/clubs",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "if-match",
        },
    )
    assert response.status_code in (200, 204)
    allow_headers = response.headers.get("access-control-allow-headers", "").lower()
    assert "if-match" in allow_headers


async def test_get_exposes_etag_and_request_id_headers(client):
    """Una respuesta GET cross-origin debe declarar ETag y X-Request-Id
    en Access-Control-Expose-Headers para que el JS del navegador pueda
    leerlas (si no, quedan invisibles aunque el servidor las mande)."""
    response = await client.get(
        "/docs",
        headers={"Origin": "http://localhost:5173"},
    )
    expose_headers = response.headers.get("access-control-expose-headers", "")
    values = {value.strip().lower() for value in expose_headers.split(",") if value.strip()}
    assert "etag" in values
    assert "x-request-id" in values
