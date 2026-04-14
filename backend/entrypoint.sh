#!/bin/sh
set -e

echo "Aplicando migraciones..."
alembic upgrade head

echo "Cargando seed data..."
python -m scripts.seed

echo "Iniciando servidor..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
