from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_survey_response_program_optional'),
    ]

    operations = [
        migrations.CreateModel(
            name='SurveyRecipients',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('form_type', models.CharField(max_length=20)),
                ('group_key', models.CharField(max_length=20)),
                ('count', models.PositiveIntegerField()),
                ('department', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='survey_recipients', to='core.department')),
            ],
            options={
                'unique_together': {('department', 'form_type', 'group_key')},
            },
        ),
    ]
