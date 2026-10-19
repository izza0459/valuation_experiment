#!/bin/sh
# Production start on Render (see render.yaml). Render's free tier has no shell,
# so everything a fresh database needs happens here, on every start; each step
# is safe to repeat.
set -e

python manage.py migrate --noinput
python manage.py seed_presets
# DLD sales for the comparables search (shipped with the app); once only.
python manage.py import_dld --if-empty data/dld/transactions-2026-10-19.csv.gz

# The first admin, from DJANGO_SUPERUSER_EMAIL / _USERNAME / _PASSWORD set in
# Render's dashboard. Fails harmlessly once the account exists.
if [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  python manage.py createsuperuser --noinput || true
fi

# One process with threads: the free instance has 512 MB, and a PDF render
# is the heaviest request.
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-10000}" --workers 1 --threads 4 --timeout 120
