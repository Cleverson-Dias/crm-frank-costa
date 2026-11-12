"""
models.py
---------
Camada relacional (PostgreSQL) do CRM Frank Costa.

Cadastros comerciais, acompanhamento de cotações, apólices, sinistros e
recebimentos ficam aqui. O documento detalhado da simulação também é
mantido no MongoDB para compatibilidade com os perfis variáveis por ramo.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings


TIPOS_SEGURO_ATIVOS = [
    ("auto", "Automóvel"),
    ("vida", "Vida"),
    ("saude", "Saúde"),
    ("residencial", "Residencial"),
    ("empresarial", "Empresarial"),
    ("condominio", "Condomínio"),
    ("responsabilidade_civil", "Responsabilidade Civil"),
    ("garantia", "Garantia"),
    ("viagem", "Viagem"),
    ("frota", "Frota"),
]


class TipoSeguro(models.Model):
    codigo = models.SlugField(max_length=40, unique=True)
    nome = models.CharField(max_length=100, unique=True)
    ativo = models.BooleanField(default=True)
    observacoes = models.TextField(blank=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Tipo de seguro"
        verbose_name_plural = "Tipos de seguro"

    def __str__(self):
        return self.nome


class Cliente(models.Model):
    """RF01 - Gestão de Clientes e Perfis (CRM)."""

    TIPO_PESSOA_CHOICES = [
        ("pf", "Pessoa Física"),
        ("pj", "Pessoa Jurídica"),
    ]

    tipo_pessoa = models.CharField(
        max_length=2,
        choices=TIPO_PESSOA_CHOICES,
        default="pf",
    )
    nome = models.CharField(max_length=150)
    cpf = models.CharField(max_length=14, blank=True, null=True)
    cnpj = models.CharField(max_length=18, blank=True, null=True)
    data_nascimento = models.DateField(blank=True, null=True)
    email = models.EmailField(blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    endereco = models.CharField(max_length=255, blank=True)
    cidade = models.CharField(max_length=100, blank=True)
    estado = models.CharField(max_length=2, blank=True)
    cep = models.CharField(max_length=9, blank=True)
    profissao = models.CharField(max_length=150, blank=True)
    corretor_responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clientes_responsaveis",
    )
    observacoes = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)  # suporta "inativar" (RF01), não deleta
    dados_sinteticos = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["cpf"],
                condition=models.Q(cpf__isnull=False),
                name="uq_cliente_cpf_preenchido",
            ),
            models.UniqueConstraint(
                fields=["cnpj"],
                condition=models.Q(cnpj__isnull=False),
                name="uq_cliente_cnpj_preenchido",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(tipo_pessoa="pf", cpf__isnull=False, cnpj__isnull=True)
                    | models.Q(tipo_pessoa="pj", cpf__isnull=True, cnpj__isnull=False)
                ),
                name="ck_cliente_documento_por_pessoa",
            ),
        ]

    def clean(self):
        super().clean()
        if self.tipo_pessoa == "pf" and not self.cpf:
            raise ValidationError({"cpf": "Informe o CPF da pessoa física."})
        if self.tipo_pessoa == "pj" and not self.cnpj:
            raise ValidationError({"cnpj": "Informe o CNPJ da pessoa jurídica."})
        if self.tipo_pessoa == "pf" and self.cnpj:
            raise ValidationError({"cnpj": "Pessoa física não deve ter CNPJ."})
        if self.tipo_pessoa == "pj" and self.cpf:
            raise ValidationError({"cpf": "Pessoa jurídica não deve ter CPF."})

    def __str__(self):
        identificador = self.cnpj if self.tipo_pessoa == "pj" else self.cpf
        return f"{self.nome} ({identificador or 'sem documento'})"


class Bem(models.Model):
    """
    Bem ou referência segurada vinculada a um cliente: veículo, capital
    de vida, saúde ou outros ramos de seguro.

    Os detalhes variáveis de cada ramo ficam na cotação NoSQL.
    """

    TIPO_CHOICES = TIPOS_SEGURO_ATIVOS

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="bens")
    tipo = models.CharField(max_length=40, choices=TIPO_CHOICES)
    descricao = models.CharField(max_length=200)
    valor_estimado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Bem"
        verbose_name_plural = "Bens"

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.descricao}"


class Seguradora(models.Model):
    """
    Parceira que a corretora representa (RF01 estendido).
    É pra QUEM, de fato, a apólice é vendida — sem isso não dá pra
    saber a origem real de uma comissão.
    """

    nome = models.CharField(max_length=150)
    cnpj = models.CharField(max_length=18, null=True, blank=True)
    contato_nome = models.CharField(max_length=150, blank=True)
    contato_email = models.EmailField(blank=True)
    contato_telefone = models.CharField(max_length=15, blank=True)
    codigo_susep = models.CharField(max_length=30, blank=True)
    site = models.URLField(blank=True)
    comissao_padrao = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Percentual padrão cadastrado; deixe em branco quando não houver informação confirmada.",
    )
    ativa = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]
        verbose_name_plural = "Seguradoras"
        constraints = [
            models.UniqueConstraint(
                fields=["cnpj"],
                condition=models.Q(cnpj__isnull=False),
                name="uq_seguradora_cnpj_preenchido",
            ),
        ]

    def __str__(self):
        return self.nome


class Plano(models.Model):
    """
    Produto específico de uma Seguradora para um tipo de seguro
    (ex: "Auto Completo" da Porto Seguro). Conecta o motor de cálculo
    a uma comissão real, em vez de uma taxa genérica fixa por tipo.
    """

    seguradora = models.ForeignKey(Seguradora, on_delete=models.CASCADE, related_name="planos")
    tipo = models.ForeignKey(
        TipoSeguro,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="planos",
    )
    tipo_seguro = models.CharField(max_length=40, choices=Bem.TIPO_CHOICES)
    nome = models.CharField(max_length=150)
    cobertura_descricao = models.TextField(blank=True)
    SEGMENTACAO_ASSISTENCIAL_CHOICES = [
        ("ambulatorial", "Ambulatorial"),
        ("hospitalar", "Hospitalar sem obstetrícia"),
        ("hospitalar_obstetricia", "Hospitalar com obstetrícia"),
        ("odontologico", "Exclusivamente odontológico"),
        ("referencia", "Referência"),
        ("ambulatorial_odontologico", "Ambulatorial + odontológico"),
        ("ambulatorial_hospitalar", "Ambulatorial + hospitalar sem obstetrícia"),
        ("ambulatorial_hospitalar_obstetricia", "Ambulatorial + hospitalar com obstetrícia"),
        ("hospitalar_obstetricia_odontologico", "Hospitalar com obstetrícia + odontológico"),
        ("hospitalar_odontologico", "Hospitalar sem obstetrícia + odontológico"),
        ("ambulatorial_hospitalar_odontologico", "Ambulatorial + hospitalar sem obstetrícia + odontológico"),
        ("ambulatorial_hospitalar_obstetricia_odontologico", "Ambulatorial + hospitalar com obstetrícia + odontológico"),
    ]
    segmentacao_assistencial = models.CharField(
        max_length=64,
        choices=SEGMENTACAO_ASSISTENCIAL_CHOICES,
        blank=True,
        default="",
        help_text="Segmentação assistencial declarada no produto/contrato.",
    )
    percentual_comissao = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Percentual contratado; deixe em branco quando ainda não for conhecido.",
    )
    ativo = models.BooleanField(default=True)
    modalidade = models.CharField(max_length=100, blank=True)
    abrangencia = models.CharField(max_length=150, blank=True)
    acomodacao = models.CharField(max_length=80, blank=True)
    coparticipacao = models.CharField(max_length=80, blank=True)
    valor_referencia = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Apenas referência comercial; não representa preço final.",
    )
    observacoes = models.TextField(blank=True)

    class Meta:
        ordering = ["seguradora__nome", "nome"]

    def __str__(self):
        return f"{self.nome} ({self.seguradora.nome})"

    def comissao_efetiva(self):
        """Retorna o percentual cadastrado, ou None quando desconhecido."""
        return self.percentual_comissao if self.percentual_comissao is not None else self.seguradora.comissao_padrao

    def save(self, *args, **kwargs):
        if not self.tipo_id:
            self.tipo = TipoSeguro.objects.get(codigo=self.tipo_seguro)
        else:
            self.tipo_seguro = self.tipo.codigo
        super().save(*args, **kwargs)


class Cotacao(models.Model):
    STATUS_CHOICES = [
        ("rascunho", "Rascunho"),
        ("enviada", "Enviada à seguradora"),
        ("aguardando", "Aguardando retorno"),
        ("aprovada", "Aprovada"),
        ("convertida", "Convertida em apólice"),
        ("recusada", "Recusada"),
        ("expirada", "Expirada"),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="cotacoes")
    tipo_seguro = models.ForeignKey(TipoSeguro, on_delete=models.PROTECT, related_name="cotacoes")
    seguradora = models.ForeignKey(
        Seguradora,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cotacoes",
    )
    plano = models.ForeignKey(
        Plano,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cotacoes",
    )
    corretor_responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cotacoes_responsaveis",
    )
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="rascunho")
    valor_estimado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    valor_final = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    valor_franquia = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    quantidade_vidas = models.PositiveIntegerField(null=True, blank=True)
    percentual_comissao = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Cópia da comissão efetiva do plano no momento da cotação.",
    )
    data_cotacao = models.DateField(auto_now_add=True)
    validade = models.DateField(null=True, blank=True)
    dados_especificos = models.JSONField(default=dict, blank=True)
    observacoes = models.TextField(blank=True)
    cotacao_mongo_id = models.CharField(max_length=50, null=True, blank=True, unique=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_cotacao", "-criado_em"]
        verbose_name = "Cotação"
        verbose_name_plural = "Cotações"

    def clean(self):
        super().clean()
        errors = {}
        if self.plano_id:
            if self.seguradora_id and self.plano.seguradora_id != self.seguradora_id:
                errors["plano"] = "O plano deve pertencer à seguradora selecionada."
            if self.tipo_seguro_id and self.plano.tipo_seguro != self.tipo_seguro.codigo:
                errors["plano"] = "O plano deve pertencer ao ramo selecionado."
            if not self.seguradora_id:
                self.seguradora = self.plano.seguradora
            if not self.tipo_seguro_id:
                self.tipo_seguro = self.plano.tipo
        if self.seguradora_id and not self.seguradora.ativa:
            errors["seguradora"] = "Selecione uma seguradora ativa."
        if self.plano_id and not self.plano.ativo:
            errors["plano"] = "Selecione um plano ativo."
        if self.cliente_id and self.tipo_seguro_id:
            if self.cliente.tipo_pessoa == "pj" and self.tipo_seguro.codigo == "saude":
                if self.quantidade_vidas is None or self.quantidade_vidas < 1:
                    errors["quantidade_vidas"] = "Informe a quantidade de vidas do contrato empresarial."
                elif self.seguradora_id and "bradesco" in self.seguradora.nome.casefold():
                    if self.quantidade_vidas < 2:
                        errors["quantidade_vidas"] = (
                            "Bradesco Saúde não aceita cotação individual; informe pelo menos duas vidas."
                        )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.get_status_display()} - {self.cliente.nome} - {self.tipo_seguro}"


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
    cotacao = models.OneToOneField(
        Cotacao,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="apolice",
    )

    cotacao_mongo_id = models.CharField(
        max_length=50, blank=True,
        help_text="ID do documento da simulação original no MongoDB, para rastreabilidade.",
    )
    numero_apolice = models.CharField(max_length=30, unique=True)
    valor_premio = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    valor_franquia = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    valor_comissao = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    data_inicio = models.DateField()
    data_fim = models.DateField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="ativa")

    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name_plural = "Apólices"

    def __str__(self):
        return f"{self.numero_apolice} - {self.cliente.nome}"


class Sinistro(models.Model):
    STATUS_CHOICES = [
        ("aberto", "Aberto"),
        ("em_analise", "Em análise"),
        ("aguardando_documentos", "Aguardando documentos"),
        ("aprovado", "Aprovado"),
        ("recusado", "Recusado"),
        ("encerrado", "Encerrado"),
    ]

    apolice = models.ForeignKey(Apolice, on_delete=models.PROTECT, related_name="sinistros")
    numero = models.CharField(max_length=40, unique=True, null=True, blank=True)
    data_ocorrencia = models.DateField()
    data_abertura = models.DateField(auto_now_add=True)
    descricao = models.TextField()
    valor_reclamado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    valor_pago = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default="aberto")
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_abertura", "-criado_em"]

    def clean(self):
        super().clean()
        if self.apolice_id and self.data_ocorrencia and self.data_ocorrencia < self.apolice.data_inicio:
            raise ValidationError({"data_ocorrencia": "A ocorrência não pode anteceder o início da apólice."})
        if self.valor_pago is not None and self.valor_reclamado is not None:
            if self.valor_pago > self.valor_reclamado:
                raise ValidationError({"valor_pago": "O valor pago não pode superar o valor reclamado."})

    def __str__(self):
        return self.numero or f"Sinistro {self.pk or 'novo'} - {self.apolice.numero_apolice}"


class RecebimentoComissao(models.Model):
    STATUS_CHOICES = [
        ("previsto", "Previsto"),
        ("recebido", "Recebido"),
        ("atrasado", "Atrasado"),
        ("cancelado", "Cancelado"),
    ]

    apolice = models.ForeignKey(
        Apolice,
        on_delete=models.PROTECT,
        related_name="recebimentos_comissao",
    )
    competencia = models.DateField()
    valor_previsto = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    valor_recebido = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    data_prevista = models.DateField(null=True, blank=True)
    data_recebimento = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="previsto")
    observacoes = models.TextField(blank=True)

    class Meta:
        ordering = ["-competencia", "apolice__numero_apolice"]
        constraints = [
            models.UniqueConstraint(
                fields=["apolice", "competencia"],
                name="uq_recebimento_comissao_apolice_competencia",
            ),
        ]
        verbose_name = "Recebimento de comissão"
        verbose_name_plural = "Recebimentos de comissão"

    def clean(self):
        super().clean()
        if self.status == "recebido" and self.valor_recebido is None:
            raise ValidationError({"valor_recebido": "Informe o valor efetivamente recebido."})
        if self.status == "recebido" and not self.data_recebimento:
            raise ValidationError({"data_recebimento": "Informe a data do recebimento."})

    def __str__(self):
        return f"{self.apolice.numero_apolice} - {self.competencia:%m/%Y}"


class RenovacaoApolice(models.Model):
    """Resultado da tentativa de renovação de uma apólice vencida."""

    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("renovada", "Renovada"),
        ("nao_renovada", "Não renovada"),
    ]

    apolice = models.ForeignKey(
        Apolice, on_delete=models.CASCADE, related_name="historico_renovacoes"
    )
    apolice_renovada = models.ForeignKey(
        Apolice, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="renovacoes_resultantes",
    )
    data_vencimento = models.DateField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="pendente")
    data_decisao = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-data_vencimento"]
        constraints = [
            models.UniqueConstraint(
                fields=["apolice", "data_vencimento"],
                name="uq_renovacao_apolice_vencimento",
            ),
        ]

    def clean(self):
        if self.status == "renovada" and not self.apolice_renovada_id:
            raise ValidationError({
                "apolice_renovada": "Informe a apólice emitida para registrar a renovação."
            })
        if self.status != "renovada" and self.apolice_renovada_id:
            raise ValidationError({
                "apolice_renovada": "Somente renovações concluídas podem apontar para uma nova apólice."
            })
        if self.apolice_id and self.apolice_renovada_id:
            if self.apolice_id == self.apolice_renovada_id:
                raise ValidationError({
                    "apolice_renovada": "A nova apólice deve ser diferente da apólice original."
                })
            origem = self.apolice
            nova = self.apolice_renovada
            if origem.cliente_id != nova.cliente_id or origem.bem.tipo != nova.bem.tipo:
                raise ValidationError({
                    "apolice_renovada": "A renovação deve pertencer ao mesmo cliente e ramo da apólice original."
                })

    def __str__(self):
        return f"Renovação de {self.apolice.numero_apolice} ({self.get_status_display()})"


class ComissaoMensalDemonstracao(models.Model):
    """Cenário acadêmico de comissões mensais fictícias para o painel."""

    mes_referencia = models.DateField()
    tipo_seguro = models.CharField(max_length=40, choices=TIPOS_SEGURO_ATIVOS)
    comissao_bruta = models.DecimalField(max_digits=12, decimal_places=2)
    percentual_liquido_estimado = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=75,
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["mes_referencia", "tipo_seguro"]
        constraints = [
            models.UniqueConstraint(
                fields=["mes_referencia", "tipo_seguro"],
                name="uq_comissao_demo_mes_ramo",
            ),
        ]
        verbose_name = "Comissão mensal demonstrativa"
        verbose_name_plural = "Comissões mensais demonstrativas"

    @property
    def comissao_liquida_estimada(self):
        return self.comissao_bruta * self.percentual_liquido_estimado / 100

    def __str__(self):
        return f"{self.mes_referencia:%m/%Y} - {self.get_tipo_seguro_display()}"
