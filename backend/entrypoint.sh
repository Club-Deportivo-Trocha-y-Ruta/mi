#!/bin/sh
set -e

echo "Aplicando migraciones..."
alembic upgrade head

if [ "${APP_ENV}" = "development" ]; then
  echo "Cargando seed data..."
  python -m scripts.seed
fi

echo "Iniciando servidor..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
