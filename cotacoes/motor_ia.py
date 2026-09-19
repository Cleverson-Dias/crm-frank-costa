"""
motor_ia.py
-----------
Núcleo de negócio do CRM: Motor de Cálculo (RF03) + Motor de IA
Simbólica (RF04/RF05).

Design intencional: NENHUM machine learning "caixa-preta" aqui.
Toda regra é explícita, ordenada e auditável (RNF06) — cada decisão
carrega o id e o motivo textual da regra que a originou.

RNF03: ambas as funções abaixo são O(n) sobre uma lista pequena e
fixa de regras, então rodam muito abaixo do limite de 3s por
simulação exigido.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, Any, List


# ---------------------------------------------------------------------------
# 1) MOTOR DE CÁLCULO (RF03)
# ---------------------------------------------------------------------------

# Taxas-base por tipo de seguro — ajustar com dados reais/estimados do parceiro.
TAXA_BASE = {
    "auto": 0.045,          # 4,5% do valor do bem
    "residencial": 0.012,   # 1,2% do valor do bem
    "vida": 0.008,          # 0,8% do valor segurado
}

MARGEM_CORRETORA = 0.15  # 15% de comissão sobre o prêmio calculado


def calcular_proposta(tipo_seguro: str, valor_bem: float, fator_risco: float = 1.0) -> Dict[str, float]:
    """
    Calcula prêmio, franquia e margem da corretora.

    fator_risco: multiplicador (>1 aumenta o prêmio) vindo de variáveis
    do segurado/bem — ex: idade do condutor, sinistros anteriores,
    localização. Por padrão 1.0 (sem ajuste).
    """
    taxa = TAXA_BASE.get(tipo_seguro, 0.02)
    premio = round(valor_bem * taxa * fator_risco, 2)
    franquia = round(premio * 0.6, 2)  # regra simplificada: franquia = 60% do prêmio
    margem = round(premio * MARGEM_CORRETORA, 2)

    return {"premio": premio, "franquia": franquia, "margem": margem}


# ---------------------------------------------------------------------------
# 2) MOTOR DE IA SIMBÓLICA (RF04 / RF05)
# ---------------------------------------------------------------------------

@dataclass
class Regra:
    id: str
    descricao: str
    condicao: Callable[[Dict[str, Any]], bool]
    parecer: str          # "Aprovada" | "Necessita de Vistoria" | "Recusada"
    prioridade: int = 0   # regras de maior prioridade são avaliadas primeiro


# A ORDEM IMPORTA: a primeira regra cuja condição bater "vence" e
# encerra a avaliação — por isso regras de recusa/vistoria vêm antes
# da aprovação padrão.
#
# Numeração alinhada com a que já foi apresentada ao grupo/banca
# (R-101, R-102, R-103) para manter consistência entre o protótipo
# de frontend e a versão real de backend.
REGRAS: List[Regra] = [
    Regra(
        id="R-101",
        descricao="Condutor abaixo da idade mínima permitida (21 anos) para contratação direta sem vistoria prévia especial.",
        condicao=lambda p: p.get("idade", 99) < 21,
        parecer="Recusada",
        prioridade=100,
    ),
    Regra(
        id="R-104",
        descricao="Valor do bem muito acima da média para o tipo de seguro (possível superavaliação).",
        condicao=lambda p: p.get("valor_bem", 0) > 500_000,
        parecer="Necessita de Vistoria",
        prioridade=90,
    ),
    Regra(
        id="R-103",
        descricao="Perfil jovem (21 a 25 anos). Cobertura liberada mediante vistoria técnica prévia do veículo.",
        condicao=lambda p: 21 <= p.get("idade", 0) <= 25,
        parecer="Necessita de Vistoria",
        prioridade=80,
    ),
    Regra(
        id="R-102",
        descricao="Condutor com idade superior a 25 anos e bem dentro do limite padrão de cobertura da seguradora.",
        condicao=lambda p: True,  # regra "catch-all", fica sempre por último
        parecer="Aprovada",
        prioridade=0,
    ),
]


def avaliar_elegibilidade(perfil: Dict[str, Any]) -> Dict[str, str]:
    """
    Recebe os dados do segurado/bem (ex: {"idade": 24, "valor_bem": 45000})
    e retorna o parecer da IA Simbólica.

    RF05: retorno sempre inclui o status E a regra/motivo que motivou
    a decisão — nunca um veredito "sem explicação".
    """
    for regra in sorted(REGRAS, key=lambda r: r.prioridade, reverse=True):
        if regra.condicao(perfil):
            return {
                "status": regra.parecer,
                "regra_id": regra.id,
                "motivo": regra.descricao,
            }

    # Não deveria ser alcançado (R-102 é catch-all), mas mantido por segurança.
    return {"status": "Necessita de Vistoria", "regra_id": "N/A", "motivo": "Nenhuma regra aplicável."}


FATORES_RISCO = {"Aprovada": 1.0, "Necessita de Vistoria": 1.25, "Recusada": 0.0}


def fator_risco_por_perfil(perfil: Dict[str, Any], parecer: Dict[str, str] = None) -> float:
    """
    Traduz o parecer da IA num multiplicador para o motor de cálculo.
    Aceita um parecer já calculado (evita reavaliar as regras duas vezes);
    se não for passado, calcula na hora.
    """
    if parecer is None:
        parecer = avaliar_elegibilidade(perfil)
    return FATORES_RISCO.get(parecer["status"], 1.0)