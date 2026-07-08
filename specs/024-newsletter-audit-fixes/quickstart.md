# Quickstart — Validación Newsletter Audit Fixes (024)

## Prerrequisitos

```bash
source backend/.venv/bin/activate
cd backend
# BD dev con seed (atleta femenina con resultado en Campeonato Departamental,
# sesiones ejecutadas en junio 2026 y ≥1 foto con consent_ack=True)
docker compose up -d   # o BD local ya migrada
```

## 1. Tests (regresión + nuevos)

```bash
cd backend && pytest tests/test_newsletter_builder_024.py \
  tests/test_newsletter_privacy.py \
  tests/test_newsletter_ai_captions.py \
  tests/routers/test_athlete_monthly_newsletters_router.py -q
cd frontend && npx vitest run src/components/training/NewsletterPreviewBlocks.test.tsx
```

Esperado: verde. Los tests de bugs A1–A5 y B12 fallan sobre el código previo (regresión genuina).

## 2. Regenerar boletín de la atleta auditada (junio 2026)

```bash
# Con el server corriendo (uvicorn app.main:app --reload) y token de coach:
curl -X POST "http://localhost:8000/api/athletes/{athlete_id}/monthly-newsletters" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"year": 2026, "month": 6}'
# Descargar PDF por el endpoint existente y abrirlo
```

## 3. Checklist visual del PDF (contra spec)

| # | Verificar | Criterio |
|---|---|---|
| A1 | KPI página 1 | "2° · CD" (nunca "V1"); tabla dice "Campeonato Departamental" |
| A2 | Valoración del entrenador | "su hija"/"ella" para atleta F; neutro si sexo ausente |
| A3 | Galería | Imágenes visibles; sin fotos elegibles → sección ausente; no embebibles → placeholder con conteo |
| A4 | Fila RPE | Referencia "0-10 (base: 3-5 · alta intensidad: 6-8)" |
| A5 | Fila horas | "≈6,4 h/sem (límite personal ≤13,9 h/sem)" + estado ✓ |
| B6 | Focos del mes | ≤10 grupos con conteo, sin lista cruda de ~15 títulos |
| B7 | Categoría | "Prejuvenil A Femenina" (label del seed), no "PJUV_A_F" |
| B8 | Fechas | "1 de agosto de 2026" en próximas válidas/sesiones |
| B9 | Página 1 | Valoración comienza en página 1; ≥70% de área usada |
| B10 | Gráficos | Ningún valor recortado (pos 1, máx puntos, gap mínimo) |
| B11 | Tabla antro | Headers "IMC", "Z-Talla", "P-Talla" legibles |
| B12 | Racha | Una sola mención, "sesiones seguidas" |
| B13 | Gráfico puntos | Nota "los campeonatos no otorgan puntos de Copa" |
| B14 | Apoyo desde casa | Solo banda 13-15 (sueño 8-10 h); regenerar otro mes → tips distintos; mismo mes → idénticos |

## 4. Compatibilidad y privacidad

```bash
# Renderizar un boletín pre-024 existente (snapshot viejo) → sin error:
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/athletes/{athlete_id}/monthly-newsletters/2026/5/pdf" -o /tmp/old.pdf
# Verificar snapshot sin data URIs:
pytest tests/test_newsletter_privacy.py -q -k "data_uri or datauri"
```

## 5. Email (dispatcher)

Enviar preview/batch en dev y verificar: fechas en español, labels CD/categoría legible, sin galería, sin antropometría, sin data URIs (invariantes existentes + nuevas).

Referencias: [contracts/metrics-snapshot.md](./contracts/metrics-snapshot.md) · [data-model.md](./data-model.md) · [research.md](./research.md)
