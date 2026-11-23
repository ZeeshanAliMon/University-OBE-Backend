from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0021_survey_recipients'),
    ]

    operations = [
        migrations.AddField(
            model_name='surveyresponse',
            name='employment_status',
            field=models.CharField(blank=True, max_length=40),
        ),
    ]
