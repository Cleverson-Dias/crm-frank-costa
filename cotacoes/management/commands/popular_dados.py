import random
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction

from cotacoes import motor_ia, nosql
from cotacoes.models import (
    Apolice,
    Bem,
    Cliente,
    Plano,
    RenovacaoApolice,
    Seguradora,
    TIPOS_SEGURO_ATIVOS,
)
from cotacoes.utils import somente_digitos


NOMES = [
    "Ana", "Bruno", "Carla", "Daniel", "Eduarda", "Felipe", "Gabriela",
    "Henrique", "Isabela", "Joao", "Larissa", "Marcelo", "Natalia",
    "Otavio", "Patricia", "Rafael", "Sabrina", "Thiago", "Vanessa", "Wagner",
    "Camila", "Diego", "Fernanda", "Gustavo", "Juliana", "Leonardo",
    "Mariana", "Nicolas", "Priscila", "Rodrigo", "Tatiane", "Victor",
]
SOBRENOMES = [
    "Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira",
    "Alves", "Pereira", "Lima", "Gomes", "Costa", "Martins", "Araujo",
    "Barbosa", "Ribeiro", "Carvalho", "Teixeira", "Melo", "Rocha", "Dias",
]

# Mix demonstrativo, não representa uma distribuição informada pela corretora.
DISTRIBUICAO_ATIVOS = {"auto": 30, "vida": 10, "saude": 10}
COMISSAO_ANUAL_POR_RAMO = {"auto": 500.00, "vida": 2500.00, "saude": 5600.00}
COTACOES_ADICIONAIS = 50


def cpf_fake(usados):
    while True:
        cpf = "".join(str(random.randint(0, 9)) for _ in range(11))
        if cpf not in usados:
            usados.add(cpf)
            return cpf


