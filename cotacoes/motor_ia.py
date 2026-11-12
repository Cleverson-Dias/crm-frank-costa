"""
motor_ia.py
------------
Motor de IA Simbolica (Sistema Especialista) para triagem de risco e
elegibilidade de cotacoes de seguro - Frank Costa Corretora de Seguros.

Um sistema especialista tem 3 camadas separadas:

1. Base de Fatos (memoria de trabalho): o que se sabe sobre o caso
   (idade, valor do bem, capital segurado...) - e TAMBEM os fatos NOVOS
   que o proprio motor vai derivando durante o raciocinio.
2. Base de Conhecimento: as regras SE/ENTAO, escritas como DADOS (uma
   lista de objetos Regra), nao como comandos de controle do programa.
3. Motor de Inferencia: um laco de encadeamento para frente (forward
   chaining) que varre a Base de Conhecimento e dispara a regra de maior
   prioridade cuja condicao bate com os fatos atuais, acrescentando fatos
   NOVOS a Base de Fatos - ate chegar a um fato de PARECER final ou ate
   nao sobrar regra para disparar (ponto fixo).

O motor e MULTI-RAMO: existe uma base de regras para cada tipo de seguro
operado pela corretora:

    - auto  -> regras R-001 a R-011 (regras internas de demonstração)
    - vida  -> regras V-001 a V-010 (SUSEP)
    - saude -> regras S-001 a S-010 (ANS)

Em cada ramo, regras de CLASSIFICACAO (prefixo C-) transformam os dados
brutos em fatos classificados (ex.: faixa_etaria = "jovem"). As regras de
PARECER leem esses fatos ja classificados - isso e encadeamento de
inferencia, nao um if/elif.

Prioridade: numero MENOR dispara primeiro (1 = Critica ... 10 = Padrao),
igual a coluna "Prioridade" das tabelas do documento. As regras de
classificacao tem prioridade 0 (rodam antes de qualquer parecer).

Auditabilidade (RNF06 / LGPD Art. 20): cada regra disparada entra na
trilha_inferencia com o id, a descricao e os fatos que gerou. O retorno
tambem informa a versao da base de regras e a data/hora da avaliacao.

Os limites numericos (valor maximo sem vistoria, capital maximo
automatico etc.) ficam centralizados em PARAMETROS para que a corretora
possa ajusta-los sem mexer nas regras.
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
import math
from typing import Callable, Optional

VERSAO_BASE_REGRAS = "2026.11.1"


@dataclass
class Regra:
    id: str
    ramo: str  # "auto", "vida" ou "saude"
    descricao: str
    # condicao: funcao que recebe a Base de Fatos (dict) e devolve bool
    condicao: Callable[[dict], bool]
    # conclusao: funcao que recebe a Base de Fatos e devolve fatos NOVOS
    conclusao: Callable[[dict], dict]
    prioridade: int  # menor numero = dispara primeiro


# --------------------------------------------------------------------
# Parametros do produto (ajustaveis pela corretora)
# --------------------------------------------------------------------
PARAMETROS = {
    "auto": {
        "idade_minima_condutor": 18,
        "idade_condutor_jovem": 25,         # abaixo disso: R-008
        "valor_maximo_sem_vistoria": 500_000.00,
        "idade_maxima_veiculo_anos": 15,
        "habilitacao_minima_anos": 2,
        "limite_sinistros_3_anos": 2,       # acima disso: R-009
    },
    "vida": {
        "idade_minima": 18,
        "idade_maxima_automatica": 65,
        "capital_maximo_automatico": 500_000.00,
    },
    "saude": {
        # Limites MAXIMOS de carencia da Lei 9.656/1998 (em dias)
        "carencia_maxima_legal_dias": {
            "urgencia_emergencia": 1,   # 24 horas
            "parto": 300,
            "demais": 180,
        },
        "cpt_maxima_dias": 730,         # 24 meses
    },
}

# Carencias configuradas no contrato (podem ser menores que o limite legal)
CARENCIAS_PADRAO_CONTRATO = {"urgencia_emergencia": 1, "parto": 300, "demais": 180}

# Quais coberturas cada segmentacao assistencial contempla
COBERTURAS_POR_SEGMENTACAO = {
    "ambulatorial": {"ambulatorial"},
    "hospitalar": {"hospitalar"},
    "hospitalar_obstetricia": {"hospitalar", "obstetricia"},
    "odontologico": {"odontologica"},
    "ambulatorial_hospitalar_obstetricia": {"ambulatorial", "hospitalar", "obstetricia"},
    "ambulatorial_odontologico": {"ambulatorial", "odontologica"},
    "ambulatorial_hospitalar": {"ambulatorial", "hospitalar"},
    "hospitalar_obstetricia_odontologico": {"hospitalar", "obstetricia", "odontologica"},
    "hospitalar_odontologico": {"hospitalar", "odontologica"},
    "ambulatorial_hospitalar_odontologico": {"ambulatorial", "hospitalar", "odontologica"},
    "ambulatorial_hospitalar_obstetricia_odontologico": {
        "ambulatorial", "hospitalar", "obstetricia", "odontologica"
    },
    "referencia": {"ambulatorial", "hospitalar", "obstetricia"},
}


# --------------------------------------------------------------------
# Funcoes auxiliares
# --------------------------------------------------------------------
def _sem_parecer(f: dict) -> bool:
    return "parecer" not in f


def _parecer(regra_id: str, status: str, motivo: str) -> dict:
    return {"parecer": status, "regra_id": regra_id, "motivo": motivo}


def _faltando(f: dict, campos: list) -> bool:
    return any(f.get(c) in (None, "") for c in campos)


def _atendimento(f: dict) -> bool:
    return f.get("operacao", "atendimento") == "atendimento"


def _reajuste(f: dict) -> bool:
    return f.get("operacao") == "reajuste"


PA = PARAMETROS["auto"]
PV = PARAMETROS["vida"]
PS = PARAMETROS["saude"]

CAMPOS_OBRIGATORIOS = {
    "auto": ["idade", "valor_bem"],
    "vida": ["idade", "capital_segurado"],
    "saude_atendimento": ["idade", "segmentacao_contratada", "tipo_atendimento", "dias_contrato"],
    "saude_nova_contratacao": ["idade", "segmentacao_contratada", "cobertura_exigida", "tipo_contratacao", "quantidade_vidas"],
    "saude_reajuste": ["idade", "tipo_plano", "tipo_reajuste"],
}


# ====================================================================
# MOTOR 1 - SEGURO DE AUTOMOVEL (SUSEP)
# ====================================================================
REGRAS_AUTO = [
    # --- Classificacao (fatos derivados) ---
    Regra("C-001", "auto", "Classifica a faixa etaria do condutor",
          lambda f: "idade" in f and "faixa_etaria" not in f,
          lambda f: {"faixa_etaria": (
              "invalida" if f["idade"] < PA["idade_minima_condutor"]
              else "jovem" if f["idade"] < PA["idade_condutor_jovem"]
              else "padrao")},
          0),
    Regra("C-002", "auto", "Classifica o risco pelo valor do bem segurado",
          lambda f: "valor_bem" in f and "faixa_valor" not in f,
          lambda f: {"faixa_valor": (
              "alto_valor" if f["valor_bem"] > PA["valor_maximo_sem_vistoria"] else "padrao")},
          0),
    Regra("C-003", "auto", "Calcula a idade do veiculo",
          lambda f: "ano_modelo" in f and "idade_veiculo" not in f,
          lambda f: {"idade_veiculo": f.get("ano_referencia", date.today().year) - f["ano_modelo"]},
          0),
    Regra("C-004", "auto", "Classifica a experiencia do condutor",
          lambda f: "tempo_habilitacao_anos" in f and "experiencia" not in f,
          lambda f: {"experiencia": (
              "baixa" if f["tempo_habilitacao_anos"] < PA["habilitacao_minima_anos"] else "adequada")},
          0),
    Regra("C-005", "auto", "Classifica a faixa etaria do condutor adicional",
          lambda f: f.get("idade_condutor_adicional") is not None
          and "condutor_adicional_jovem" not in f,
          lambda f: {"condutor_adicional_jovem":
                     f["idade_condutor_adicional"] < PA["idade_condutor_jovem"]},
          0),

    # --- Parecer ---
    Regra("R-001", "auto", "Dados obrigatorios ausentes, invalidos ou contraditorios",
          lambda f: _sem_parecer(f) and (
              _faltando(f, CAMPOS_OBRIGATORIOS["auto"])
              or f.get("valor_bem", 0) <= 0
              or f.get("faixa_etaria") == "invalida"),
          lambda f: _parecer("R-001", "Pendência de Dados",
                             "Dados obrigatorios do segurado ou do bem ausentes ou invalidos."),
          1),
    Regra("R-002", "auto", "Indicios de fraude, duplicidade ou divergencia documental",
          lambda f: _sem_parecer(f) and f.get("indicio_fraude", False),
          lambda f: _parecer("R-002", "Análise Manual",
                             "Indicios de fraude, duplicidade de proposta ou divergencia documental."),
          2),
    Regra("R-003", "auto", "Veiculo fora do escopo ou sem identificacao confiavel",
          lambda f: _sem_parecer(f) and (
              not f.get("veiculo_no_escopo", True) or not f.get("chassi_valido", True)),
          lambda f: (
              _parecer("R-003", "Recusada", "Veiculo fora do escopo do produto.")
              if not f.get("veiculo_no_escopo", True)
              else _parecer("R-003", "Análise Manual",
                            "Veiculo sem identificacao confiavel (chassi/documento).")),
          3),
    Regra("R-004", "auto", "Modificacao estrutural, blindagem, importacao especial ou acessorio sem comprovacao",
          lambda f: _sem_parecer(f) and f.get("veiculo_modificado", False),
          lambda f: _parecer("R-004", "Necessita de Vistoria",
                             "Veiculo com modificacao, blindagem ou acessorio sem comprovacao."),
          4),
    Regra("R-005", "auto", "Valor do bem acima do parametro interno de subscricao",
          lambda f: _sem_parecer(f) and f.get("faixa_valor") == "alto_valor",
          lambda f: _parecer("R-005", "Necessita de Vistoria",
                             "Valor do bem acima de R$ 500.000,00 exige vistoria previa."),
          5),
    Regra("R-006", "auto", "Veiculo acima do limite de idade do produto",
          lambda f: _sem_parecer(f) and f.get("idade_veiculo", 0) > PA["idade_maxima_veiculo_anos"],
          lambda f: _parecer("R-006", "Necessita de Vistoria",
                             f"Veiculo com {f['idade_veiculo']} anos, acima do limite de "
                             f"{PA['idade_maxima_veiculo_anos']} anos do produto."),
          6),
    Regra("R-007", "auto", "Condutor com baixa experiencia em uso profissional ou com sinistros",
          lambda f: _sem_parecer(f) and f.get("experiencia") == "baixa" and (
              f.get("uso_profissional", False) or f.get("sinistros_ultimos_3_anos", 0) >= 1),
          lambda f: _parecer("R-007", "Análise Manual",
                             "Condutor com menos de 2 anos de habilitacao associado a uso "
                             "profissional ou a sinistros recentes."),
          7),
    Regra("R-008", "auto", "Condutor jovem (menos de 25 anos) sem agravantes adicionais",
          lambda f: _sem_parecer(f) and f.get("faixa_etaria") == "jovem",
          lambda f: _parecer("R-008", "Aprovada com Fator de Risco",
                             "Condutor com menos de 25 anos: aceito com agravo tarifario."),
          8),
    Regra("R-009", "auto", "Historico de sinistros acima do limite tecnico",
          lambda f: _sem_parecer(f) and f.get("sinistros_ultimos_3_anos", 0) > PA["limite_sinistros_3_anos"],
          lambda f: _parecer("R-009", "Ajuste de Prêmio",
                             "Sinistros nos ultimos 3 anos acima do limite tecnico."),
          9),
    Regra("R-010", "auto", "Perfil completo e dentro dos parametros tecnicos",
          lambda f: _sem_parecer(f) and f.get("faixa_etaria") == "padrao" and f.get("faixa_valor") == "padrao",
          lambda f: _parecer("R-010", "Aprovada", "Perfil dentro dos parametros padrao de aceitacao."),
          10),
    Regra("R-011", "auto", "Condutor adicional jovem informado na proposta",
          lambda f: _sem_parecer(f) and f.get("condutor_adicional_jovem", False),
          lambda f: _parecer("R-011", "Aprovada com Fator de Risco",
                             "Condutor adicional com menos de 25 anos: sujeito a agravo tarifario."),
          9),
]


# ====================================================================
# MOTOR 2 - SEGURO DE VIDA (SUSEP)
# ====================================================================
REGRAS_VIDA = [
    # --- Classificacao ---
    Regra("C-101", "vida", "Classifica a faixa etaria do proponente",
          lambda f: "idade" in f and "faixa_etaria" not in f,
          lambda f: {"faixa_etaria": (
              "invalida" if f["idade"] < PV["idade_minima"]
              else "acima_limite" if f["idade"] > PV["idade_maxima_automatica"]
              else "padrao")},
          0),
    Regra("C-102", "vida", "Classifica o capital segurado solicitado",
          lambda f: "capital_segurado" in f and "faixa_capital" not in f,
          lambda f: {"faixa_capital": (
              "acima_limite" if f["capital_segurado"] > PV["capital_maximo_automatico"] else "padrao")},
          0),
    Regra("C-103", "vida", "Identifica habitos de risco declarados",
          lambda f: "habitos_risco" not in f,
          lambda f: {"habitos_risco": bool(f.get("tabagismo") or f.get("alcool_elevado"))},
          0),

    # --- Parecer ---
    Regra("V-001", "vida", "Dados obrigatorios ausentes ou DPS incompleta",
          lambda f: _sem_parecer(f) and (
              _faltando(f, CAMPOS_OBRIGATORIOS["vida"])
              or f.get("capital_segurado", 0) <= 0
              or f.get("faixa_etaria") == "invalida"
              or not f.get("dps_completa", True)),
          lambda f: _parecer("V-001", "Pendência de Dados",
                             "Dados obrigatorios ausentes ou Declaracao Pessoal de Saude incompleta."),
          1),
    Regra("V-002", "vida", "Informacoes incompativeis entre proposta e DPS",
          lambda f: _sem_parecer(f) and not f.get("dps_compativel", True),
          lambda f: _parecer("V-002", "Análise Manual",
                             "Informacoes da proposta incompativeis com a DPS."),
          2),
    Regra("V-003", "vida", "Capital segurado acima do limite de aceitacao automatica",
          lambda f: _sem_parecer(f) and f.get("faixa_capital") == "acima_limite",
          lambda f: _parecer("V-003", "Análise Médica ou Manual",
                             "Capital segurado acima do limite de aceitacao automatica."),
          3),
    Regra("V-004", "vida", "Idade acima da faixa de subscricao automatica",
          lambda f: _sem_parecer(f) and f.get("faixa_etaria") == "acima_limite",
          lambda f: _parecer("V-004", "Análise Médica ou Manual",
                             "Idade do proponente acima da faixa de subscricao automatica."),
          4),
    Regra("V-005", "vida", "Doenca relevante declarada ou internacao recente",
          lambda f: _sem_parecer(f) and (
              f.get("doenca_relevante_declarada", False) or f.get("internacao_recente", False)),
          lambda f: _parecer("V-005", "Declaração de Saúde / Exame Médico",
                             "Doenca relevante declarada ou internacao recente exige DPS detalhada ou exame."),
          5),
    Regra("V-006", "vida", "Profissao classificada como de alto risco",
          lambda f: _sem_parecer(f) and f.get("profissao_risco", False),
          lambda f: _parecer("V-006", "Ajuste de Prêmio",
                             "Atividade profissional de alto risco: agravo de taxa ou analise manual."),
          6),
    Regra("V-007", "vida", "Pratica habitual de esportes radicais",
          lambda f: _sem_parecer(f) and f.get("esporte_radical", False),
          lambda f: _parecer("V-007", "Análise de Cobertura / Agravo",
                             "Pratica de esporte radical: avaliar exclusao de cobertura ou agravo."),
          7),
    Regra("V-008", "vida", "Tabagismo ou consumo elevado de alcool",
          lambda f: _sem_parecer(f) and f.get("habitos_risco") is True,
          lambda f: _parecer("V-008", "Aprovada com Fator de Risco",
                             "Habitos declarados de risco: aceito com agravo tarifario."),
          8),
    Regra("V-009", "vida", "Aumento relevante de capital durante a vigencia",
          lambda f: _sem_parecer(f) and f.get("aumento_capital", False),
          lambda f: _parecer("V-009", "Nova Análise de Risco",
                             "Aumento de capital segurado durante a vigencia exige nova analise."),
          9),
    Regra("V-010", "vida", "Perfil completo, higido e dentro dos limites do produto",
          lambda f: _sem_parecer(f) and f.get("faixa_etaria") == "padrao" and f.get("faixa_capital") == "padrao",
          lambda f: _parecer("V-010", "Aprovada", "Perfil dentro dos parametros padrao de aceitacao."),
          10),
]


# ====================================================================
# MOTOR 3 - PLANO E SEGURO SAUDE (ANS)
# Nao seleciona risco por doenca (vedado pela ANS): valida elegibilidade,
# cobertura, carencias e CPT.
# ====================================================================
def _carencia_tipo(tipo_atendimento: str) -> str:
    return tipo_atendimento if tipo_atendimento in ("urgencia_emergencia", "parto") else "demais"


REGRAS_SAUDE = [
    # --- Classificacao ---
    Regra("C-201", "saude", "Valida as carencias configuradas contra os limites legais",
          lambda f: "carencia_config_valida" not in f,
          lambda f: {"carencia_config_valida": all(
              f.get("carencias_contrato", CARENCIAS_PADRAO_CONTRATO)[k] <= limite
              for k, limite in PS["carencia_maxima_legal_dias"].items())},
          0),
    Regra("C-202", "saude", "Verifica se o procedimento e coberto pela segmentacao contratada",
          lambda f: f.get("operacao", "atendimento") in {"atendimento", "nova_contratacao"} and "segmentacao_contratada" in f and "segmentacao_compativel" not in f,
          lambda f: {"segmentacao_compativel": f.get("cobertura_exigida", "ambulatorial")
                     in COBERTURAS_POR_SEGMENTACAO.get(f["segmentacao_contratada"], set())},
          0),
    Regra("C-203", "saude", "Calcula a carencia exigida e se ja foi cumprida",
          lambda f: _atendimento(f) and f.get("carencia_config_valida") is True
          and "tipo_atendimento" in f and "dias_contrato" in f and "carencia_cumprida" not in f,
          lambda f: (lambda exigida: {
              "carencia_exigida_dias": exigida,
              "carencia_cumprida": f["dias_contrato"] >= exigida,
              "carencia_restante_dias": max(0, exigida - f["dias_contrato"]),
          })(f.get("carencias_contrato", CARENCIAS_PADRAO_CONTRATO)[_carencia_tipo(f["tipo_atendimento"])]),
          0),
    Regra("C-204", "saude", "Verifica se o procedimento esta sob Cobertura Parcial Temporaria",
          lambda f: _atendimento(f) and "sob_cpt" not in f and "dias_contrato" in f,
          lambda f: {"sob_cpt": bool(
              f.get("dlp_declarada") and f.get("relacionado_dlp") and f.get("alta_complexidade")
              and f["dias_contrato"] < PS["cpt_maxima_dias"])},
          0),

    # --- Parecer ---
    Regra("S-001", "saude", "Dados do beneficiario ou do contrato incompletos",
          lambda f: _sem_parecer(f) and _faltando(
              f, CAMPOS_OBRIGATORIOS["saude_reajuste" if _reajuste(f) else "saude_nova_contratacao" if f.get("operacao") == "nova_contratacao" else "saude_atendimento"]),
          lambda f: _parecer("S-001", "Pendência de Dados",
                             "Dados do beneficiario, dependentes ou do contrato incompletos."),
          1),
    Regra("S-002", "saude", "Procedimento fora do Rol da ANS ou incompativel com a segmentacao",
          lambda f: _sem_parecer(f) and _atendimento(f) and (
              not f.get("no_rol_ans", True) or f.get("segmentacao_compativel") is False),
          lambda f: _parecer("S-002", "Não Coberto",
                             "Procedimento fora do Rol da ANS ou incompativel com a segmentacao contratada."),
          2),
    Regra("S-011", "saude", "Nova contratacao requer cotacao e condicoes da operadora",
          lambda f: _sem_parecer(f) and f.get("operacao") == "nova_contratacao"
          and f.get("segmentacao_compativel") is True,
          lambda f: _parecer("S-011", "Aguardando Cotação da Operadora",
                             "Sem contrato vigente: carências e preço dependem da proposta e das condições informadas pela operadora."),
          11),
    Regra("S-012", "saude", "Cobertura solicitada fora da segmentacao pretendida",
          lambda f: _sem_parecer(f) and f.get("operacao") == "nova_contratacao"
          and f.get("segmentacao_compativel") is False,
          lambda f: _parecer("S-012", "Revisar Segmentação",
                             "A segmentação pretendida não inclui a cobertura solicitada."),
          12),
    Regra("S-003", "saude", "Atendimento fora da area de abrangencia geografica",
          lambda f: _sem_parecer(f) and _atendimento(f) and not f.get("dentro_abrangencia", True),
          lambda f: _parecer("S-003", "Oferecer Produto / Análise Manual",
                             "Atendimento fora da area de abrangencia geografica do contrato."),
          3),
    Regra("S-004", "saude", "Doenca ou lesao preexistente declarada: aplica CPT",
          lambda f: _sem_parecer(f) and _atendimento(f) and f.get("sob_cpt") is True,
          lambda f: _parecer("S-004", "Aplicar CPT",
                             "Procedimento de alta complexidade ligado a DLP declarada: Cobertura "
                             "Parcial Temporaria de ate 24 meses."),
          4),
    Regra("S-005", "saude", "Urgencia ou emergencia com carencia de 24h cumprida",
          lambda f: _sem_parecer(f) and _atendimento(f)
          and f.get("tipo_atendimento") == "urgencia_emergencia" and f.get("carencia_cumprida") is True,
          lambda f: _parecer("S-005", "Atendimento Liberado",
                             "Urgencia/emergencia apos o prazo legal de 24 horas."),
          5),
    Regra("S-006", "saude", "Procedimento no Rol, na segmentacao e com carencia cumprida",
          lambda f: _sem_parecer(f) and _atendimento(f) and f.get("carencia_cumprida") is True,
          lambda f: _parecer("S-006", "Cobertura Autorizada",
                             "Procedimento coberto pelo Rol da ANS e pela segmentacao contratada."),
          6),
    Regra("S-007", "saude", "Carencia ainda em cumprimento",
          lambda f: _sem_parecer(f) and _atendimento(f) and f.get("carencia_cumprida") is False,
          lambda f: _parecer("S-007", "Carência em Cumprimento",
                             f"Faltam {f['carencia_restante_dias']} dia(s) para o fim da carencia."),
          7),
    Regra("S-008", "saude", "Carencia configurada acima do limite legal da ANS",
          lambda f: _sem_parecer(f) and f.get("carencia_config_valida") is False,
          lambda f: _parecer("S-008", "Erro de Parâmetro",
                             "Carencia configurada acima do limite legal (24h, 300 ou 180 dias)."),
          8),
    Regra("S-009", "saude", "Reajuste por mudanca de faixa etaria",
          lambda f: _sem_parecer(f) and _reajuste(f) and f.get("tipo_reajuste") == "faixa_etaria",
          lambda f: _parecer("S-009", "Aplicar Percentual Contratual",
                             "Mudanca de faixa etaria: aplicar o percentual previsto em contrato."),
          9),
    Regra("S-010", "saude", "Reajuste anual de plano individual sem indice autorizado pela ANS",
          lambda f: _sem_parecer(f) and _reajuste(f) and f.get("tipo_reajuste") == "anual"
          and f.get("tipo_plano") == "individual" and not f.get("indice_ans_autorizado", False),
          lambda f: _parecer("S-010", "Bloquear Cálculo de Reajuste",
                             "Plano individual: reajuste anual depende de indice autorizado pela ANS."),
          10),
]


BASES_DE_CONHECIMENTO = {
    "auto": REGRAS_AUTO,
    "vida": REGRAS_VIDA,
    "saude": REGRAS_SAUDE,
}


def _normalizar_ramo(tipo: Optional[str]) -> str:
    tipo = (tipo or "auto").strip().lower()
    return {"saúde": "saude", "automovel": "auto", "automóvel": "auto"}.get(tipo, tipo)


def avaliar_elegibilidade(perfil: dict) -> dict:
    """
    Motor de Inferencia (encadeamento para frente / forward chaining).

    Recebe os fatos brutos do caso (perfil) e devolve o parecer final,
    junto com a trilha de regras disparadas no caminho - a prova de
    que a decisao e 100% auditavel (RNF06), sem caixa-preta.

    O campo "tipo_seguro" do perfil escolhe a base de regras
    (auto, vida ou saude). Se nao for informado, assume "auto".
    """
    ramo = _normalizar_ramo(perfil.get("tipo_seguro"))
    avaliado_em = datetime.now(timezone.utc).isoformat()

    if ramo not in BASES_DE_CONHECIMENTO:
        return {
            "status": "Pendência de Dados",
            "regra_id": None,
            "motivo": f"Tipo de seguro '{ramo}' nao operado pela corretora.",
            "trilha_inferencia": [],
            "versao_base_regras": VERSAO_BASE_REGRAS,
            "avaliado_em": avaliado_em,
        }

    regras = sorted(BASES_DE_CONHECIMENTO[ramo], key=lambda r: r.prioridade)
    fatos = dict(perfil)
    trilha = []

    houve_disparo = True
    while houve_disparo and "parecer" not in fatos:
        houve_disparo = False
        # a cada rodada, varre a Base de Conhecimento em ordem de
        # prioridade e dispara a PRIMEIRA regra cuja condicao bate com
        # os fatos atuais. O fato novo gerado pode habilitar outra
        # regra na proxima rodada - isso e inferencia, nao um if/elif.
        for regra in regras:
            if regra.condicao(fatos):
                fatos_novos = regra.conclusao(fatos)
                fatos.update(fatos_novos)
                trilha.append({
                    "regra_id": regra.id,
                    "descricao": regra.descricao,
                    "fatos_gerados": fatos_novos,
                })
                houve_disparo = True
                break  # reinicia a varredura com a Base de Fatos atualizada

    return {
        "status": fatos.get("parecer", "Indefinido"),
        "regra_id": fatos.get("regra_id"),
        "motivo": fatos.get("motivo"),
        "trilha_inferencia": trilha,  # auditoria completa (RNF06)
        "versao_base_regras": VERSAO_BASE_REGRAS,
        "avaliado_em": avaliado_em,
    }


# --------------------------------------------------------------------
# Motor de Calculo
# --------------------------------------------------------------------
# Multiplicador aplicado ao premio conforme o parecer.
# Pareceres que nao estao aqui (analises pendentes) usam 1.0, ou seja,
# o premio exibido e uma estimativa sujeita a confirmacao.
FATORES_RISCO = {
    "Aprovada": 1.0,
    "Aprovada com Fator de Risco": 1.15,
    "Necessita de Vistoria": 1.25,
    "Ajuste de Prêmio": 1.30,
    "Recusada": 0.0,
}


def fator_risco_por_perfil(perfil: dict, parecer: Optional[dict] = None) -> float:
    parecer = parecer or avaliar_elegibilidade(perfil)
    return FATORES_RISCO.get(parecer["status"], 1.0)


# Taxa base de estimativa sobre o valor do bem (auto) ou capital segurado (vida).
# Em saúde, a entrada é uma mensalidade informada ou o prêmio anual da operadora.
TAXA_BASE = {"auto": 0.045, "vida": 0.008}
MARGEM_CORRETORA = 0.15


def taxa_referencia_vida(idade: Optional[int]) -> float:
    """Taxa anual estimativa baseada em faixas públicas de preço de 2026.

    Usa o limite superior publicado para cobertura básica por morte, não é
    tarifa de seguradora nem substitui cotação com as coberturas e o perfil.
    Sem idade, preserva a taxa legada para chamadas antigas do motor.
    """
    if idade is None:
        return TAXA_BASE["vida"]
    pontos = (
        (18, 35), (25, 35), (30, 35), (35, 50), (40, 50),
        (45, 120), (50, 120), (55, 250), (60, 250), (65, 500),
    )  # prêmio mensal por R$ 100 mil de capital segurado
    idade = max(18, int(idade))
    mensal_por_100mil = pontos[-1][1]
    for (idade_a, valor_a), (idade_b, valor_b) in zip(pontos, pontos[1:]):
        if idade <= idade_b:
            proporcao = (idade - idade_a) / (idade_b - idade_a)
            mensal_por_100mil = valor_a + (valor_b - valor_a) * proporcao
            break
    return mensal_por_100mil * 12 / 100_000


def calcular_proposta(
    tipo_seguro: str,
    valor_bem: Optional[float],
    fator_risco: Optional[float],
    idade: Optional[int] = None,
    periodicidade: str = "anual",
) -> dict:
    ramo = _normalizar_ramo(tipo_seguro)
    try:
        valor = float(valor_bem) if valor_bem is not None else None
    except (TypeError, ValueError, OverflowError):
        valor = None
    try:
        fator = float(fator_risco) if fator_risco is not None else 1.0
    except (TypeError, ValueError, OverflowError):
        fator = 1.0

    if valor is None or not math.isfinite(valor) or valor < 0:
        return {
            "premio_bruto": None,
            "premio": None,
            "franquia": 0.0,
            "comissao_corretora": None,
            "margem": None,
        }
    if not math.isfinite(fator):
        fator = 1.0

    if ramo == "saude":
        premio = valor * 12 if periodicidade == "mensal" else valor
        franquia = 0.0
        margem = premio * 0.10
    else:
        if ramo not in TAXA_BASE:
            raise ValueError(f"Tipo de seguro '{tipo_seguro}' nao possui taxa de calculo configurada.")
        taxa = taxa_referencia_vida(idade) if ramo == "vida" else TAXA_BASE[ramo]
        premio = valor * taxa * fator
        franquia = premio * 0.6
        margem = premio * MARGEM_CORRETORA
    premio = round(premio, 2)
    franquia = round(franquia, 2)
    margem = round(margem, 2)
    return {
        "premio_bruto": premio,
        "premio": premio,
        "franquia": franquia,
        "comissao_corretora": margem,
        "margem": margem,
    }
