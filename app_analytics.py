import logging
import os
import sys
import calendar
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
from cotacoes.analytics import (
    PARECERES_FAVORAVEIS,
    calcular_taxa_retencao,
    deslocar_mes,
)
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
    "brand": "#16845b",
    "brand_dark": "#086346",
    "mint": "#dff3ea",
    "navy": "#163b35",
    "ink": "#253a35",
    "muted": "#71827c",
    "line": "#e4ece8",
    "page": "#f4f7f5",
    "orange": "#e69a54",
    "blue": "#6d9fc6",
    "red": "#d97470",
    "purple": "#9279b7",
}
CORES_STATUS = {
    "Aprovada": "#16845b",
    "Aprovada com Fator de Risco": "#67aa83",
    "Cobertura Autorizada": "#67aa83",
    "Atendimento Liberado": "#67aa83",
    "Análise Manual": "#e69a54",
    "Análise Médica ou Manual": "#e69a54",
    "Necessita de Vistoria": "#e69a54",
    "Pendência de Dados": "#d9b752",
    "Recusada": "#d97470",
    "Não Coberto": "#d97470",
    "Análise pendente": "#9ba9a4",
}
LIMITE_COTACOES = 10_000

st.set_page_config(
    page_title="Painel Gerencial | Frank Costa",
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
    [data-testid="stHeader"] {{ background: rgba(244,247,245,.94); }}
    [data-testid="stToolbar"], [data-testid="stStatusWidget"], #MainMenu, footer {{
        display:none !important;
    }}
    [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
        background:var(--page); color:var(--ink);
    }}
    [data-testid="stSidebar"] {{
        background: #fff;
        border-right: 1px solid var(--line);
    }}
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
        color:#344d44;
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
        background:linear-gradient(145deg,#2aa879,#086346);
        color:#fff; font-size:1.35rem; font-weight:800;
        box-shadow:0 6px 16px rgba(8,99,70,.18);
    }}
    .brand-name {{ color:#176f50; font-family:Georgia,serif; font-size:1.15rem;
        font-weight:700; letter-spacing:.09em; line-height:1.05; }}
    .brand-subtitle {{ color:#82918b; font-size:.58rem; letter-spacing:.28em;
        margin-top:.22rem; text-transform:uppercase; }}
    .hero {{
        position:relative; overflow:hidden;
        background:linear-gradient(115deg,#0c6a4c 0%,#16845b 58%,#28a477 100%);
        border-radius:1.2rem; padding:1.65rem 2rem;
        box-shadow:0 14px 32px rgba(9,94,66,.15);
        margin-bottom:1.25rem;
    }}
    .hero:after {{
        content:""; position:absolute; width:19rem; height:19rem; border-radius:50%;
        border:1px solid rgba(255,255,255,.14); right:5%; top:-12rem;
        box-shadow:0 0 0 2.4rem rgba(255,255,255,.035),0 0 0 5rem rgba(255,255,255,.025);
    }}
    .hero-kicker {{ color:#b9e8d5; font-size:.69rem; font-weight:700;
        letter-spacing:.16em; text-transform:uppercase; }}
    .hero h1 {{ color:white; font-size:1.8rem; font-weight:700;
        letter-spacing:-.025em; margin:.42rem 0 .35rem; }}
    .hero p {{ color:rgba(255,255,255,.83); font-size:.94rem; margin:0; }}
    .hero-meta {{ color:rgba(255,255,255,.75); font-size:.75rem;
        margin-top:.9rem; }}
    div[data-testid="stMetric"] {{
        background:#fff; border:1px solid var(--line); border-radius:.9rem;
        padding:1rem 1.1rem; box-shadow:0 5px 16px rgba(24,62,49,.045);
        min-height:7.1rem;
    }}
    div[data-testid="stMetricLabel"] p {{ color:#52675f !important; font-size:.79rem; font-weight:650; }}
    div[data-testid="stMetricValue"] {{ color:#176f50 !important; font-size:1.48rem; font-weight:750; }}
    div[data-testid="stMetricDelta"] {{ font-size:.73rem; }}
    div[data-testid="stTabs"] button {{ font-weight:650; }}
    div[data-testid="stTabs"] button[aria-selected="true"] {{
        color:var(--brand-dark); border-bottom-color:var(--brand);
    }}
    div[data-testid="stTabs"] button {{ color:#425a50; }}
    div[data-testid="stWidgetLabel"] p, label, .stMarkdown p, .stMarkdown h1,
    .stMarkdown h2, .stMarkdown h3, [data-testid="stCaptionContainer"] {{
        color:#40584f;
    }}
    [data-testid="stPills"] button {{ border-radius:999px; }}
    [data-testid="stPills"] button[aria-pressed="true"] {{
        background:#e4f3ec; border-color:#83bda2; color:#075f42;
    }}
    .section-heading {{ color:#183e35; font-size:1.05rem; font-weight:700;
        margin:.35rem 0 .2rem; }}
    .section-note {{ color:#82918b; font-size:.78rem; margin-bottom:.8rem; }}
    .data-note {{ background:#e9f4ef; border:1px solid #d5e9df;
        border-radius:.7rem; color:#356a56; padding:.7rem .9rem;
        font-size:.8rem; }}
    .stButton button, .stDownloadButton button {{
        border-radius:.65rem; font-weight:650;
    }}
    .stButton button[kind="primary"] {{
        background:#16845b; border-color:#16845b;
    }}
    .stCaption {{ color:#82918b; }}
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
    apolices_ativas_qs = (
        Apolice.objects.filter(status="ativa", bem__tipo__in=ramos)
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
        .annotate(total=Sum("valor_comissao"))
        .order_by("bem__tipo")
    )
    comissoes_por_seguradora = list(
        apolices_ativas_qs.values("seguradora__nome")
        .annotate(total=Sum("valor_comissao"))
        .order_by("-total")
    )
    clientes_na_carteira = (
        apolices_ativas_qs.filter(cliente__ativo=True)
        .values("cliente_id")
        .distinct()
        .count()
    )
    ids_cotacoes_fechadas = list(
        Apolice.objects.filter(bem__tipo__in=ramos)
        .exclude(cotacao_mongo_id="")
        .values_list("cotacao_mongo_id", flat=True)
    )
    renovacoes = RenovacaoApolice.objects.filter(
        data_vencimento__gte=data_inicio,
        data_vencimento__lte=data_fim,
        status__in=["renovada", "nao_renovada"],
        apolice__bem__tipo__in=ramos,
    )
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
    linhas = []
    for documento in documentos:
        dados = documento.get("dados") or documento.get("dados_bem") or {}
        calculo = documento.get("resultado_calculo") or {}
        parecer = documento.get("parecer_ia") or {}
        linhas.append({
            "id": str(documento.get("_id", "")),
            "cliente": nomes_clientes.get(documento.get("cliente_id"), "Cliente não localizado"),
            "ramo": documento.get("tipo_seguro", "desconhecido"),
            "premio": calculo.get("premio_bruto") or calculo.get("premio"),
            "status": traducao_status(parecer.get("status", "Análise pendente")),
            "criado_em": documento.get("criado_em"),
            "origem": dados.get("origem_dados", ""),
            "sintetica": dados.get("origem_dados") == "demonstracao_sintetica",
        })
    df = pd.DataFrame(linhas, columns=[
        "id", "cliente", "ramo", "premio", "status", "criado_em", "origem", "sintetica"
    ])
    if not df.empty:
        df["premio"] = pd.to_numeric(df["premio"], errors="coerce")
        df["criado_em"] = pd.to_datetime(df["criado_em"], errors="coerce", utc=True)
    return df


def formatar_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def primeiro_dia_do_mes(data_referencia, deslocamento=0):
    return deslocar_mes(date(data_referencia.year, data_referencia.month, 1), deslocamento)


def traducao_status(status):
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
comissao_anual = sum(float(apolice["valor_comissao"]) for apolice in apolices)
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
    receita_media_mensal = receitas_por_mes["comissao_bruta"].mean()
    liquido_medio_mensal = receitas_por_mes["liquido_estimado"].mean()
taxa_retencao = calcular_taxa_retencao(
    dados_relacionais["renovacoes_concluidas"],
    dados_relacionais["renovacoes_elegiveis"],
)
ids_fechados = set(dados_relacionais["ids_cotacoes_fechadas"])
cotacoes_fechadas = int(df["id"].isin(ids_fechados).sum()) if not df.empty else 0
taxa_conversao = cotacoes_fechadas / len(df) * 100 if not df.empty else 0
pareceres_favoraveis = int(df["status"].isin(PARECERES_FAVORAVEIS).sum()) if not df.empty else 0
taxa_favoravel = pareceres_favoraveis / len(df) * 100 if not df.empty else 0

st.markdown(
    f"""
    <section class="hero">
      <div class="hero-kicker">Gestão da carteira</div>
      <h1>Visão gerencial</h1>
      <p>Decisões mais claras para cuidar do que importa.</p>
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

kpis = st.columns(5)
kpis[0].metric("Clientes na carteira", f"{dados_relacionais['clientes_na_carteira']:,}")
kpis[1].metric("Apólices vigentes", f"{len(apolices):,}")
kpis[2].metric(
    "Comissão bruta média mensal",
    formatar_moeda(receita_media_mensal) if receita_media_mensal is not None else "Sem base",
    help="Média mensal do cenário demonstrativo no período e ramos selecionados.",
)
kpis[3].metric(
    "Líquido médio estimado",
    formatar_moeda(liquido_medio_mensal) if liquido_medio_mensal is not None else "Sem base",
    help="Comissão bruta demonstrativa × margem líquida estimada de 75%.",
)
kpis[4].metric(
    "Retenção de renovações",
    f"{taxa_retencao:.1f}%" if taxa_retencao is not None else "Sem base",
    help=(
        f"{dados_relacionais['renovacoes_concluidas']} renovadas de "
        f"{dados_relacionais['renovacoes_elegiveis']} decisões no período selecionado."
    ),
)
st.caption(
    "As receitas mensais são valores fictícios de demonstração entre R$ 6 mil e R$ 12 mil. "
    "O líquido é estimado com margem acadêmica de 75%; não representa resultado contábil."
)
st.markdown(
    '<div class="data-note">O período filtra cotações, receitas demonstrativas e renovações. '
    'A carteira e as apólices vigentes consideram os ramos selecionados.</div>',
    unsafe_allow_html=True,
)

st.markdown('<div class="section-heading">Comissão bruta mês a mês</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-note">Cenário fictício: com os três ramos selecionados, o total mensal foi gerado entre R$ 6 mil e R$ 12 mil. Com menos ramos, o gráfico mostra apenas o subtotal.</div>',
    unsafe_allow_html=True,
)
if receitas_por_mes.empty:
    st.info("Não há valores demonstrativos para o período e os ramos selecionados.")
else:
    receitas_por_mes["mes_label"] = receitas_por_mes["mes_referencia"].map(
        lambda mes: f"{MESES[mes.month - 1][:3].capitalize()}/{mes.year}"
    )
    fig_receita = px.area(
        receitas_por_mes,
        x="mes_referencia",
        y="comissao_bruta",
        markers=True,
        color_discrete_sequence=[CORES["brand"]],
        labels={"mes_referencia": "Mês", "comissao_bruta": "Comissão bruta"},
    )
    fig_receita.update_traces(
        fill="tozeroy",
        line=dict(width=3),
        fillcolor="rgba(22,132,91,.12)",
        marker=dict(size=6),
        customdata=[
            f"{mes} · Comissão bruta: {formatar_moeda(valor)}"
            for mes, valor in zip(
                receitas_por_mes["mes_label"], receitas_por_mes["comissao_bruta"]
            )
        ],
        hovertemplate="%{customdata}<extra></extra>",
    )
    aplicar_estilo_grafico(fig_receita, 285)
    fig_receita.update_xaxes(
        tickmode="array",
        tickvals=receitas_por_mes["mes_referencia"].tolist(),
        ticktext=receitas_por_mes["mes_label"].tolist(),
    )
    fig_receita.update_yaxes(
        title=None,
        tickprefix="R$ ",
        tickformat=",.0f",
        separatethousands=True,
    )
    st.plotly_chart(fig_receita, width="stretch", config={"displayModeBar": False})

tab_cotacoes, tab_carteira, tab_renovacoes = st.tabs(
    ["Cotações & conversão", "Carteira & comissões", "Renovações"]
)

with tab_cotacoes:
    st.markdown('<div class="section-heading">Desempenho comercial</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-note">Acompanhe volume, qualidade e conversão no período selecionado.</div>',
        unsafe_allow_html=True,
    )
    kpi_cotacoes = st.columns(4)
    kpi_cotacoes[0].metric("Cotações no período", f"{len(df):,}")
    kpi_cotacoes[1].metric("Negócios fechados", f"{cotacoes_fechadas:,}")
    kpi_cotacoes[2].metric("Conversão", f"{taxa_conversao:.1f}%")
    kpi_cotacoes[3].metric("Parecer favorável", f"{taxa_favoravel:.1f}%")

    if df.empty:
        st.info("Nenhuma cotação encontrada com os filtros atuais. Amplie o período ou revise os filtros.")
    else:
        esquerda, direita = st.columns([1.2, 1])
        with esquerda:
            st.markdown('<div class="section-heading">Evolução das cotações</div>', unsafe_allow_html=True)
            mensal = df.assign(
                mes=df["criado_em"].dt.tz_localize(None).dt.to_period("M").dt.to_timestamp()
            )
            mensal = mensal.groupby("mes").size().reset_index(name="Cotações")
            mensal["Mês"] = mensal["mes"].map(
                lambda mes: f"{MESES[mes.month - 1][:3].capitalize()}/{mes.year}"
            )
            fig_tempo = px.area(
                mensal,
                x="mes",
                y="Cotações",
                markers=True,
                color_discrete_sequence=[CORES["brand"]],
                labels={"mes": "Mês", "Cotações": "Cotações"},
            )
            fig_tempo.update_traces(
                fill="tozeroy",
                line=dict(width=3),
                fillcolor="rgba(22,132,91,.12)",
                marker=dict(size=6),
            )
            aplicar_estilo_grafico(fig_tempo, 320)
            fig_tempo.update_xaxes(
                tickmode="array",
                tickvals=mensal["mes"].tolist(),
                ticktext=mensal["Mês"].tolist(),
            )
            st.plotly_chart(fig_tempo, width="stretch", config={"displayModeBar": False})
        with direita:
            st.markdown('<div class="section-heading">Distribuição por ramo</div>', unsafe_allow_html=True)
            por_ramo = df.groupby("ramo").size().reset_index(name="Cotações")
            por_ramo["Ramo"] = por_ramo["ramo"].map(RAMOS).fillna(por_ramo["ramo"])
            fig_ramos = px.bar(
                por_ramo.sort_values("Cotações"),
                x="Cotações",
                y="Ramo",
                orientation="h",
                text="Cotações",
                color_discrete_sequence=[CORES["brand"]],
            )
            fig_ramos.update_traces(textposition="outside", cliponaxis=False)
            aplicar_estilo_grafico(fig_ramos, 320)
            fig_ramos.update_xaxes(showgrid=True, gridcolor="#edf1ef")
            fig_ramos.update_yaxes(showgrid=False)
            st.plotly_chart(fig_ramos, width="stretch", config={"displayModeBar": False})

        esquerda, direita = st.columns([1, 1.2])
        with esquerda:
            st.markdown('<div class="section-heading">Pareceres da análise</div>', unsafe_allow_html=True)
            por_status = df.groupby("status").size().reset_index(name="Cotações")
            fig_status = px.pie(
                por_status,
                names="status",
                values="Cotações",
                hole=.68,
                color="status",
                color_discrete_map=CORES_STATUS,
            )
            fig_status.update_traces(
                textposition="inside",
                textinfo="percent",
                hovertemplate="%{label}<br>%{value} cotações (%{percent})<extra></extra>",
            )
            aplicar_estilo_grafico(fig_status, 320)
            fig_status.update_layout(showlegend=True, legend=dict(orientation="h", y=-.12))
            st.plotly_chart(fig_status, width="stretch", config={"displayModeBar": False})
        with direita:
            st.markdown('<div class="section-heading">Cotações recentes</div>', unsafe_allow_html=True)
            tabela_completa = formatar_tabela_cotacoes(df, ids_fechados)
            busca_cotacao = st.text_input(
                "Buscar cotação por cliente",
                placeholder="Digite o nome do cliente",
                key="busca_cotacao_dashboard",
            )
            if busca_cotacao.strip():
                tabela_completa = tabela_completa[
                    tabela_completa["Cliente"].str.contains(
                        busca_cotacao.strip(), case=False, na=False
                    )
                ]
            tabela = tabela_completa.head(100)
            st.caption(
                f"Exibindo as {len(tabela):,} cotações mais recentes de {len(tabela_completa):,} no filtro."
            )
            st.table(tabela)
            csv = tabela_completa.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "Baixar cotações filtradas",
                data=csv,
                file_name=f"cotacoes_{data_inicio:%Y%m%d}_{data_fim:%Y%m%d}.csv",
                mime="text/csv",
                icon=":material/download:",
            )

with tab_carteira:
    st.markdown('<div class="section-heading">Carteira vigente</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-note">Contratos ativos e comissões do PostgreSQL, por ramo e seguradora.</div>',
        unsafe_allow_html=True,
    )
    st.metric("Comissão anual registrada na carteira", formatar_moeda(comissao_anual))
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