class Command(BaseCommand):
    help = "Gera 50 clientes, 50 apólices ativas e histórico sintético de cotações e renovações."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limpar",
            action="store_true",
            help="Remove cotações do MongoDB e clientes/apólices do PostgreSQL antes de popular.",
        )

    def handle(self, *args, **options):
        random.seed(2026)
        if options["limpar"]:
            self._limpar_dados_anteriores()

        self._criar_seguradoras_e_planos()
        cpfs_usados = set(Cliente.objects.values_list("cpf", flat=True))
        ramos_ativos = [
            ramo
            for ramo, quantidade in DISTRIBUICAO_ATIVOS.items()
            for _ in range(quantidade)
        ]
        random.shuffle(ramos_ativos)

        clientes_e_apolices = []
        registros_cotacoes = []
        apolices_ativas_criadas = 0

        for ramo in ramos_ativos:
            hoje = date.today()
            nome = f"{random.choice(NOMES)} {random.choice(SOBRENOMES)}"
            idade = random.randint(25, 65)
            try:
                nascimento = hoje.replace(year=hoje.year - idade)
            except ValueError:
                nascimento = hoje.replace(year=hoje.year - idade, day=28)

            with transaction.atomic():
                cliente = Cliente.objects.create(
                    nome=nome,
                    cpf=cpf_fake(cpfs_usados),
                    data_nascimento=nascimento,
                    email=f"{nome.lower().replace(' ', '.')}@exemplo.com",
                    telefone=somente_digitos(f"119{random.randint(10000000, 99999999)}"),
                    dados_sinteticos=True,
                )
                plano = self._plano_ativo(ramo)
                perfil = self._perfil_ativo(ramo, plano)
                bem = Bem.objects.create(
                    cliente=cliente,
                    tipo=ramo,
                    descricao=self._descricao_bem(nome, ramo),
                    valor_estimado=Decimal(str(round(perfil["valor_bem"], 2))),
                )
                parecer = motor_ia.avaliar_elegibilidade(perfil)
                fator_risco = motor_ia.fator_risco_por_perfil(perfil, parecer)
                resultado = motor_ia.calcular_proposta(
                    ramo, perfil["valor_bem"], fator_risco
                )
                cotacao_id = nosql.salvar_cotacao(
                    cliente_id=cliente.id,
                    bem_id=bem.id,
                    tipo_seguro=ramo,
                    dados={**perfil, "origem_dados": "demonstracao_sintetica"},
                    resultado_calculo=resultado,
                    parecer_ia=parecer,
                )
                apolice = self._criar_apolice(
                    cliente, bem, plano, cotacao_id, resultado, hoje
                )
                apolices_ativas_criadas += 1
                clientes_e_apolices.append((cliente, apolice, ramo))
                registros_cotacoes.append(self._registro_higienizacao(
                    cliente, ramo, perfil, parecer, resultado
                ))

        ramos_extras = [
            ramo
            for ramo, quantidade in DISTRIBUICAO_ATIVOS.items()
            for _ in range(quantidade)
        ]
        random.shuffle(ramos_extras)
        for indice in range(COTACOES_ADICIONAIS):
            cliente, _, _ = clientes_e_apolices[indice]
            ramo = ramos_extras[indice]
            perfil = self._perfil_cotacao_adicional(ramo, indice)
            with transaction.atomic():
                bem = Bem.objects.create(
                    cliente=cliente,
                    tipo=ramo,
                    descricao=self._descricao_bem(cliente.nome, ramo),
                    valor_estimado=Decimal(str(round(perfil["valor_bem"], 2))),
                )
                parecer = motor_ia.avaliar_elegibilidade(perfil)
                fator_risco = motor_ia.fator_risco_por_perfil(perfil, parecer)
                resultado = motor_ia.calcular_proposta(
                    ramo, perfil["valor_bem"], fator_risco
                )
                nosql.salvar_cotacao(
                    cliente_id=cliente.id,
                    bem_id=bem.id,
                    tipo_seguro=ramo,
                    dados={**perfil, "origem_dados": "demonstracao_sintetica"},
                    resultado_calculo=resultado,
                    parecer_ia=parecer,
                )
                registros_cotacoes.append(self._registro_higienizacao(
                    cliente, ramo, perfil, parecer, resultado
                ))

        renovacoes_criadas = self._criar_historico_renovacoes(clientes_e_apolices)
        self._demonstrar_higienizacao_rf07(registros_cotacoes)

        comissao_anual = sum(
            Apolice.objects.filter(status="ativa").values_list("valor_comissao", flat=True)
        )
        self.stdout.write(self.style.SUCCESS(
            "\nBase demonstrativa sintética concluída.\n"
            f"  Clientes ativos criados:       {len(clientes_e_apolices)}\n"
            f"  Apólices ativas criadas:       {apolices_ativas_criadas}\n"
            f"  Cotações criadas:              {len(registros_cotacoes)}\n"
            f"  Histórico de renovações:       {renovacoes_criadas}\n"
            f"  Comissão anual da carteira:    R$ {comissao_anual:,.2f}\n"
        ))

    def _perfil_ativo(self, ramo, plano):
        comissao = float(COMISSAO_ANUAL_POR_RAMO[ramo])
        percentual = float(plano.comissao_efetiva())
        premio = comissao / (percentual / 100)
        if ramo == "auto":
            valor_bem = premio / motor_ia.TAXA_BASE[ramo]
            return {
                "tipo_seguro": ramo,
                "idade": 40,
                "valor_bem": valor_bem,
                "uso_veiculo": "passeio",
            }
        if ramo == "vida":
            capital = premio / motor_ia.TAXA_BASE[ramo]
            return {
                "tipo_seguro": ramo,
                "idade": 40,
                "valor_bem": capital,
                "capital_segurado": capital,
                "dps_completa": True,
                "dps_compativel": True,
            }
        return {
            "tipo_seguro": ramo,
            "idade": 40,
            "valor_bem": premio,
            "mensalidade_mensal": premio / 12,
            "operacao": "atendimento",
            "segmentacao_contratada": "referencia",
            "tipo_atendimento": "demais",
            "dias_contrato": 365,
        }

    def _perfil_cotacao_adicional(self, ramo, indice):
        if ramo == "auto":
            valor = random.uniform(25_000, 180_000)
            return {
                "tipo_seguro": ramo,
                "idade": 20 + indice % 35,
                "valor_bem": valor,
                "uso_veiculo": "passeio",
            }
        if ramo == "vida":
            capital = random.uniform(80_000, 450_000)
            return {
                "tipo_seguro": ramo,
                "idade": 25 + indice % 45,
                "valor_bem": capital,
                "capital_segurado": capital,
                "dps_completa": True,
                "dps_compativel": True,
                "tabagismo": indice % 2 == 0,
            }
        mensalidade = random.uniform(450, 1800)
        return {
            "tipo_seguro": ramo,
            "idade": 22 + indice % 50,
            "valor_bem": mensalidade * 12,
            "mensalidade_mensal": mensalidade,
            "operacao": "atendimento",
            "segmentacao_contratada": "referencia",
            "tipo_atendimento": "demais",
            "dias_contrato": 30 if indice % 2 == 0 else 365,
        }

    def _criar_apolice(self, cliente, bem, plano, cotacao_id, resultado, hoje):
        premio = Decimal(str(resultado["premio"]))
        comissao = Decimal(str(round(
            float(premio) * float(plano.comissao_efetiva()) / 100, 2
        )))
        data_inicio = hoje - timedelta(days=random.randint(20, 200))
        return Apolice.objects.create(
            cliente=cliente,
            bem=bem,
            seguradora=plano.seguradora,
            plano=plano,
            cotacao_mongo_id=str(cotacao_id),
            numero_apolice=self._numero_apolice_unico(hoje.year),
            valor_premio=premio,
            valor_franquia=Decimal(str(resultado["franquia"])),
            valor_comissao=comissao,
            data_inicio=data_inicio,
            data_fim=data_inicio + timedelta(days=365),
            status="ativa",
        )

    def _criar_historico_renovacoes(self, clientes_e_apolices):
        hoje = date.today()
        renovacoes_criadas = 0
        for indice, (cliente, apolice_atual, ramo_atual) in enumerate(clientes_e_apolices[:25]):
            data_vencimento = hoje - timedelta(days=30 + indice * 12)
            renovada = indice < 20
            ramo_anterior = ramo_atual if renovada else next(
                ramo for ramo, _ in TIPOS_SEGURO_ATIVOS if ramo != ramo_atual
            )
            plano_anterior = self._plano_ativo(ramo_anterior)
            bem_anterior = apolice_atual.bem if renovada else Bem.objects.create(
                cliente=cliente,
                tipo=ramo_anterior,
                descricao=self._descricao_bem(cliente.nome, ramo_anterior),
                valor_estimado=apolice_atual.valor_premio,
                ativo=False,
            )
            apolice_anterior = Apolice.objects.create(
                cliente=cliente,
                bem=bem_anterior,
                seguradora=plano_anterior.seguradora,
                plano=plano_anterior,
                numero_apolice=self._numero_apolice_unico(data_vencimento.year),
                valor_premio=apolice_atual.valor_premio,
                valor_franquia=apolice_atual.valor_franquia,
                valor_comissao=apolice_atual.valor_comissao,
                data_inicio=data_vencimento - timedelta(days=365),
                data_fim=data_vencimento,
                status="vencida",
            )
            RenovacaoApolice.objects.create(
                apolice=apolice_anterior,
                apolice_renovada=apolice_atual if renovada else None,
                data_vencimento=data_vencimento,
                data_decisao=data_vencimento + timedelta(days=1),
                status="renovada" if renovada else "nao_renovada",
            )
            if renovada:
                apolice_atual.data_inicio = data_vencimento + timedelta(days=1)
                apolice_atual.data_fim = apolice_atual.data_inicio + timedelta(days=365)
                apolice_atual.save(update_fields=["data_inicio", "data_fim"])
            renovacoes_criadas += 1
        return renovacoes_criadas

    def _plano_ativo(self, ramo):
        planos = list(Plano.objects.filter(
            tipo_seguro=ramo, ativo=True, seguradora__ativa=True
        ).select_related("seguradora"))
        if not planos:
            raise RuntimeError(f"Nenhum plano ativo cadastrado para o ramo '{ramo}'.")
        return random.choice(planos)

    def _numero_apolice_unico(self, ano):
        while True:
            numero = f"AP-{ano}-{random.randint(100000, 999999)}"
            if not Apolice.objects.filter(numero_apolice=numero).exists():
                return numero

    def _descricao_bem(self, nome, ramo):
        descricoes = {
            "auto": f"{nome} - veículo de passeio",
            "vida": f"{nome} - capital segurado",
            "saude": f"{nome} - plano de saúde",
        }
        return descricoes[ramo]

    def _registro_higienizacao(self, cliente, ramo, perfil, parecer, resultado):
        return {
            "cliente": cliente.nome,
            "cpf": cliente.cpf,
            "tipo_seguro": ramo,
            "valor_bem": round(perfil["valor_bem"], 2),
            "idade": perfil["idade"],
            "parecer": parecer["status"],
            "premio": resultado["premio"],
        }

    def _limpar_dados_anteriores(self):
        self.stdout.write(self.style.WARNING("Removendo somente registros sintéticos identificados..."))
        resultado = nosql.get_db().cotacoes.delete_many(
            {"dados.origem_dados": "demonstracao_sintetica"}
        )
        self.stdout.write(f"  MongoDB: {resultado.deleted_count} cotações removidas.")
        clientes_sinteticos = Cliente.objects.filter(dados_sinteticos=True)
        ids_clientes = list(clientes_sinteticos.values_list("id", flat=True))
        qtd_clientes = len(ids_clientes)
        Apolice.objects.filter(cliente_id__in=ids_clientes).delete()
        clientes_sinteticos.delete()
        self.stdout.write(
            f"  PostgreSQL: apólices e {qtd_clientes} clientes sintéticos removidos; "
            "dados não identificados como sintéticos, seguradoras e planos foram mantidos.\n"
        )

    def _criar_seguradoras_e_planos(self):
        dados_seguradoras = [
            {"nome": "Allianz", "cnpj": "06.193.425/0001-33", "comissao_padrao": Decimal("12.00")},
            {"nome": "Azul Seguros", "cnpj": "04.598.082/0001-13", "comissao_padrao": Decimal("12.00")},
            {"nome": "Bradesco Seguros", "cnpj": "33.055.146/0001-93", "comissao_padrao": Decimal("10.00")},
            {"nome": "Porto Seguro", "cnpj": "61.198.164/0001-60", "comissao_padrao": Decimal("15.00")},
            {"nome": "SulAmérica", "cnpj": "01.938.018/0001-56", "comissao_padrao": Decimal("12.50")},
            {"nome": "Tokio Marine Seguradora", "cnpj": "33.164.021/0001-00", "comissao_padrao": Decimal("18.00")},
        ]
        for dados in dados_seguradoras:
            seguradora, _ = Seguradora.objects.get_or_create(
                cnpj=dados["cnpj"],
                defaults={
                    "nome": dados["nome"],
                    "comissao_padrao": dados["comissao_padrao"],
                },
            )
            for tipo, label in TIPOS_SEGURO_ATIVOS:
                Plano.objects.get_or_create(
                    seguradora=seguradora,
                    tipo_seguro=tipo,
                    nome=f"{label} Completo {seguradora.nome.split()[0]}",
                    defaults={
                        "cobertura_descricao": f"Cobertura de demonstração de {label.lower()}.",
                    },
                )

    def _demonstrar_higienizacao_rf07(self, registros):
        df = pd.DataFrame(registros)
        self.stdout.write(self.style.WARNING("\n--- RF07: Higienização de Dados (Pandas) ---"))
        self.stdout.write(f"Linhas brutas: {len(df)}")
        antes = len(df)
        df = df.drop_duplicates(subset=["cpf", "tipo_seguro", "valor_bem"])
        df = df.dropna(subset=["cpf", "valor_bem", "parecer"])
        self.stdout.write(
            f"Linhas após remover duplicatas/nulos: {len(df)} "
            f"(removidas: {antes - len(df)})"
        )
        self.stdout.write("\nDistribuição de pareceres:")
        self.stdout.write(str(df["parecer"].value_counts()))
        self.stdout.write("\nEstatísticas de valor informado (R$):")
        self.stdout.write(f"  Média:   R$ {df['valor_bem'].mean():,.2f}")
        self.stdout.write(f"  Mediana: R$ {df['valor_bem'].median():,.2f}")
        if not df["valor_bem"].mode().empty:
            self.stdout.write(f"  Moda:    R$ {df['valor_bem'].mode().iloc[0]:,.2f}")
