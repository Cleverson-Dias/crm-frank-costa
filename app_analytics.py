import logging
import os
import sys
import calendar
import math
from datetime import date, datetime, timedelta
from pathlib import Path

import django
import pandas as pd
import plotly.express as px
import streamlit as st
from django.db import DatabaseError, ProgrammingError
from django.db.models import Count, Sum
from pymongo import MongoClient
from pymongo.errors import PyMongoError


BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "crm_core.settings")
django.setup()

from django.conf import settings
from cotacoes.analytics import calcular_taxa_retencao, deslocar_mes
from cotacoes.models import (
    Apolice,
    Cliente,
    ComissaoMensalDemonstracao,
    RenovacaoApolice,
)


LOGGER = logging.getLogger(__name__)
RAMOS = {
    "auto": "Automóvel",
    "vida": "Vida",
    "saude": "Saúde",
}
RAMOS_ATIVOS = ("auto", "vida", "saude")
MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]
PERIODOS = ("Últimos 12 meses", "Últimos 24 meses", "Ano atual", "Personalizado")
CORES = {
    "brand": "#0284c7",
    "brand_dark": "#0369a1",
    "mint": "#10b981",
    "navy": "#0f172a",
    "ink": "#1e293b",
    "muted": "#64748b",
    "line": "#e2e8f0",
    "page": "#f4f7fb",
    "orange": "#f59e0b",
    "blue": "#06b6d4",
    "red": "#ef4444",
    "purple": "#8b5cf6",
}
CORES_STATUS = {
    "Aprovada": "#0284c7",
    "Aprovada com Fator de Risco": "#10b981",
    "Cobertura Autorizada": "#10b981",
    "Atendimento Liberado": "#10b981",
    "Análise Manual": "#f59e0b",
    "Análise Médica ou Manual": "#f59e0b",
    "Necessita de Vistoria": "#8b5cf6",
    "Pendência de Dados": "#f59e0b",
    "Recusada": "#ef4444",
    "Não Coberto": "#ef4444",
    "Análise pendente": "#64748b",
}
LIMITE_COTACOES = 10_000

