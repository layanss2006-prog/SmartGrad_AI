from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_alter_task_assigned_to"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="start_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
