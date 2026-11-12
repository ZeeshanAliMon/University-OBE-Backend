from django.db import migrations, models


def fill_years(apps, schema_editor):
    """Responses saved before each kept its own year take their file's year."""
    SurveyResponse = apps.get_model('core', 'SurveyResponse')
    for response in SurveyResponse.objects.select_related('upload'):
        response.year = response.upload.year
        response.save(update_fields=['year'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0018_department_direct_weight'),
    ]

    operations = [
        migrations.AlterUniqueTogether(name='surveyupload', unique_together=set()),
        migrations.AlterModelOptions(name='surveyupload', options={'ordering': ['form_type', '-uploaded_at']}),
        migrations.AlterField(model_name='surveyupload', name='year', field=models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField(model_name='surveyresponse', name='year', field=models.PositiveSmallIntegerField(db_index=True, null=True)),
        migrations.AddField(model_name='surveyresponse', name='period', field=models.CharField(blank=True, max_length=40)),
        migrations.RunPython(fill_years, migrations.RunPython.noop),
        migrations.AlterField(model_name='surveyresponse', name='year', field=models.PositiveSmallIntegerField(db_index=True)),
    ]