st.set_page_config(
    page_title="Painel Estatístico e Analítico | Frank Costa",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    f"""
    <style>
    :root {{
        --brand: {CORES["brand"]};
        --brand-dark: {CORES["brand_dark"]};
        --ink: {CORES["ink"]};
        --muted: {CORES["muted"]};
        --line: {CORES["line"]};
        --page: {CORES["page"]};
    }}
    .stApp {{ background: var(--page); color: var(--ink); }}
    [data-testid="stHeader"] {{ background: rgba(244,247,251,.94); }}
    [data-testid="stToolbar"], [data-testid="stStatusWidget"], #MainMenu, footer {{
        display:none !important;
    }}
    [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
        background:var(--page); color:var(--ink);
    }}
    [data-testid="stSidebar"] {{
        background:linear-gradient(180deg,#0f172a 0%,#1e293b 100%);
        border-right: 0;
    }}
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
        color:#e2e8f0;
    }}
    [data-testid="stSidebar"] > div:first-child {{ padding-top: 1.15rem; }}
    .block-container {{
        max-width: 1540px;
        padding: 1.6rem 2rem 3.2rem;
    }}
    .brand-lockup {{ display:flex; align-items:center; gap:.75rem; padding:.3rem 0 .85rem; }}
    .brand-symbol {{
        display:flex; align-items:center; justify-content:center;
        width:2.55rem; height:2.55rem; border-radius:.8rem;
        background:linear-gradient(145deg,#38bdf8,#0284c7);
        color:#fff; font-size:1.35rem; font-weight:800;
        box-shadow:0 6px 16px rgba(8,99,70,.18);
    }}
    .brand-name {{ color:#f8fafc; font-family:Inter,Arial,sans-serif; font-size:1.05rem;
        font-weight:700; letter-spacing:.09em; line-height:1.05; }}
    .brand-subtitle {{ color:#94a3b8; font-size:.58rem; letter-spacing:.28em;
        margin-top:.22rem; text-transform:uppercase; }}
    .hero {{
        position:relative; overflow:hidden;
        background:transparent;
        border-radius:0; padding:.45rem .35rem 1.1rem;
        box-shadow:none;
        margin-bottom:1.25rem;
    }}
    .hero-kicker {{ color:#0284c7; font-size:.69rem; font-weight:750;
        letter-spacing:.16em; text-transform:uppercase; }}
    .hero h1 {{ color:#0f172a; font-size:1.8rem; font-weight:750;
        letter-spacing:-.025em; margin:.42rem 0 .35rem; }}
    .hero p {{ color:#64748b; font-size:.94rem; margin:0; }}
    .hero-meta {{ color:#94a3b8; font-size:.75rem;
        margin-top:.9rem; }}
    div[data-testid="stMetric"] {{
        background:#fff; border:1px solid #e2e8f0; border-radius:1rem;
        padding:1rem 1.1rem; box-shadow:0 4px 12px rgba(15,23,42,.03);
        min-height:7.8rem;
    }}
    [data-testid="stMetricLabel"] {{ min-height:2.3rem; align-items:flex-start; }}
    [data-testid="stMetricLabel"] [data-testid="stMarkdownContainer"] {{
        white-space:normal !important; overflow:visible !important;
        text-overflow:clip !important;
    }}
    [data-testid="stMetricLabel"] p {{
        color:#52675f !important; font-size:.78rem; font-weight:650;
        white-space:normal !important; overflow:visible !important;
        text-overflow:clip !important; line-height:1.2;
    }}
    div[data-testid="stMetricValue"] {{ color:#0f172a !important; font-size:1.48rem; font-weight:750; }}
    div[data-testid="stMetricDelta"] {{ font-size:.73rem; }}
    div[data-testid="stTabs"] button {{ font-weight:650; }}
    div[data-testid="stTabs"] button[aria-selected="true"] {{
        color:var(--brand-dark); border-bottom-color:var(--brand);
    }}
    div[data-testid="stTabs"] button {{ color:#425a50; }}
    div[data-testid="stWidgetLabel"] p, label, .stMarkdown p, .stMarkdown h1,
    .stMarkdown h2, .stMarkdown h3, [data-testid="stCaptionContainer"] {{
        color:#475569;
    }}
    [data-testid="stPills"] button {{ border-radius:999px; }}
    [data-testid="stPills"] button[aria-pressed="true"] {{
        background:#e0f2fe; border-color:#7dd3fc; color:#0369a1;
    }}
    .section-heading {{ color:#0f172a; font-size:1.05rem; font-weight:750;
        margin:.35rem 0 .2rem; }}
    .section-note {{ color:#82918b; font-size:.78rem; margin-bottom:.8rem; }}
    .data-note {{ background:#eff6ff; border:1px solid #bfdbfe;
        border-radius:1rem; color:#1e40af; padding:.9rem 1rem;
        font-size:.8rem; }}
    .stButton button, .stDownloadButton button {{
        border-radius:.65rem; font-weight:650;
    }}
    .stButton button[kind="primary"] {{
        background:#0284c7; border-color:#0284c7;
    }}
    .stCaption {{ color:#64748b; }}
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        background:#ffffff; border:1px solid #e2e8f0; border-radius:1rem;
        box-shadow:0 4px 12px rgba(15,23,42,.03); padding:.35rem .65rem .6rem;
    }}
    [data-testid="stSidebar"] [data-testid="stSelectbox"] div,
    [data-testid="stSidebar"] [data-testid="stMultiSelect"] div {{ color:#0f172a; }}
    [data-testid="stSidebar"] hr {{ border-color:rgba(148,163,184,.22); }}
    @media (max-width: 800px) {{
        .block-container {{ padding:1rem 1rem 2rem; }}
        .hero {{ padding:1.3rem; }}
        .hero h1 {{ font-size:1.45rem; }}
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_mongo_collection():
    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
    return client[settings.MONGO_DB_NAME]["cotacoes"]


@st.cache_data(ttl=60, show_spinner="Atualizando cotações...")
def carregar_cotacoes():
    collection = get_mongo_collection()
    collection.database.client.admin.command("ping")
    documentos = list(
        collection.find()
        .sort("criado_em", -1)
        .limit(LIMITE_COTACOES + 1)
    )
    atingiu_limite = len(documentos) > LIMITE_COTACOES
    return documentos[:LIMITE_COTACOES], atingiu_limite


@st.cache_data(ttl=60, show_spinner="Atualizando carteira e histórico...")
def carregar_dados_relacionais(ramos, data_inicio, data_fim, incluir_demonstracao):
    apolices_ativas_filtro = Apolice.objects.filter(
        status="ativa",
        bem__tipo__in=ramos,
    )
    if not incluir_demonstracao:
        apolices_ativas_filtro = apolices_ativas_filtro.filter(
            cliente__dados_sinteticos=False
        )
    apolices_ativas_qs = (
        apolices_ativas_filtro
        .select_related("cliente", "bem", "seguradora", "plano")
        .order_by("cliente__nome")
    )
    apolices_ativas = list(
        apolices_ativas_qs.values(
            "numero_apolice",
            "cliente__nome",
            "bem__tipo",
            "seguradora__nome",
            "valor_premio",
            "valor_comissao",
            "data_inicio",
            "data_fim",
        )
    )
    comissoes_por_ramo = list(
        apolices_ativas_qs.values("bem__tipo")
        .annotate(total=Sum("valor_comissao", default=0))
        .order_by("bem__tipo")
    )
    comissoes_por_seguradora = list(
        apolices_ativas_qs.values("seguradora__nome")
        .annotate(total=Sum("valor_comissao", default=0))
        .order_by("-total")
    )
    clientes_na_carteira = (
        apolices_ativas_qs.filter(cliente__ativo=True)
        .values("cliente_id")
        .distinct()
        .count()
    )
    cotacoes_fechadas_qs = Apolice.objects.filter(bem__tipo__in=ramos)
    if not incluir_demonstracao:
        cotacoes_fechadas_qs = cotacoes_fechadas_qs.filter(
            cliente__dados_sinteticos=False
        )
    ids_cotacoes_fechadas = list(
        cotacoes_fechadas_qs.exclude(cotacao_mongo_id="").values_list(
            "cotacao_mongo_id", flat=True
        )
    )
    renovacoes = RenovacaoApolice.objects.filter(
        data_vencimento__gte=data_inicio,
        data_vencimento__lte=data_fim,
        status__in=["renovada", "nao_renovada"],
        apolice__bem__tipo__in=ramos,
    )
    if not incluir_demonstracao:
        renovacoes = renovacoes.filter(apolice__cliente__dados_sinteticos=False)
    renovacoes_por_status = list(
        renovacoes.values("status")
        .annotate(total=Count("id"))
        .order_by("status")
    )
    historico_renovacoes = list(
        renovacoes.values(
            "data_vencimento",
            "status",
            "apolice__numero_apolice",
            "apolice__cliente__nome",
            "apolice__bem__tipo",
        ).order_by("-data_vencimento")
    )
    nomes_clientes = dict(Cliente.objects.values_list("id", "nome"))
    comissoes_mensais = []
    if incluir_demonstracao:
        mes_inicio = date(data_inicio.year, data_inicio.month, 1)
        mes_fim = date(data_fim.year, data_fim.month, 1)
        comissoes_mensais = list(
            ComissaoMensalDemonstracao.objects.filter(
                mes_referencia__gte=mes_inicio,
                mes_referencia__lte=mes_fim,
                tipo_seguro__in=ramos,
            ).values(
                "mes_referencia",
                "tipo_seguro",
                "comissao_bruta",
                "percentual_liquido_estimado",
            ).order_by("mes_referencia", "tipo_seguro")
        )
    elegiveis = sum(int(item["total"]) for item in renovacoes_por_status)
    renovadas = sum(
        int(item["total"])
        for item in renovacoes_por_status
        if item["status"] == "renovada"
    )
    return {
        "apolices_ativas": apolices_ativas,
        "comissoes_por_ramo": comissoes_por_ramo,
        "comissoes_por_seguradora": comissoes_por_seguradora,
        "clientes_na_carteira": clientes_na_carteira,
        "ids_cotacoes_fechadas": ids_cotacoes_fechadas,
        "renovacoes_elegiveis": elegiveis,
        "renovacoes_concluidas": renovadas,
        "historico_renovacoes": historico_renovacoes,
        "nomes_clientes": nomes_clientes,
        "comissoes_mensais": comissoes_mensais,
    }


def preparar_cotacoes(documentos, nomes_clientes):
    """Normaliza documentos Mongo com subdocumentos opcionais e esquema legado."""
    documentos_seguros = []
    for documento in documentos or []:
        if not isinstance(documento, dict):
            continue
        documento_seguro = dict(documento)
        for campo in ("dados", "dados_bem", "resultado_calculo", "parecer_ia"):
            if not isinstance(documento_seguro.get(campo), dict):
                documento_seguro[campo] = {}
        documentos_seguros.append(documento_seguro)
    normalizados = pd.json_normalize(documentos_seguros, sep=".").fillna("")
    linhas = []
    for documento in normalizados.to_dict("records"):
        ramo = documento.get("tipo_seguro") or "desconhecido"
        mensalidade = (
            documento.get("dados.mensalidade_estimada")
            or documento.get("mensalidade_estimada")
            or documento.get("dados.mensalidade_mensal")
        ) if ramo == "saude" else None
        premio = (
            documento.get("resultado_calculo.premio_anual")
            or documento.get("resultado_calculo.premio_bruto")
            or documento.get("resultado_calculo.premio")
            or documento.get("premio_anual")
            or (documento.get("dados.premio_anual") if ramo == "saude" else None)
            or (documento.get("dados.premio_anual_estimado") if ramo == "saude" else None)
        )
        if ramo == "saude" and not premio and mensalidade:
            try:
                premio = float(mensalidade) * 12
            except (TypeError, ValueError):
                premio = None
        trilha = documento.get("parecer_ia.trilha_inferencia") or documento.get("trilha_inferencia")
        tem_regra_e_motivo = bool(documento.get("parecer_ia.regra_id") and documento.get("parecer_ia.motivo"))
        status = documento.get("parecer_ia.status") or documento.get("status") or "Análise pendente"
        valor_bem = None
        if ramo != "saude":
            valor_bem = (
                documento.get("dados.valor_bem") or documento.get("dados.valor_fipe")
                or documento.get("dados.capital_segurado") or documento.get("dados_bem.valor_bem")
                or documento.get("dados_bem.valor_fipe")
            )
        linhas.append({
            "id": str(documento.get("_id") or ""),
            "cliente": nomes_clientes.get(documento.get("cliente_id"), "Cliente não localizado"),
            "ramo": ramo,
            "mensalidade_estimada": mensalidade,
            "premio": premio,
            "valor_bem": valor_bem,
            "status": traducao_status(status),
            "criado_em": documento.get("criado_em"),
            "origem": documento.get("dados.origem_dados") or "",
            "sintetica": documento.get("dados.origem_dados") == "demonstracao_sintetica",
            "auditavel": bool(trilha) or tem_regra_e_motivo,
        })
    colunas = [
        "id", "cliente", "ramo", "mensalidade_estimada", "premio", "valor_bem",
        "status", "criado_em", "origem", "sintetica", "auditavel",
    ]
    df = pd.DataFrame(linhas, columns=colunas).fillna({
        "id": "", "cliente": "Cliente não localizado", "ramo": "desconhecido",
        "status": "Análise pendente", "origem": "", "sintetica": False, "auditavel": False,
    })
    df["premio"] = pd.to_numeric(df["premio"], errors="coerce")
    df["mensalidade_estimada"] = pd.to_numeric(df["mensalidade_estimada"], errors="coerce")
    df["valor_bem"] = pd.to_numeric(df["valor_bem"], errors="coerce")
    df["criado_em"] = pd.to_datetime(df["criado_em"], errors="coerce", utc=True)
    return df

def formatar_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def primeiro_dia_do_mes(data_referencia, deslocamento=0):
    return deslocar_mes(date(data_referencia.year, data_referencia.month, 1), deslocamento)


def traducao_status(status):
    if status is None:
        return "Análise pendente"
    status = str(status).strip()
    if not status or status.casefold() in {"null", "none", "não processado", "nao processado"}:
        return "Análise pendente"
    traducoes = {
        "approved": "Aprovada",
        "approved with risk factor": "Aprovada com Fator de Risco",
        "manual review": "Análise Manual",
        "pending": "Pendente",
        "pending data": "Pendência de Dados",
        "rejected": "Recusada",
        "denied": "Não Coberto",
        "pending analysis": "Análise pendente",
        "approved with factor risk": "Aprovada com Fator de Risco",
        "análise manual": "Análise Manual",
        "análise médica ou manual": "Análise Médica ou Manual",
        "cobertura autorizada": "Cobertura Autorizada",
        "atendimento liberado": "Atendimento Liberado",
        "aprovada com fator de risco": "Aprovada com Fator de Risco",
        "aprovada": "Aprovada",
        "pendência de dados": "Pendência de Dados",
        "recusada": "Recusada",
        "não coberto": "Não Coberto",
        "análise pendente": "Análise pendente",
    }
    return traducoes.get(status.strip().casefold(), status)


def aplicar_estilo_grafico(fig, altura=330):
    fig.update_layout(
        height=altura,
        margin=dict(l=12, r=12, t=28, b=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Arial, sans-serif", color=CORES["muted"], size=12),
        title_font=dict(color=CORES["navy"], size=15),
        legend_title_text="",
        hoverlabel=dict(bgcolor="#ffffff", bordercolor=CORES["line"], font_color=CORES["ink"]),
    )
    fig.update_xaxes(showgrid=False, linecolor=CORES["line"], tickfont_size=11)
    fig.update_yaxes(showgrid=True, gridcolor="#edf1ef", zeroline=False, tickfont_size=11)
    return fig


def formatar_tabela_cotacoes(df, ids_fechados):
    tabela = df.copy()
    tabela["Situação"] = tabela["id"].isin(ids_fechados).map(
        {True: "Fechada", False: "Em negociação"}
    )
    tabela["Ramo"] = tabela["ramo"].map(RAMOS).fillna(tabela["ramo"])
    tabela["Prêmio estimado"] = tabela["premio"].map(
        lambda valor: formatar_moeda(valor) if pd.notna(valor) else "—"
    )
    tabela["Data"] = tabela["criado_em"].dt.strftime("%d/%m/%Y")
    return tabela[["Data", "cliente", "Ramo", "status", "Prêmio estimado", "Situação"]].rename(
        columns={
            "cliente": "Cliente",
            "status": "Parecer",
        }
    )


st.sidebar.markdown(
    """
    <div class="brand-lockup">
      <div class="brand-symbol">F</div>
      <div><div class="brand-name">FRANK COSTA</div>
      <div class="brand-subtitle">Corretora de Seguros</div></div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.sidebar.caption("PAINEL GERENCIAL")
st.sidebar.divider()
st.sidebar.subheader("Filtros")

hoje = date.today()
periodo_selecionado = st.sidebar.selectbox(
    "Período das cotações e renovações",
    options=PERIODOS,
    index=1,
    key="periodo_dashboard",
)
if periodo_selecionado == "Personalizado":
    anos = list(range(hoje.year - 5, hoje.year + 1))
    mes_padrao_inicio = primeiro_dia_do_mes(hoje, -23)
    col_mes_inicio, col_ano_inicio = st.sidebar.columns(2)
    with col_mes_inicio:
        mes_inicio = st.selectbox(
            "Mês inicial",
            options=range(1, 13),
            index=mes_padrao_inicio.month - 1,
            format_func=lambda mes: MESES[mes - 1].capitalize(),
            key="mes_inicio_dashboard",
        )
    with col_ano_inicio:
        ano_inicio = st.selectbox(
            "Ano inicial",
            options=anos,
            index=anos.index(mes_padrao_inicio.year),
            key="ano_inicio_dashboard",
        )
    col_mes_fim, col_ano_fim = st.sidebar.columns(2)
    with col_mes_fim:
        mes_fim = st.selectbox(
            "Mês final",
            options=range(1, 13),
            index=hoje.month - 1,
            format_func=lambda mes: MESES[mes - 1].capitalize(),
            key="mes_fim_dashboard",
        )
    with col_ano_fim:
        ano_fim = st.selectbox(
            "Ano final",
            options=anos,
            index=anos.index(hoje.year),
            key="ano_fim_dashboard",
        )
    data_inicio = date(ano_inicio, mes_inicio, 1)
    data_fim = date(ano_fim, mes_fim, calendar.monthrange(ano_fim, mes_fim)[1])
elif periodo_selecionado == "Ano atual":
    data_inicio = date(hoje.year, 1, 1)
    data_fim = hoje
else:
    meses_periodo = 12 if periodo_selecionado == "Últimos 12 meses" else 24
    data_inicio = primeiro_dia_do_mes(hoje, -(meses_periodo - 1))
    data_fim = hoje

if st.sidebar.button(
    "Atualizar dados",
    icon=":material/refresh:",
    width="stretch",
    key="atualizar_dashboard",
):
    st.cache_data.clear()
    st.rerun()
st.sidebar.caption("Os filtros selecionados permanecem ao atualizar.")
if data_inicio > data_fim:
    st.sidebar.error("A data inicial deve ser anterior à data final.")
    st.stop()

try:
    documentos, atingiu_limite = carregar_cotacoes()
except PyMongoError:
    LOGGER.exception("Falha ao carregar as cotações do MongoDB.")
    st.error("Não foi possível conectar ao MongoDB. Verifique a configuração MONGO_URI.")
    st.stop()

try:
    nomes_clientes = dict(Cliente.objects.values_list("id", "nome"))
except DatabaseError:
    LOGGER.exception("Falha ao carregar os clientes do PostgreSQL.")
    st.error("Não foi possível consultar os clientes no PostgreSQL. Verifique DB_*.")
    st.stop()

df_todas = preparar_cotacoes(documentos, nomes_clientes)
df_todas = df_todas[df_todas["ramo"].isin(RAMOS_ATIVOS)].reset_index(drop=True)
filtro_ramos = st.sidebar.pills(
    "Ramos de seguro",
    options=list(RAMOS_ATIVOS),
    default=list(RAMOS_ATIVOS),
    format_func=lambda ramo: RAMOS.get(ramo, ramo),
    help="Os ramos selecionados filtram cotações, apólices vigentes e comissões.",
    selection_mode="multi",
    key="ramos_dashboard",
)
status_disponiveis = sorted(df_todas["status"].dropna().unique()) if not df_todas.empty else []
filtro_status = st.sidebar.multiselect(
    "Pareceres das cotações",
    options=status_disponiveis,
    default=status_disponiveis,
    placeholder="Todos os pareceres",
    help="Este filtro afeta os indicadores, gráficos e a tabela de cotações.",
    key="pareceres_dashboard",
)
incluir_sinteticos = st.sidebar.toggle(
    "Incluir dados fictícios da demonstração",
    value=True,
    key="incluir_demo_dashboard",
    help=(
        "São registros inventados para testar o painel, não clientes ou contratos reais. "
        "Desative para ocultar os registros marcados como demonstração."
    ),
)
st.sidebar.caption(
    "Dados fictícios são exemplos gerados pelo projeto. A seleção não altera o banco de dados."
)
st.sidebar.divider()
st.sidebar.caption("Dados operacionais no PostgreSQL e cotações no MongoDB.")

df = df_todas.copy()
if not df.empty:
    df = df[df["ramo"].isin(filtro_ramos)]
    df = df[df["status"].isin(filtro_status)]
    df = df[
        df["criado_em"].notna()
        & (df["criado_em"].dt.date >= data_inicio)
        & (df["criado_em"].dt.date <= data_fim)
    ]
    if not incluir_sinteticos:
        df = df[~df["sintetica"]]
    df = df.sort_values("criado_em", ascending=False).reset_index(drop=True)

if not filtro_ramos:
    st.warning("Selecione ao menos um ramo na barra lateral.")
    st.stop()

try:
    dados_relacionais = carregar_dados_relacionais(
        tuple(sorted(filtro_ramos)),
        data_inicio,
        data_fim,
        incluir_sinteticos,
    )
except ProgrammingError:
    LOGGER.exception("O esquema PostgreSQL está incompatível com as consultas do painel.")
    st.error(
        "O PostgreSQL está acessível, mas falta uma tabela ou coluna do projeto. "
        "Execute `python manage.py migrate` no terminal e reinicie o painel."
    )
    st.stop()
except DatabaseError:
    LOGGER.exception("Falha ao carregar os indicadores do PostgreSQL.")
    st.error(
        "Não foi possível consultar o PostgreSQL. Verifique se o serviço está ativo, "
        "as configurações DB_* e os detalhes no terminal."
    )
    st.stop()

apolices = dados_relacionais["apolices_ativas"]
comissao_anual = sum(
    float(apolice["valor_comissao"] or 0)
    for apolice in apolices
)
df_receitas = pd.DataFrame(dados_relacionais["comissoes_mensais"])
receita_media_mensal = None
liquido_medio_mensal = None
receitas_por_mes = pd.DataFrame()
if not df_receitas.empty:
    df_receitas["comissao_bruta"] = pd.to_numeric(df_receitas["comissao_bruta"], errors="coerce")
    df_receitas["percentual_liquido_estimado"] = pd.to_numeric(
        df_receitas["percentual_liquido_estimado"], errors="coerce"
    )
    df_receitas["liquido_estimado"] = (
        df_receitas["comissao_bruta"] * df_receitas["percentual_liquido_estimado"] / 100
    )
    receitas_por_mes = (
        df_receitas.groupby("mes_referencia", as_index=False)
        .agg(
            comissao_bruta=("comissao_bruta", "sum"),
            liquido_estimado=("liquido_estimado", "sum"),
        )
        .sort_values("mes_referencia")
    )
    inicio_mes = pd.Timestamp(data_inicio.year, data_inicio.month, 1)
    fim_mes = pd.Timestamp(data_fim.year, data_fim.month, 1)
    meses_selecionados = pd.date_range(inicio_mes, fim_mes, freq="MS")
    receitas_por_mes["mes_referencia"] = pd.to_datetime(
        receitas_por_mes["mes_referencia"]
    )
    receitas_por_mes = (
        receitas_por_mes.set_index("mes_referencia")
        .reindex(meses_selecionados, fill_value=0)
        .rename_axis("mes_referencia")
        .reset_index()
    )
    receita_media_mensal = receitas_por_mes["comissao_bruta"].mean()
    liquido_medio_mensal = receitas_por_mes["liquido_estimado"].mean()
taxa_retencao = calcular_taxa_retencao(
    dados_relacionais["renovacoes_concluidas"],
    dados_relacionais["renovacoes_elegiveis"],
)
ids_fechados = set(dados_relacionais["ids_cotacoes_fechadas"])
cotacoes_fechadas = int(df["id"].isin(ids_fechados).sum()) if not df.empty else 0
taxa_conversao = cotacoes_fechadas / len(df) * 100 if not df.empty else 0
pareceres_aprovados = int((df["status"] == "Aprovada").sum()) if not df.empty else 0
taxa_aprovacao_ia = pareceres_aprovados / len(df) * 100 if not df.empty else 0
valores_bens = pd.to_numeric(
    df.loc[df["ramo"] != "saude", "valor_bem"], errors="coerce"
).dropna()
valores_bens = valores_bens[valores_bens > 0]
mediana_valor_bens = valores_bens.median() if not valores_bens.empty else None
percentual_auditavel = df["auditavel"].astype(bool).mean() * 100 if not df.empty else None

st.markdown(
    f"""
    <section class="hero">
      <div class="hero-kicker">CRM Frank Costa Corretora</div>
      <h1>📊 Painel Estatístico e Analítico — CRM Frank Costa</h1>
      <p>Explore e compreenda os dados de simulações, IA Simbólica e carteira de forma clara e interativa.</p>
      <div class="hero-meta">Frank Costa Corretora de Seguros &nbsp;·&nbsp;
        Dados atualizados em {datetime.now().strftime("%d/%m/%Y às %H:%M")}
      </div>
    </section>
    """,
    unsafe_allow_html=True,
)
st.caption(
    f"Período: {MESES[data_inicio.month - 1].capitalize()} de {data_inicio.year} a "
    f"{MESES[data_fim.month - 1].capitalize()} de {data_fim.year} "
    f"· Ramos: {', '.join(RAMOS.get(ramo, ramo) for ramo in filtro_ramos)}"
)

kpis_principais = st.columns(4)
kpis_principais[0].metric(
    "Total de Simulações Registradas", f"{len(df):,}",
    delta="Dados atualizados",
    help="Cotações no período, ramos e pareceres selecionados.",
)
kpis_principais[1].metric(
    "Mediana do Valor dos Bens",
    formatar_moeda(mediana_valor_bens) if mediana_valor_bens is not None else "Sem base",
    help="Mediana dos valores positivos dos ramos com bem ou capital segurado; Saúde é excluída.",
)
kpis_principais[2].metric(
    "Taxa de Aprovação da IA Simbólica",
    f"{taxa_aprovacao_ia:.1f}%" if not df.empty else "Sem base",
    help="Percentual de pareceres com status Aprovada nas simulações filtradas.",
)
kpis_principais[3].metric(
    "Auditabilidade LGPD (Art. 20)",
    f"{percentual_auditavel:.1f}%" if percentual_auditavel is not None else "Sem base",
    help="Simulações com trilha de inferência ou registro de regra e motivo para auditoria.",
)

st.caption(
    "A mediana é adotada como indicador oficial de tendência central por ser imune a "
    "distorções causadas por veículos de alto valor (outliers)."
)

tab_cotacoes, tab_carteira, tab_renovacoes = st.tabs(
    ["Análise estatística", "Carteira & comissões", "Renovações"]
)

with tab_cotacoes:
    if df.empty:
        st.info("Nenhuma cotação encontrada com os filtros atuais. Amplie o período ou revise os filtros.")
    else:
        por_status = df.groupby("status").size().reset_index(name="Simulações")
        por_ramo = df.groupby("ramo").size().reset_index(name="Simulações")
        por_ramo["Ramo"] = por_ramo["ramo"].map(RAMOS).fillna(por_ramo["ramo"])

        esquerda, direita = st.columns(2)
        with esquerda:
            with st.container(border=True):
                st.markdown('<div class="section-heading">📌 Distribuição dos Pareceres da IA Simbólica</div>', unsafe_allow_html=True)
                st.markdown('<div class="section-note">Variável qualitativa nominal: decisões registradas pelo motor simbólico.</div>', unsafe_allow_html=True)
                fig_status = px.pie(
                    por_status,
                    names="status",
                    values="Simulações",
                    hole=.66,
                    color="status",
                    color_discrete_map=CORES_STATUS,
                )
                fig_status.update_traces(
                    textposition="inside",
                    textinfo="percent",
                    pull=[0.08 if status == "Aprovada" else 0 for status in por_status["status"]],
                    hovertemplate="%{label}<br>%{value} simulações (%{percent})<extra></extra>",
                )
                fig_status.add_annotation(
                    text=f"<b>{len(df):,}</b><br>Total", showarrow=False,
                    font=dict(size=19, color=CORES["navy"]),
                )
                aplicar_estilo_grafico(fig_status, 335)
                fig_status.update_layout(showlegend=True, legend=dict(orientation="v", x=.92, y=.5))
                st.plotly_chart(fig_status, width="stretch", config={"displayModeBar": False})
        with direita:
            with st.container(border=True):
                st.markdown('<div class="section-heading">📊 Contagem de Ocorrências por Ramo / Categoria</div>', unsafe_allow_html=True)
                st.markdown('<div class="section-note">Variável quantitativa discreta: frequência de simulações por ramo.</div>', unsafe_allow_html=True)
                fig_ramos = px.bar(
                    por_ramo.sort_values("Ramo"),
                    x="Ramo",
                    y="Simulações",
                    text="Simulações",
                    color_discrete_sequence=[CORES["brand"]],
                )
                fig_ramos.update_traces(textposition="outside", cliponaxis=False)
                fig_ramos.update_yaxes(title="Frequência", rangemode="tozero")
                fig_ramos.update_xaxes(title=None)
                aplicar_estilo_grafico(fig_ramos, 335)
                st.plotly_chart(fig_ramos, width="stretch", config={"displayModeBar": False})

        bens_com_valor = df.loc[
            (df["ramo"] != "saude") & df["valor_bem"].notna() & (df["valor_bem"] > 0)
        ].copy()
        premios_validos = df.loc[
            ~df["status"].isin({"Recusada", "Não Coberto"})
            & df["premio"].notna()
            & (df["premio"] > 0)
        ].copy()

        esquerda, direita = st.columns(2)
        with esquerda:
            with st.container(border=True):
                st.markdown('<div class="section-heading">〽 Análise Quantitativa Contínua</div>', unsafe_allow_html=True)
                aba_histograma, aba_boxplot = st.tabs(["Histograma do Valor dos Bens", "Boxplot dos Prêmios"])
                with aba_histograma:
                    if bens_com_valor.empty:
                        st.info("Não há valores positivos de bens ou capitais segurados para os filtros atuais.")
                    else:
                        media_bens = bens_com_valor["valor_bem"].mean()
                        mediana_bens = bens_com_valor["valor_bem"].median()
                        amplitude = bens_com_valor["valor_bem"].max() - bens_com_valor["valor_bem"].min()
                        numero_faixas = max(1, math.ceil(amplitude / 20_000))
                        fig_histograma = px.histogram(
                            bens_com_valor,
                            x="valor_bem",
                            nbins=numero_faixas,
                            labels={"valor_bem": "Valor do bem / capital segurado (R$)", "count": "Simulações"},
                            color_discrete_sequence=[CORES["brand"]],
                            hover_data={"cliente": True, "ramo": True, "valor_bem": ":,.2f"},
                        )
                        fig_histograma.update_traces(marker_line_color="#ffffff", marker_line_width=1)
                        fig_histograma.add_vline(
                            x=media_bens, line_dash="dash", line_color=CORES["orange"],
                            annotation_text=f"Média {formatar_moeda(media_bens)}", annotation_position="top left",
                        )
                        fig_histograma.add_vline(
                            x=mediana_bens, line_dash="dot", line_color=CORES["blue"],
                            annotation_text=f"Mediana {formatar_moeda(mediana_bens)}", annotation_position="top right",
                        )
                        fig_histograma.update_xaxes(tickprefix="R$ ", tickformat=",.0f")
                        fig_histograma.update_yaxes(title="Frequência", rangemode="tozero")
                        aplicar_estilo_grafico(fig_histograma, 345)
                        fig_histograma.update_layout(margin=dict(l=12, r=12, t=65, b=12), bargap=.05)
                        st.plotly_chart(fig_histograma, width="stretch", config={"displayModeBar": False})
                        st.caption("Faixas aproximadas de R$ 20 mil; Saúde é excluída por não possuir bem físico.")
                with aba_boxplot:
                    if premios_validos.empty:
                        st.info("Não há prêmios positivos e não recusados para os filtros atuais.")
                    else:
                        premios_validos["Ramo"] = premios_validos["ramo"].map(RAMOS).fillna(premios_validos["ramo"])
                        fig_box = px.box(
                            premios_validos, x="Ramo", y="premio", color="Ramo", points="outliers",
                            hover_data={"cliente": True, "status": True, "premio": ":,.2f"},
                            labels={"premio": "Prêmio bruto calculado (R$)"},
                            color_discrete_sequence=[CORES["brand"], CORES["blue"], CORES["purple"]],
                        )
                        fig_box.update_traces(boxmean=False, quartilemethod="linear")
                        fig_box.update_yaxes(title="Prêmio bruto calculado (R$)", tickprefix="R$ ", tickformat=",.2f")
                        aplicar_estilo_grafico(fig_box, 285)
                        st.plotly_chart(fig_box, width="stretch", config={"displayModeBar": False})
                        q1, q2, q3 = premios_validos["premio"].quantile([.25, .5, .75])
                        coluna_q1, coluna_q2, coluna_q3 = st.columns(3)
                        coluna_q1.metric("Q1", formatar_moeda(q1))
                        coluna_q2.metric("Mediana (Q2)", formatar_moeda(q2))
                        coluna_q3.metric("Q3", formatar_moeda(q3))

        with direita:
            with st.container(border=True):
                st.markdown('<div class="section-heading">∑ Tabela de Frequências Acumuladas</div>', unsafe_allow_html=True)
                st.markdown('<div class="section-note">Seção 8.2: distribuição de frequência dos valores segurados.</div>', unsafe_allow_html=True)
                if bens_com_valor.empty:
                    st.info("A tabela requer valores positivos de bens ou capitais segurados.")
                    tabela_frequencia = pd.DataFrame()
                else:
                    minimo = int(bens_com_valor["valor_bem"].min() // 20_000) * 20_000
                    maximo = (int(bens_com_valor["valor_bem"].max() // 20_000) + 1) * 20_000
                    limites = list(range(minimo, maximo + 20_000, 20_000))
                    faixas = pd.cut(bens_com_valor["valor_bem"], bins=limites, right=False, include_lowest=True)
                    frequencia = faixas.value_counts(sort=False)
                    tabela_frequencia = pd.DataFrame({"Faixa de Valor (R$)": frequencia.index.map(lambda faixa: f"{formatar_moeda(faixa.left)} – {formatar_moeda(faixa.right)}"), "Frequência (fi)": frequencia.values})
                    tabela_frequencia["Frequência Acumulada (Fi)"] = tabela_frequencia["Frequência (fi)"].cumsum()
                    tabela_frequencia["% Relativo (fri)"] = (tabela_frequencia["Frequência (fi)"] / len(bens_com_valor) * 100).map(lambda valor: f"{valor:.1f}%")
                    tabela_frequencia["% Acumulado"] = (tabela_frequencia["Frequência (fi)"].cumsum() / len(bens_com_valor) * 100).map(lambda valor: f"{valor:.1f}%")
                    st.dataframe(tabela_frequencia, hide_index=True, width="stretch", height=345)

        with st.container(border=True):
            st.markdown('<div class="section-heading">💡 Principais Insights</div>', unsafe_allow_html=True)
            insight_1, insight_2, insight_3, insight_exportar = st.columns([1.2, 1.1, 1.1, .9])
            if bens_com_valor.empty:
                texto_concentracao = "Não há valores de bens suficientes para indicar uma faixa predominante."
            else:
                faixa_principal = tabela_frequencia.loc[tabela_frequencia["Frequência (fi)"].idxmax(), "Faixa de Valor (R$)"]
                texto_concentracao = f"Maior concentração de propostas: {faixa_principal}."
            insight_1.markdown(f"**Distribuição**  \n{texto_concentracao}")
            insight_2.markdown(f"**IA Simbólica**  \n{taxa_aprovacao_ia:.1f}% dos pareceres estão aprovados.")
            insight_3.markdown(f"**LGPD Art. 20**  \n{percentual_auditavel:.1f}% das decisões têm trilha explicável." if percentual_auditavel is not None else "**LGPD Art. 20**  \nSem registros no filtro.")
            tabela_exportacao = formatar_tabela_cotacoes(df, ids_fechados)
            insight_exportar.download_button(
                "Exportar relatório CSV",
                data=tabela_exportacao.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"relatorio_cotacoes_{data_inicio:%Y%m%d}_{data_fim:%Y%m%d}.csv",
                mime="text/csv",
                icon=":material/download:",
                width="stretch",
            )

with tab_carteira:
    st.markdown('<div class="section-heading">Carteira vigente</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-note">Contratos ativos e comissões do PostgreSQL, por ramo e seguradora.</div>',
        unsafe_allow_html=True,
    )
    st.metric("Comissão anual registrada na carteira", formatar_moeda(comissao_anual))
    st.metric(
        "Comissão Mensal Estimada",
        formatar_moeda(comissao_anual / 12),
        help="Estimativa mensal calculada pela comissão anual das apólices vigentes dividida por 12.",
    )
    comissao_por_ramo = pd.DataFrame(dados_relacionais["comissoes_por_ramo"])
    comissao_por_seguradora = pd.DataFrame(dados_relacionais["comissoes_por_seguradora"])
    esquerda, direita = st.columns(2)
    with esquerda:
        st.markdown('<div class="section-heading">Comissão anual por ramo</div>', unsafe_allow_html=True)
        if comissao_por_ramo.empty:
            st.info("Não há apólices vigentes nos ramos selecionados.")
        else:
            comissao_por_ramo["Ramo"] = comissao_por_ramo["bem__tipo"].map(RAMOS).fillna(
                comissao_por_ramo["bem__tipo"]
            )
            comissao_por_ramo["Comissão anual"] = comissao_por_ramo["total"].astype(float)
            fig_comissao = px.bar(
                comissao_por_ramo,
                x="Ramo",
                y="Comissão anual",
                text=comissao_por_ramo["Comissão anual"].map(formatar_moeda),
                color_discrete_sequence=[CORES["brand"]],
            )
            fig_comissao.update_traces(textposition="outside", cliponaxis=False)
            aplicar_estilo_grafico(fig_comissao, 310)
            fig_comissao.update_yaxes(title=None, tickprefix="R$ ", separatethousands=True)
            st.plotly_chart(fig_comissao, width="stretch", config={"displayModeBar": False})
    with direita:
        st.markdown('<div class="section-heading">Comissão por seguradora</div>', unsafe_allow_html=True)
        if comissao_por_seguradora.empty:
            st.info("Sem comissões disponíveis para os filtros atuais.")
        else:
            comissao_por_seguradora["Comissão anual"] = comissao_por_seguradora["total"].astype(float)
            fig_seguradora = px.bar(
                comissao_por_seguradora,
                x="Comissão anual",
                y="seguradora__nome",
                orientation="h",
                text=comissao_por_seguradora["Comissão anual"].map(formatar_moeda),
                color_discrete_sequence=[CORES["brand_dark"]],
                labels={"seguradora__nome": "Seguradora"},
            )
            fig_seguradora.update_traces(textposition="outside", cliponaxis=False)
            aplicar_estilo_grafico(fig_seguradora, 310)
            fig_seguradora.update_xaxes(title=None, showgrid=True, gridcolor="#edf1ef")
            fig_seguradora.update_yaxes(title=None, showgrid=False, autorange="reversed")
            st.plotly_chart(fig_seguradora, width="stretch", config={"displayModeBar": False})
    st.markdown('<div class="section-heading">Apólices ativas</div>', unsafe_allow_html=True)
    if not apolices:
        st.info("Não há apólices ativas nos ramos selecionados.")
    else:
        tabela_apolices = pd.DataFrame(apolices).rename(columns={
            "numero_apolice": "Apólice",
            "cliente__nome": "Cliente",
            "bem__tipo": "ramo",
            "seguradora__nome": "Seguradora",
            "valor_premio": "Prêmio anual",
            "valor_comissao": "Comissão anual",
            "data_inicio": "Início",
            "data_fim": "Vencimento",
        })
        tabela_apolices["Ramo"] = tabela_apolices["ramo"].map(RAMOS).fillna(tabela_apolices["ramo"])
        tabela_apolices["Prêmio anual"] = tabela_apolices["Prêmio anual"].map(
            lambda valor: formatar_moeda(float(valor))
        )
        tabela_apolices["Comissão anual"] = tabela_apolices["Comissão anual"].map(
            lambda valor: formatar_moeda(float(valor))
        )
        tabela_apolices["Vencimento"] = pd.to_datetime(
            tabela_apolices["Vencimento"], errors="coerce"
        ).dt.strftime("%d/%m/%Y")
        tabela_apolices = tabela_apolices[
            ["Apólice", "Cliente", "Ramo", "Seguradora", "Prêmio anual", "Comissão anual", "Vencimento"]
        ]
        busca_apolice = st.text_input(
            "Buscar apólice por cliente, número ou seguradora",
            placeholder="Digite para localizar",
            key="busca_apolice_dashboard",
        )
        if busca_apolice.strip():
            corresponde = tabela_apolices.astype(str).apply(
                lambda coluna: coluna.str.contains(busca_apolice.strip(), case=False, na=False)
            ).any(axis=1)
            tabela_apolices = tabela_apolices[corresponde]
        st.table(tabela_apolices.head(100))
        st.caption(f"Exibindo até 100 apólices de {len(tabela_apolices):,} encontradas.")
    st.caption(
        "A comissão anual da carteira é calculada a partir das apólices ativas; "
        "os valores não representam necessariamente o caixa recebido em cada mês."
    )

with tab_renovacoes:
    st.markdown('<div class="section-heading">Acompanhamento de renovações</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-note">Decisões registradas no histórico de apólices, no período e ramos selecionados.</div>',
        unsafe_allow_html=True,
    )
    coluna_renovacao = st.columns(4)
    coluna_renovacao[0].metric("Com decisão", dados_relacionais["renovacoes_elegiveis"])
    coluna_renovacao[1].metric("Renovadas", dados_relacionais["renovacoes_concluidas"])
    nao_renovadas = (
        dados_relacionais["renovacoes_elegiveis"] - dados_relacionais["renovacoes_concluidas"]
    )
    coluna_renovacao[2].metric("Não renovadas", nao_renovadas)
    coluna_renovacao[3].metric(
        "Retenção",
        f"{taxa_retencao:.1f}%" if taxa_retencao is not None else "Sem base",
    )
    if not dados_relacionais["historico_renovacoes"]:
        st.info("Não há renovações decididas no período para os ramos selecionados.")
    else:
        resumo_renovacao = pd.DataFrame(dados_relacionais["historico_renovacoes"])
        resumo_renovacao["Status"] = resumo_renovacao["status"].map({
            "renovada": "Renovada",
            "nao_renovada": "Não renovada",
        })
        resumo_renovacao["Ramo"] = resumo_renovacao["apolice__bem__tipo"].map(RAMOS).fillna(
            resumo_renovacao["apolice__bem__tipo"]
        )
        resumo_renovacao = resumo_renovacao.rename(columns={
            "data_vencimento": "Vencimento",
            "apolice__numero_apolice": "Apólice",
            "apolice__cliente__nome": "Cliente",
        })
        resumo_renovacao["Vencimento"] = pd.to_datetime(
            resumo_renovacao["Vencimento"], errors="coerce"
        ).dt.strftime("%d/%m/%Y")
        st.table(resumo_renovacao[["Vencimento", "Cliente", "Ramo", "Apólice", "Status"]].head(100))
        st.caption(
            "Retenção = apólices renovadas ÷ apólices elegíveis com decisão. "
            "Pendências são excluídas do cálculo."
        )

if atingiu_limite:
    st.warning(
        f"Para manter o painel responsivo, foram carregadas as {LIMITE_COTACOES:,} cotações mais recentes. "
        "Refine o período para analisar um intervalo menor."
    )
st.caption(
    "Frank Costa Corretora de Seguros · Indicadores para gestão · "
    "Dados sintéticos de demonstração devem ser interpretados como cenário acadêmico."
)
