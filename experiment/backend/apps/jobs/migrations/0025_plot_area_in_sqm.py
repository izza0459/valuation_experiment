from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations, models

SQFT_PER_SQM = Decimal("10.76391")


def to_sqm(apps, schema_editor):
    """Plot areas entered in sqft keep their value, now held in sqm (QA #11)."""
    SummaryData = apps.get_model("jobs", "SummaryData")
    for row in SummaryData.objects.exclude(plot_area_sqft=None):
        row.plot_area_sqm = (row.plot_area_sqft / SQFT_PER_SQM).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        row.save(update_fields=["plot_area_sqm"])


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0024_reviewer_suggestions"),
    ]

    operations = [
        migrations.AddField(
            model_name="summarydata",
            name="plot_area_sqm",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.RunPython(to_sqm, migrations.RunPython.noop),
    ]
