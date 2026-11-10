from django.db import migrations


PRODUTOS = [
    (
        "SulAmérica",
        "SulAmérica Direto Nacional",
        "PME / Empresarial",
        "Enfermaria ou Apartamento",
        "Opcional",
        "Ambulatorial + Hospitalar com Obstetrícia (AHO)",
    ),
    (
        "SulAmérica",
        "SulAmérica Direto Mais",
        "PME / Empresarial",
        "Enfermaria ou Apartamento",
        "Opcional",
        "AHO, rede regional e benefícios adicionais",
    ),
    (
        "SulAmérica",
        "SulAmérica Clássico",
        "PME / Empresarial",
        "Enfermaria ou Apartamento",
        "Opcional",
        "AHO, assistência viagem nacional e reembolso de consulta de urgência",
    ),
    (
        "SulAmérica",
        "SulAmérica Especial 100",
        "PME / Empresarial",
        "Enfermaria ou Apartamento",
        "Opcional",
        "AHO, reembolso e serviços ampliados",
    ),
    (
        "SulAmérica",
        "SulAmérica Especial Mais",
        "PME / Empresarial",
        "Enfermaria ou Apartamento",
        "Opcional",
        "AHO, check-up, vacinas e concierge maternidade",
    ),
    (
        "SulAmérica",
        "SulAmérica Executivo",
        "PME / Empresarial",
        "Enfermaria ou Apartamento",
        "Opcional",
        "AHO, reembolso e retaguarda em hospitais premium",
    ),
    (
        "SulAmérica",
        "SulAmérica Prestige",
        "PME / Empresarial",
        "Apartamento",
        "Opcional",
        "Cobertura premium, reembolso e serviços ampliados",
    ),
    (
        "SulAmérica",
        "SulAmérica Exato",
        "PME / Empresarial",
        "Enfermaria ou Apartamento",
        "Opcional",
        "Linha empresarial/PME",
    ),
    (
        "Bradesco Saúde",
        "Bradesco Saúde Efetivo",
        "Empresarial",
        "Enfermaria ou Apartamento",
        "Opcional",
        "Ambulatorial, hospitalar e obstetrícia",
    ),
    (
        "Bradesco Saúde",
        "Bradesco Saúde Efetivo Plus",
        "Empresarial",
        "Enfermaria ou Apartamento",
        "Opcional",
        "Ambulatorial, hospitalar e obstetrícia",
    ),
    (
        "Bradesco Saúde",
        "Bradesco Saúde Flex",
        "Empresarial",
        "Enfermaria ou Apartamento",
        "Opcional",
        "Rede nacional intermediária",
    ),
    (
        "Bradesco Saúde",
        "Bradesco Saúde Ideal",
        "Empresarial",
        "Enfermaria ou Apartamento",
        "Opcional",
        "Rede nacional intermediária",
    ),
    (
        "Bradesco Saúde",
        "Bradesco Saúde Nacional",
        "Empresarial",
        "Enfermaria ou Apartamento",
        "Opcional",
        "Rede nacional ampla",
    ),
    (
        "Bradesco Saúde",
        "Bradesco Saúde Nacional Flex",
        "Empresarial",
        "Enfermaria ou Apartamento",
        "Opcional",
        "Rede nacional intermediária/ampla",
    ),
    (
        "Bradesco Saúde",
        "Bradesco Saúde Nacional Plus",
        "Empresarial",
        "Apartamento",
        "Opcional",
        "Rede ampliada e reembolso",
    ),
    (
        "Bradesco Saúde",
        "Bradesco Saúde Premium",
        "Empresarial",
        "Apartamento",
        "Opcional",
        "Rede premium e reembolso",
    ),
]


def cadastrar_produtos_confirmados(apps, schema_editor):
    alias = schema_editor.connection.alias
    Seguradora = apps.get_model("cotacoes", "Seguradora")
    Plano = apps.get_model("cotacoes", "Plano")
    TipoSeguro = apps.get_model("cotacoes", "TipoSeguro")
    tipo_saude = TipoSeguro.objects.using(alias).get(codigo="saude")

    seguradoras = {}
    for nome, produto, modalidade, acomodacao, coparticipacao, cobertura in PRODUTOS:
        if nome not in seguradoras:
            seguradoras[nome], _ = Seguradora.objects.using(alias).get_or_create(
                nome=nome,
                defaults={"cnpj": None},
            )
        Plano.objects.using(alias).get_or_create(
            seguradora=seguradoras[nome],
            nome=produto,
            defaults={
                "tipo_id": tipo_saude.pk,
                "tipo_seguro": "saude",
                "modalidade": modalidade,
                "acomodacao": acomodacao,
                "coparticipacao": coparticipacao,
                "cobertura_descricao": cobertura,
                "ativo": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("cotacoes", "0008_cotacao_quantidade_vidas_alter_seguradora_cnpj_and_more"),
    ]

    operations = [
        migrations.RunPython(cadastrar_produtos_confirmados, migrations.RunPython.noop),
    ]
