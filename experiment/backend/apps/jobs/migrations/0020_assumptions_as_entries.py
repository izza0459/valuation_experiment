"""Assumptions become a list of paragraphs, each picked and edited like the
Special Assumptions, with a Yes / No for each (report text inputs, Oct 2026).

Text entered before becomes one entry. Built as add / copy / drop / rename
rather than a type change: Postgres can't cast free text to JSON."""

from django.db import migrations, models


def to_entries(apps, schema_editor):
    SummaryData = apps.get_model("jobs", "SummaryData")
    for row in SummaryData.objects.all().only("pk", "assumptions", "special_assumptions"):
        text = (row.assumptions or "").strip()
        SummaryData.objects.filter(pk=row.pk).update(
            assumption_entries=[{"title": "", "body": text}] if text else [],
            has_assumptions=bool(text),
            has_special_assumptions=bool(row.special_assumptions),
        )


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0019_reviewer_edits"),
    ]

    operations = [
        migrations.AddField(
            model_name="summarydata",
            name="has_assumptions",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="summarydata",
            name="has_special_assumptions",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="summarydata",
            name="assumption_entries",
            field=models.JSONField(blank=True, default=list, help_text="[{title, body}]"),
        ),
        migrations.RunPython(to_entries, migrations.RunPython.noop),
        migrations.RemoveField(model_name="summarydata", name="assumptions"),
        migrations.RenameField(model_name="summarydata", old_name="assumption_entries", new_name="assumptions"),
    ]
