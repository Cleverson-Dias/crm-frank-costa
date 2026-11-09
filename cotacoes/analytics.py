import calendar
from datetime import date
from decimal import Decimal
from random import Random
from typing import Optional


PARECERES_FAVORAVEIS = frozenset({
    "Aprovada",
    "Aprovada com Fator de Risco",
    "Cobertura Autorizada",
    "Atendimento Liberado",
})


def calcular_taxa_retencao(renovadas: int, elegiveis: int) -> Optional[float]:
    if renovadas < 0 or elegiveis < 0 or renovadas > elegiveis:
        raise ValueError("A quantidade de renovações deve estar entre zero e o total elegível.")
    if elegiveis == 0:
        return None
    return round(renovadas / elegiveis * 100, 1)


def deslocar_mes(data_referencia: date, meses: int) -> date:
    indice = data_referencia.year * 12 + data_referencia.month - 1 + meses
    ano, mes_indice = divmod(indice, 12)
    mes = mes_indice + 1
    dia = min(data_referencia.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def gerar_comissoes_demonstracao(data_atual: date, quantidade_meses: int = 24):
    if quantidade_meses <= 0:
        raise ValueError("A quantidade de meses deve ser positiva.")

    gerador = Random(20261109)
    resultados = []
    inicio = date(data_atual.year, data_atual.month, 1)
    for deslocamento in range(quantidade_meses - 1, -1, -1):
        mes = deslocar_mes(inicio, -deslocamento)
        total = Decimal(str(gerador.randint(600000, 1200000) / 100))
        percentual_auto = Decimal(str(gerador.randint(25, 40) / 100))
        percentual_vida = Decimal(str(gerador.randint(20, 35) / 100))
        valores = [
            (mes, "auto", (total * percentual_auto).quantize(Decimal("0.01"))),
            (mes, "vida", (total * percentual_vida).quantize(Decimal("0.01"))),
        ]
        valor_saude = total - valores[0][2] - valores[1][2]
        valores.append((mes, "saude", valor_saude))
        resultados.extend(valores)

    return resultados
