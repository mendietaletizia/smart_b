# Generated migration to add new fields to ModeloIA
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reportes_dinamicos', '0001_initial_reportes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='modeloia',
            name='fecha_entrenamiento',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='modeloia',
            name='nombre',
            field=models.CharField(default='Modelo de Predicción de Ventas', max_length=100),
        ),
        migrations.AlterField(
            model_name='modeloia',
            name='algoritmo',
            field=models.CharField(default='random_forest', max_length=50),
        ),
        migrations.AlterField(
            model_name='modeloia',
            name='estado',
            field=models.CharField(choices=[('activo', 'Activo'), ('entrenando', 'Entrenando'), ('retirado', 'Retirado'), ('error', 'Error')], default='retirado', max_length=20),
        ),
        migrations.AddField(
            model_name='modeloia',
            name='fecha_ultima_actualizacion',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='modeloia',
            name='mae',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='modeloia',
            name='registros_entrenamiento',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='modeloia',
            name='proxima_actualizacion',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]


