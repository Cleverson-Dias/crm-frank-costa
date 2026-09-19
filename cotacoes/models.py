"""
models.py
---------
Camada de persistência RELACIONAL (PostgreSQL) do CRM Frank Costa.

Aqui ficam apenas os dados "fixos" e estruturados: clientes e bens
segurados. As cotações (dados dinâmicos, schema variável por tipo de
seguro) NÃO entram aqui — elas vivem no MongoDB (ver nosql.py),
conforme RNF02 (persistência híbrida).
"""

from django.db import models


class Cliente(models.Model):
    """RF01 - Gestão de Clientes e Perfis (CRM)."""

    nome = models.CharField(max_length=150)
    cpf = models.CharField(max_length=14, unique=True)  # formato: 000.000.000-00
    data_nascimento = models.DateField()
    email = models.EmailField(blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    ativo = models.BooleanField(default=True)  # suporta "inativar" (RF01), não deleta
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} ({self.cpf})"


class Bem(models.Model):
    """
    Bem segurado vinculado a um cliente: veículo, imóvel ou objeto
    de seguro de vida (pessoa segurada / dependente).

    O detalhamento fino e variável de cada tipo (placa, ano, m²,
    histórico de saúde etc.) fica na cotação NoSQL — aqui guardamos só
    o essencial para o cadastro relacional funcionar como cadastro.
    """

    TIPO_CHOICES = [
        ("auto", "Automóvel"),
        ("residencial", "Residencial"),
        ("vida", "Vida"),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="bens")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    descricao = models.CharField(max_length=200)  # ex: "Honda Civic 2022" / "Apto 80m² - Ipiranga"
    valor_estimado = models.DecimalField(max_digits=12, decimal_places=2)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.descricao}"