import django.core.validators
from django.db import migrations, models
from django.db.models import F


def count_the_ground(apps, schema_editor):
    """The floor count includes the ground floor again: G+2 was saved as 2,
    now 3; ground only was 0, now 1."""
    InspectionData = apps.get_model("jobs", "InspectionData")
    InspectionData.objects.exclude(floors_above_ground=None).update(floors_above_ground=F("floors_above_ground") + 1)


def above_ground_only(apps, schema_editor):
    InspectionData = apps.get_model("jobs", "InspectionData")
    InspectionData.objects.filter(floors_above_ground__gte=1).update(floors_above_ground=F("floors_above_ground") - 1)


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0026_floors_above_ground_from_zero"),
    ]

    operations = [
        migrations.RunPython(count_the_ground, above_ground_only),
        migrations.AlterField(
            model_name="inspectiondata",
            name="floors_above_ground",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True,
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(6)],
            ),
        ),
    ]
