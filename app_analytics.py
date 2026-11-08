import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import django
import pandas as pd
import plotly.express as px
import streamlit as st
from django.db import DatabaseError, ProgrammingError
from django.db.models import Sum
from pymongo import MongoClient
from pymongo.errors import PyMongoError


BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "crm_core.settings")
django.setup()

from django.conf import settings
from cotacoes.analytics import PARECERES_FAVORAVEIS, calcular_taxa_retencao
from cotacoes.models import Apolice, Cliente, RenovacaoApolice


LOGGER = logging.getLogger(__name__)
RAMOS = {
    "auto": "Automóvel",
    "vida": "Vida",
    "saude": "Saúde",
    "residencial": "Residencial (histórico)",
}
MARGEM_LIQUIDA_ESTIMADA = 0.75

st.set_page_config(
    page_title="Painel Gerencial | Frank Costa",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        --brand: #1e8a56;
        --brand-dark: #146b41;
        --ink: #1f2937;
        --muted: #6b7280;
        --surface: #ffffff;
        --page: #f5f7f5;
    }
    .stApp { background: var(--page); color: var(--ink); }
    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid #e5e7eb; }
    .block-container { max-width: 1440px; padding-top: 2rem; padding-bottom: 3rem; }
    .brand-mark {
        color: var(--brand-dark); font-size: 1.05rem; font-weight: 800;
        letter-spacing: .08em; text-transform: uppercase;
    }
    .hero {
        background: linear-gradient(120deg, #ffffff 35%, #e7f5ec 100%);
        border: 1px solid #dfe9e2; border-radius: 18px;
        padding: 1.5rem 1.75rem; margin-bottom: 1.25rem;
    }
    .hero-kicker { color: var(--brand-dark); font-size: .75rem; font-weight: 700;
        letter-spacing: .12em; text-transform: uppercase; margin-bottom: .35rem; }
    .hero h1 { color: var(--ink); font-size: 1.8rem; margin: 0; }
    .hero p { color: var(--muted); margin: .45rem 0 0; }
    div[data-testid="stMetric"] {
        background: var(--surface); border: 1px solid #e5e7eb;
        border-top: 3px solid var(--brand); border-radius: 12px;
        padding: 1rem 1.15rem; box-shadow: 0 2px 8px rgba(31, 41, 55, .04);
    }
    div[data-testid="stMetricLabel"] p { color: var(--muted); font-weight: 600; }
    div[data-testid="stMetricValue"] { color: var(--brand-dark); font-weight: 750; }
    div[data-testid="stTabs"] button[aria-selected="true"] { color: var(--brand-dark); }
    .stCaption { color: var(--muted); }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_mongo_collection():
    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
    return client[settings.MONGO_DB_NAME]["cotacoes"]


@st.cache_data(ttl=60)
def carregar_cotacoes():
    collection = get_mongo_collection()
    collection.database.client.admin.command("ping")
    return list(collection.find().sort("criado_em", -1).limit(1000))


@st.cache_data(ttl=60)
def carregar_dados_relacionais(data_inicio, hoje):
    clientes_ativos = Cliente.objects.filter(ativo=True).count()
    apolices_ativas = list(
        Apolice.objects.filter(status="ativa")
        .values("bem__tipo", "valor_premio", "valor_comissao", "data_inicio", "data_fim")
    )
    renovacoes = RenovacaoApolice.objects.filter(
        data_vencimento__gte=data_inicio,
        data_vencimento__lte=hoje,
        status__in=["renovada", "nao_renovada"],
    )
    elegiveis = renovacoes.count()
    renovadas = renovacoes.filter(status="renovada").count()
    comissoes_por_ramo = list(
        Apolice.objects.filter(status="ativa")
        .values("bem__tipo")
        .annotate(total=Sum("valor_comissao"))
    )
    ids_cotacoes_fechadas = list(
        Apolice.objects.exclude(cotacao_mongo_id="")
        .values_list("cotacao_mongo_id", flat=True)
    )
    return {
        "clientes_ativos": clientes_ativos,
        "apolices_ativas": apolices_ativas,
        "comissoes_por_ramo": comissoes_por_ramo,
        "ids_cotacoes_fechadas": ids_cotacoes_fechadas,
        "renovacoes_elegiveis": elegiveis,
        "renovacoes_concluidas": renovadas,
    }


def preparar_cotacoes(documentos):
    linhas = []
    for documento in documentos:
        dados = documento.get("dados") or documento.get("dados_bem") or {}
        calculo = documento.get("resultado_calculo") or {}
        parecer = documento.get("parecer_ia") or {}
        linhas.append({
            "id": str(documento.get("_id", "")),
            "ramo": documento.get("tipo_seguro", "desconhecido"),
            "premio_anual": calculo.get("premio_bruto") or calculo.get("premio"),
            "status": parecer.get("status", "Análise pendente"),
            "criado_em": documento.get("criado_em"),
            "origem": dados.get("origem_dados", ""),
        })
    return pd.DataFrame(linhas, columns=[
        "id", "ramo", "premio_anual", "status", "criado_em", "origem"
    ])


st.sidebar.markdown('<div class="brand-mark">Frank Costa</div>', unsafe_allow_html=True)
st.sidebar.caption("Corretora de Seguros · Painel gerencial")
st.sidebar.markdown("---")
st.sidebar.subheader("Filtros")
filtro_ramos = st.sidebar.multiselect(
    "Ramos",
    options=["auto", "vida", "saude", "residencial"],
    default=["auto", "vida", "saude"],
    format_func=lambda ramo: RAMOS[ramo],
)
st.sidebar.caption("Os registros gerados pelo projeto são dados sintéticos de demonstração.")

st.markdown(
    """
    <section class="hero">
      <div class="hero-kicker">Gestão da carteira</div>
      <h1>Visão gerencial da Frank Costa</h1>
      <p>Apólices, comissões, cotações e renovações em um só painel.</p>
    </section>
    """,
    unsafe_allow_html=True,
)

hoje = date.today()
inicio_janela = hoje - timedelta(days=365)
try:
    documentos = carregar_cotacoes()
except PyMongoError:
    LOGGER.exception("Falha ao carregar as cotações do MongoDB.")
    st.error("Não foi possível conectar ao MongoDB. Verifique a configuração MONGO_URI.")
    st.stop()

try:
    dados_relacionais = carregar_dados_relacionais(inicio_janela, hoje)
except ProgrammingError:
    LOGGER.exception("O esquema PostgreSQL está incompatível com as consultas do painel.")
    st.error(
        "O PostgreSQL está acessível, mas falta uma tabela ou coluna do projeto. "
        "No terminal do projeto, execute `python manage.py migrate` e reinicie o painel."
    )
    st.stop()
except DatabaseError:
    LOGGER.exception("Falha ao carregar os indicadores do PostgreSQL.")
    st.error(
        "Não foi possível consultar o PostgreSQL. Verifique se o serviço está ativo, "
        "as configurações DB_* e os detalhes no terminal."
    )
    st.stop()

df = preparar_cotacoes(documentos)
if not df.empty:
    df = df[df["ramo"].isin(filtro_ramos)].copy()
    df["premio_anual"] = pd.to_numeric(df["premio_anual"], errors="coerce")

apolices = dados_relacionais["apolices_ativas"]
comissao_anual = sum(float(apolice["valor_comissao"]) for apolice in apolices)
comissao_mensal = comissao_anual / 12
lucro_liquido_mensal_estimado = comissao_mensal * MARGEM_LIQUIDA_ESTIMADA
taxa_retencao = calcular_taxa_retencao(
    dados_relacionais["renovacoes_concluidas"],
    dados_relacionais["renovacoes_elegiveis"],
)
ids_fechados = set(dados_relacionais["ids_cotacoes_fechadas"])
cotacoes_fechadas = df["id"].isin(ids_fechados).sum() if not df.empty else 0
taxa_conversao = cotacoes_fechadas / len(df) * 100 if not df.empty else 0
pareceres_favoraveis = df["status"].isin(PARECERES_FAVORAVEIS).sum() if not df.empty else 0
taxa_favoravel = pareceres_favoraveis / len(df) * 100 if not df.empty else 0

kpis = st.columns(5)
kpis[0].metric("Clientes ativos", f"{dados_relacionais['clientes_ativos']:,}")
kpis[1].metric("Apólices vigentes", f"{len(apolices):,}")
kpis[2].metric("Comissão média mensal", f"R$ {comissao_mensal:,.2f}")
kpis[3].metric("Lucro líquido estimado", f"R$ {lucro_liquido_mensal_estimado:,.2f}")
kpis[4].metric(
    "Retenção em 12 meses",
    f"{taxa_retencao:.1f}%" if taxa_retencao is not None else "Sem base",
    help=(
        f"{dados_relacionais['renovacoes_concluidas']} renovadas de "
        f"{dados_relacionais['renovacoes_elegiveis']} apólices elegíveis."
    ),
)
st.caption(
    "Comissão mensal = comissão anualizada das apólices ativas ÷ 12. "
    "Lucro líquido é uma estimativa com a margem de 75% do relatório acadêmico, não um valor contábil."
)
st.info(
    "Base demonstrativa sintética. A composição por ramo e os valores não representam "
    "dados reais de clientes ou contratos."
)

tab_cotacoes, tab_carteira, tab_renovacoes = st.tabs(
    ["Cotações e conversão", "Carteira e comissões", "Renovações"]
)

with tab_cotacoes:
    col1, col2, col3 = st.columns(3)
    col1.metric("Cotações no filtro", f"{len(df):,}")
    col2.metric("Conversão em apólice", f"{taxa_conversao:.1f}%")
    col3.metric("Pareceres favoráveis", f"{taxa_favoravel:.1f}%")
    if df.empty:
        st.info("Não há cotações para os filtros selecionados.")
    else:
        df["ramo_legenda"] = df["ramo"].map(RAMOS).fillna(df["ramo"])
        g1, g2 = st.columns(2)
        with g1:
            st.subheader("Volume por ramo")
            por_ramo = df.groupby("ramo_legenda").size().reset_index(name="Cotações")
            fig_ramos = px.bar(
                por_ramo, x="ramo_legenda", y="Cotações",
                color_discrete_sequence=["#1e8a56"],
                labels={"ramo_legenda": "Ramo"},
            )
            fig_ramos.update_layout(showlegend=False, margin=dict(t=20, b=20))
            st.plotly_chart(fig_ramos, use_container_width=True)
        with g2:
            st.subheader("Distribuição dos pareceres")
            por_status = df.groupby("status").size().reset_index(name="Cotações")
            fig_status = px.pie(
                por_status, names="status", values="Cotações", hole=0.55,
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            fig_status.update_layout(margin=dict(t=20, b=20), legend_title_text="")
            st.plotly_chart(fig_status, use_container_width=True)

        com_premio = df.dropna(subset=["premio_anual"])
        if not com_premio.empty:
            st.subheader("Prêmio anual estimado por ramo")
            fig_premios = px.box(
                com_premio,
                x="ramo_legenda",
                y="premio_anual",
                color="ramo_legenda",
                points="outliers",
                labels={
                    "ramo_legenda": "Ramo",
                    "premio_anual": "Prêmio anual estimado (R$)",
                },
                color_discrete_sequence=["#1e8a56", "#3b82f6", "#f59e0b", "#9ca3af"],
            )
            fig_premios.update_layout(showlegend=False, margin=dict(t=20, b=20))
            st.plotly_chart(fig_premios, use_container_width=True)

with tab_carteira:
    st.subheader("Comissão anualizada por ramo")
    df_comissoes = pd.DataFrame(dados_relacionais["comissoes_por_ramo"])
    if df_comissoes.empty:
        st.info("Ainda não há apólices ativas para compor as comissões.")
    else:
        df_comissoes["Ramo"] = df_comissoes["bem__tipo"].map(RAMOS).fillna(df_comissoes["bem__tipo"])
        df_comissoes["Comissão anual (R$)"] = df_comissoes["total"].astype(float)
        fig_comissoes = px.bar(
            df_comissoes,
            x="Ramo",
            y="Comissão anual (R$)",
            text_auto=".2s",
            color_discrete_sequence=["#1e8a56"],
        )
        fig_comissoes.update_layout(showlegend=False, margin=dict(t=20, b=20))
        st.plotly_chart(fig_comissoes, use_container_width=True)
    st.caption(
        "A comissão é calculada a partir das apólices vigentes no PostgreSQL; "
        "o valor mensal é uma média anualizada, não necessariamente o caixa recebido em cada mês."
    )

with tab_renovacoes:
    st.subheader("Retenção da carteira")
    if dados_relacionais["renovacoes_elegiveis"] == 0:
        st.info("Não há renovações concluídas ou não renovadas na janela dos últimos 12 meses.")
    else:
        col1, col2, col3 = st.columns(3)
        col1.metric("Elegíveis com decisão", dados_relacionais["renovacoes_elegiveis"])
        col2.metric("Renovadas", dados_relacionais["renovacoes_concluidas"])
        col3.metric("Taxa de retenção", f"{taxa_retencao:.1f}%")
        st.caption(
            "Fórmula: apólices renovadas ÷ apólices elegíveis com decisão de renovação "
            "nos últimos 12 meses. Pendências não entram no denominador."
        )
