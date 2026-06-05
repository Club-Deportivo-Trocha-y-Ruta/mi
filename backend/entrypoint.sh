#!/bin/sh
set -e

echo "Aplicando migraciones..."
alembic upgrade head

# Seed determinista y offline de la tabla de referencia CDC LMS
# (constantes poblacionales, sin datos de menores). Idempotente: reejecutar es
# un no-op. Guardado para que un fallo NO tumbe el arranque (log + continuar).
echo "Sembrando datos de referencia LMS (CDC, offline)..."
python -m app.seed_growth_data || echo "WARN: seed LMS falló; el servidor continúa."

# Backfill idempotente de valores derivados (BMI/percentiles) en registros
# antropométricos históricos. Seguro de reejecutar; nunca toca medidas crudas.
echo "Backfill de antropometría (idempotente)..."
python -m app.scripts.backfill_anthropometry || echo "WARN: backfill antropometría falló; el servidor continúa."

if [ "${APP_ENV}" = "development" ]; then
  echo "Cargando seed data..."
  python -m scripts.seed
fi

echo "Iniciando servidor..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
