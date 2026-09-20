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


class Seguradora(models.Model):
    """
    Parceira que a corretora representa (RF01 estendido).
    É pra QUEM, de fato, a apólice é vendida — sem isso não dá pra
    saber a origem real de uma comissão.
    """

    nome = models.CharField(max_length=150)
    cnpj = models.CharField(max_length=18, unique=True)  # formato: 00.000.000/0000-00
    contato_nome = models.CharField(max_length=150, blank=True)
    contato_email = models.EmailField(blank=True)
    contato_telefone = models.CharField(max_length=15, blank=True)
    comissao_padrao = models.DecimalField(
        max_digits=5, decimal_places=2, default=15.00,
        help_text="Percentual padrão de comissão, usado quando o Plano não define um próprio.",
    )
    ativa = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]
        verbose_name_plural = "Seguradoras"

    def __str__(self):
        return self.nome


class Plano(models.Model):
    """
    Produto específico de uma Seguradora para um tipo de seguro
    (ex: "Auto Completo" da Porto Seguro). Conecta o motor de cálculo
    a uma comissão real, em vez de uma taxa genérica fixa por tipo.
    """

    seguradora = models.ForeignKey(Seguradora, on_delete=models.CASCADE, related_name="planos")
    tipo_seguro = models.CharField(max_length=20, choices=Bem.TIPO_CHOICES)
    nome = models.CharField(max_length=150)
    cobertura_descricao = models.TextField(blank=True)
    percentual_comissao = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Deixe em branco para usar o percentual padrão da Seguradora.",
    )
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["seguradora__nome", "nome"]

    def __str__(self):
        return f"{self.nome} ({self.seguradora.nome})"

    def comissao_efetiva(self):
        """Retorna o percentual próprio do plano, ou o padrão da seguradora."""
        return self.percentual_comissao if self.percentual_comissao is not None else self.seguradora.comissao_padrao


class Apolice(models.Model):
    """
    O CONTRATO de fato — criado quando uma cotação (simulação, que
    vive no MongoDB) é aceita pelo cliente. É isso que transforma o
    dashboard num painel de negócio real (apólices fechadas), e não
    só de simulações.
    """

    STATUS_CHOICES = [
        ("ativa", "Ativa"),
        ("cancelada", "Cancelada"),
        ("vencida", "Vencida"),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="apolices")
    bem = models.ForeignKey(Bem, on_delete=models.PROTECT, related_name="apolices")
    seguradora = models.ForeignKey(Seguradora, on_delete=models.PROTECT, related_name="apolices")
    plano = models.ForeignKey(Plano, on_delete=models.SET_NULL, null=True, blank=True, related_name="apolices")

    cotacao_mongo_id = models.CharField(
        max_length=50, blank=True,
        help_text="ID do documento da simulação original no MongoDB, para rastreabilidade.",
    )
    numero_apolice = models.CharField(max_length=30, unique=True)
    valor_premio = models.DecimalField(max_digits=12, decimal_places=2)
    valor_franquia = models.DecimalField(max_digits=12, decimal_places=2)
    valor_comissao = models.DecimalField(max_digits=12, decimal_places=2)

    data_inicio = models.DateField()
    data_fim = models.DateField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="ativa")

    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name_plural = "Apólices"

    def __str__(self):
        return f"{self.numero_apolice} - {self.cliente.nome}"