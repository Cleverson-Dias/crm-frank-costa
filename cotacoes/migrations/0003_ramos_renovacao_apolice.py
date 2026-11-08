from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("cotacoes", "0002_seguradora_plano_apolice"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="bem",
            options={"verbose_name": "Bem", "verbose_name_plural": "Bens"},
        ),
        migrations.AddField(
            model_name="cliente",
            name="dados_sinteticos",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="bem",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("auto", "Automóvel"),
                    ("vida", "Vida"),
                    ("saude", "Saúde"),
                    ("residencial", "Residencial (histórico)"),
                ],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="plano",
            name="tipo_seguro",
            field=models.CharField(
                choices=[
                    ("auto", "Automóvel"),
                    ("vida", "Vida"),
                    ("saude", "Saúde"),
                    ("residencial", "Residencial (histórico)"),
                ],
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="RenovacaoApolice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data_vencimento", models.DateField()),
                ("status", models.CharField(choices=[("pendente", "Pendente"), ("renovada", "Renovada"), ("nao_renovada", "Não renovada")], default="pendente", max_length=15)),
                ("data_decisao", models.DateField(blank=True, null=True)),
                ("apolice", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="historico_renovacoes", to="cotacoes.apolice")),
                ("apolice_renovada", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="renovacoes_resultantes", to="cotacoes.apolice")),
            ],
            options={
                "ordering": ["-data_vencimento"],
            },
        ),
        migrations.AddConstraint(
            model_name="renovacaoapolice",
            constraint=models.UniqueConstraint(fields=("apolice", "data_vencimento"), name="uq_renovacao_apolice_vencimento"),
        ),
    ]
