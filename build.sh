#!/usr/bin/env bash
# build.sh - Script para Render

echo "Aplicando migraciones..."
python manage.py migrate

echo "Recolectando archivos estáticos..."
python manage.py collectstatic --no-input