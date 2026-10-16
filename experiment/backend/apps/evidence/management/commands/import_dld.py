"""Loads a DLD transactions CSV (downloaded from DLD's open data) for large
files that are too big to upload through the app:

    python manage.py import_dld path/to/transactions.csv
"""

from django.core.management.base import BaseCommand, CommandError

from apps.evidence import dld


class Command(BaseCommand):
    help = "Load a DLD transactions CSV into the comparables search (sales only)."

    def add_arguments(self, parser):
        parser.add_argument("path")

    def handle(self, *args, path, **options):
        try:
            with open(path, "rb") as fh:
                result = dld.import_file(fh)
        except OSError as exc:
            raise CommandError(f"Can't read {path}: {exc}") from exc
        except dld.DldFileError as exc:
            raise CommandError(str(exc)) from exc
        status = dld.data_status()
        self.stdout.write(self.style.SUCCESS(
            f"Read {result['rows']} rows: {result['added']} sales added, {result['already_loaded']} already loaded, "
            f"{result['skipped']} skipped. {status['count']} sales loaded, {status['earliest']} to {status['latest']}."
        ))
