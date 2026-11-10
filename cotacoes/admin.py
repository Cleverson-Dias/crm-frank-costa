"""
admin.py
--------
Registra os models no Django Admin — a interface administrativa nativa
do Django. Usamos ela para o back-office de Seguradoras/Planos/Apólices
(dados mais "operacionais", gerenciados por um gerente) em vez de
escrever telas customizadas do zero para tudo, focando o tempo de
desenvolvimento no fluxo principal do CRM (cotação → cliente).
"""

from django.contrib import admin
from .models import (
    Apolice,
    Bem,
    Cliente,
    ComissaoMensalDemonstracao,
    Cotacao,
    Plano,
    RecebimentoComissao,
    RenovacaoApolice,
    Seguradora,
    Sinistro,
    TipoSeguro,
)


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo_pessoa", "cpf", "cnpj", "email", "telefone", "corretor_responsavel", "ativo")
    search_fields = ("nome", "cpf", "cnpj", "email", "telefone")
    list_filter = ("tipo_pessoa", "ativo", "dados_sinteticos", "estado")


@admin.register(TipoSeguro)
class TipoSeguroAdmin(admin.ModelAdmin):
    list_display = ("nome", "codigo", "ativo")
    list_filter = ("ativo",)
    search_fields = ("nome", "codigo")


@admin.register(Bem)
class BemAdmin(admin.ModelAdmin):
    list_display = ("descricao", "tipo", "cliente", "valor_estimado", "ativo")
    list_filter = ("tipo", "ativo")
    search_fields = ("descricao", "cliente__nome")


@admin.register(Seguradora)
class SeguradoraAdmin(admin.ModelAdmin):
    list_display = ("nome", "cnpj", "comissao_padrao", "ativa")
    search_fields = ("nome", "cnpj")
    list_filter = ("ativa",)


@admin.register(Plano)
class PlanoAdmin(admin.ModelAdmin):
    list_display = ("nome", "seguradora", "tipo", "tipo_seguro", "comissao_efetiva", "ativo")
    list_filter = ("tipo", "tipo_seguro", "ativo", "seguradora")
    search_fields = ("nome", "seguradora__nome")


@admin.register(Cotacao)
class CotacaoAdmin(admin.ModelAdmin):
    list_display = ("cliente", "tipo_seguro", "seguradora", "plano", "quantidade_vidas", "status", "data_cotacao", "validade")
    list_filter = ("status", "tipo_seguro", "seguradora", "data_cotacao")
    search_fields = ("cliente__nome", "cliente__cpf", "cliente__cnpj", "cotacao_mongo_id")
    date_hierarchy = "data_cotacao"


@admin.register(Apolice)
class ApoliceAdmin(admin.ModelAdmin):
    list_display = ("numero_apolice", "cliente", "seguradora", "valor_premio", "valor_comissao", "status", "data_inicio", "data_fim")
    list_filter = ("status", "seguradora")
    search_fields = ("numero_apolice", "cliente__nome")
    date_hierarchy = "data_inicio"


@admin.register(RenovacaoApolice)
class RenovacaoApoliceAdmin(admin.ModelAdmin):
    list_display = ("apolice", "data_vencimento", "status", "apolice_renovada", "data_decisao")
    list_filter = ("status", "data_vencimento")
    search_fields = ("apolice__numero_apolice", "apolice__cliente__nome")
    date_hierarchy = "data_vencimento"


@admin.register(Sinistro)
class SinistroAdmin(admin.ModelAdmin):
    list_display = ("numero", "apolice", "data_ocorrencia", "status", "valor_reclamado", "valor_pago")
    list_filter = ("status", "data_ocorrencia")
    search_fields = ("numero", "apolice__numero_apolice", "apolice__cliente__nome")
    date_hierarchy = "data_ocorrencia"


@admin.register(RecebimentoComissao)
class RecebimentoComissaoAdmin(admin.ModelAdmin):
    list_display = ("apolice", "competencia", "valor_previsto", "valor_recebido", "status", "data_prevista", "data_recebimento")
    list_filter = ("status", "competencia")
    search_fields = ("apolice__numero_apolice", "apolice__cliente__nome")
    date_hierarchy = "competencia"


@admin.register(ComissaoMensalDemonstracao)
class ComissaoMensalDemonstracaoAdmin(admin.ModelAdmin):
    list_display = ("mes_referencia", "tipo_seguro", "comissao_bruta", "percentual_liquido_estimado")
    list_filter = ("tipo_seguro", "mes_referencia")
    date_hierarchy = "mes_referencia"