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
from .models import Cliente, Bem, Seguradora, Plano, Apolice


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nome", "cpf", "email", "telefone", "ativo")
    search_fields = ("nome", "cpf")
    list_filter = ("ativo",)


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
    list_display = ("nome", "seguradora", "tipo_seguro", "comissao_efetiva", "ativo")
    list_filter = ("tipo_seguro", "ativo", "seguradora")
    search_fields = ("nome", "seguradora__nome")


@admin.register(Apolice)
class ApoliceAdmin(admin.ModelAdmin):
    list_display = ("numero_apolice", "cliente", "seguradora", "valor_premio", "valor_comissao", "status", "data_inicio", "data_fim")
    list_filter = ("status", "seguradora")
    search_fields = ("numero_apolice", "cliente__nome")
    date_hierarchy = "data_inicio"