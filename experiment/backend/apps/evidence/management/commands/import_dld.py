"""Loads a DLD transactions CSV (DLD's open-data export) into the comparables
search, sales only:

    python manage.py import_dld path/to/transactions.csv[.gz]
    python manage.py import_dld --if-empty data/dld/transactions-2026.csv.gz

`--if-empty` does nothing once sales are loaded, so a deploy can run it on
every start. Loading the same file again adds nothing.
"""

import gzip

from django.core.management.base import BaseCommand, CommandError

from apps.evidence import dld
from apps.evidence.models import DldTransaction


class Command(BaseCommand):
    help = "Load a DLD transactions CSV (or .csv.gz) into the comparables search (sales only)."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--if-empty", action="store_true", help="Skip when DLD sales are already loaded.")

    def handle(self, *args, path, if_empty=False, **options):
        if if_empty and DldTransaction.objects.exists():
            self.stdout.write("DLD sales already loaded; nothing to do.")
            return
        opener = gzip.open if path.endswith(".gz") else open
        try:
            with opener(path, "rb") as fh:
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
