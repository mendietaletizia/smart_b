# Generated migration for HistorialEntrenamiento
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('reportes_dinamicos', '0002_add_modeloia_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='HistorialEntrenamiento',
            fields=[
                ('id_historial', models.AutoField(primary_key=True, serialize=False)),
                ('fecha_inicio', models.DateTimeField(auto_now_add=True)),
                ('fecha_fin', models.DateTimeField(blank=True, null=True)),
                ('estado', models.CharField(choices=[('iniciado', 'Iniciado'), ('completado', 'Completado'), ('error', 'Error')], default='iniciado', max_length=20)),
                ('registros_procesados', models.IntegerField(default=0)),
                ('metricas', models.JSONField(blank=True, default=dict)),
                ('mensaje_error', models.TextField(blank=True, null=True)),
                ('modelo', models.ForeignKey(db_column='id_modelo', on_delete=django.db.models.deletion.CASCADE, to='reportes_dinamicos.modeloia')),
            ],
            options={
                'db_table': 'historial_entrenamiento',
                'verbose_name': 'Historial de Entrenamiento',
                'verbose_name_plural': 'Historiales de Entrenamiento',
                'ordering': ['-fecha_inicio'],
            },
        ),
    ]


