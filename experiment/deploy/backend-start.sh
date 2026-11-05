#!/bin/sh
# Same first-start steps as render-start.sh; each is safe to repeat.
set -e
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py seed_presets
python manage.py import_dld --if-empty data/dld/transactions-2026-10-19.csv.gz
if [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  python manage.py createsuperuser --noinput || true
fi
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120
