import django.core.validators
from django.db import migrations, models
from django.db.models import F


def above_ground_only(apps, schema_editor):
    """The ground floor no longer counts (QA #12): G+1 was saved as 2, now 1."""
    InspectionData = apps.get_model("jobs", "InspectionData")
    InspectionData.objects.filter(floors_above_ground__gte=1).update(floors_above_ground=F("floors_above_ground") - 1)


def ground_counts_again(apps, schema_editor):
    InspectionData = apps.get_model("jobs", "InspectionData")
    InspectionData.objects.exclude(floors_above_ground=None).update(floors_above_ground=F("floors_above_ground") + 1)


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0025_plot_area_in_sqm"),
    ]

    operations = [
        migrations.AlterField(
            model_name="inspectiondata",
            name="floors_above_ground",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True,
                validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(5)],
            ),
        ),
        migrations.RunPython(above_ground_only, ground_counts_again),
    ]
