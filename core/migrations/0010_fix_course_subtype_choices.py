# Generated 2026-07-11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_course_subtype'),
    ]

    operations = [
        migrations.AlterField(
            model_name='course',
            name='subtype',
            field=models.CharField(
                choices=[('theory', 'Theory'), ('lab', 'Lab')],
                default='theory',
                max_length=10,
            ),
        ),
    ]
