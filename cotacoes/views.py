"""
views.py
--------
Camada de controle (MTV) que conecta a interface web às três peças de
negócio: cadastros (Postgres/models.py), cálculo + IA (motor_ia.py) e
persistência de cotações (Mongo/nosql.py).
"""

import json
import random
from datetime import date, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from .models import Cliente, Bem, Seguradora, Plano, Apolice
from . import motor_ia
from . import nosql
from .utils import somente_digitos


def home(request):
    """Landing page institucional (a tela que você já tinha pronta)."""
    return render(request, "cotacoes/home.html")


# ---------------------------------------------------------------------------
# RF01 - Gestão de Clientes
# ---------------------------------------------------------------------------

@login_required
def listar_clientes(request):
    clientes = Cliente.objects.filter(ativo=True)
    return render(request, "cotacoes/clientes_list.html", {"clientes": clientes})


@login_required
@require_http_methods(["GET", "POST"])
def novo_cliente(request):
    if request.method == "POST":
        cpf = somente_digitos(request.POST["cpf"])
        telefone = somente_digitos(request.POST.get("telefone", ""))

        if Cliente.objects.filter(cpf=cpf).exists():
            messages.error(request, "Já existe um cliente cadastrado com esse CPF.")
            return render(request, "cotacoes/cliente_form.html")

        Cliente.objects.create(
            nome=request.POST["nome"],
            cpf=cpf,
            data_nascimento=request.POST["data_nascimento"],
            email=request.POST.get("email", ""),
            telefone=telefone,
        )
        messages.success(request, "Cliente cadastrado com sucesso.")
        return redirect("listar_clientes")
    return render(request, "cotacoes/cliente_form.html")


# ---------------------------------------------------------------------------
# RF02 + RF03 + RF04 + RF05 - Nova cotação (o fluxo central do sistema)
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def nova_cotacao(request):
    if request.method == "GET":
        return render(request, "cotacoes/cotacao_form.html")

    # --- POST: processa a simulação completa ---
    nome = request.POST["nome"]
    cpf = somente_digitos(request.POST["cpf"])
    email = request.POST.get("email", "")
    telefone = somente_digitos(request.POST.get("telefone", ""))
    tipo_seguro = request.POST["tipo_seguro"]
    valor_bem = float(request.POST["valor_bem"])
    idade = int(request.POST["idade"])
    uso_veiculo = request.POST.get("uso_veiculo", "")  # ainda não entra no cálculo, ver nota no README

    # O formulário só coleta a idade (não a data de nascimento completa),
    # então aproximamos a data de nascimento a partir dela. Suficiente
    # para o cadastro do cliente nesta etapa do projeto; pode ser
    # substituído por um campo de data real no formulário depois.
    hoje = date.today()
    try:
        data_nascimento_aproximada = hoje.replace(year=hoje.year - idade)
    except ValueError:  # 29 de fevereiro em ano não bissexto
        data_nascimento_aproximada = hoje.replace(year=hoje.year - idade, day=28)

    cliente, criado = Cliente.objects.get_or_create(
        cpf=cpf,
        defaults={
            "nome": nome,
            "data_nascimento": data_nascimento_aproximada,
            "email": email,
            "telefone": telefone,
        },
    )

    # Se o cliente já existia e algum desses campos veio preenchido agora
    # mas estava vazio no cadastro, aproveita para completar o cadastro
    # (sem sobrescrever dados já existentes, só preenchendo lacunas).
    if not criado:
        atualizou = False
        if email and not cliente.email:
            cliente.email = email
            atualizou = True
        if telefone and not cliente.telefone:
            cliente.telefone = telefone
            atualizou = True
        if atualizou:
            cliente.save()

    bem = Bem.objects.create(
        cliente=cliente,
        tipo=tipo_seguro,
        descricao=f"{cliente.nome} - {tipo_seguro}",
        valor_estimado=valor_bem,
    )

    perfil = {"idade": idade, "valor_bem": valor_bem}

    # 1) IA Simbólica decide o parecer (RF04/RF05)
    parecer = motor_ia.avaliar_elegibilidade(perfil)

    # 2) Motor de cálculo usa o parecer para ajustar o prêmio (RF03)
    fator_risco = motor_ia.fator_risco_por_perfil(perfil, parecer)
    resultado_calculo = motor_ia.calcular_proposta(tipo_seguro, valor_bem, fator_risco)

    # 3) Persiste a cotação completa no Mongo, schema-less (RF02)
    cotacao_id = nosql.salvar_cotacao(
        cliente_id=cliente.id,
        bem_id=bem.id,
        tipo_seguro=tipo_seguro,
        dados={**perfil, "uso_veiculo": uso_veiculo},
        resultado_calculo=resultado_calculo,
        parecer_ia=parecer,
    )

    contexto = {
        "cliente": cliente,
        "bem": bem,
        "parecer": parecer,
        "resultado_calculo": resultado_calculo,
        "cotacao_id": cotacao_id,
    }
    return render(request, "cotacoes/cotacao_resultado.html", contexto)


# ---------------------------------------------------------------------------
# Fechar Negócio - transforma uma simulação (Mongo) numa Apólice real (Postgres)
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def fechar_negocio(request, cotacao_id):
    cotacao = nosql.buscar_cotacao_por_id(cotacao_id)
    if cotacao is None:
        messages.error(request, "Cotação não encontrada.")
        return redirect("dashboard")

    cliente = get_object_or_404(Cliente, pk=cotacao["cliente_id"])
    bem = get_object_or_404(Bem, pk=cotacao["bem_id"])
    planos_disponiveis = Plano.objects.filter(
        tipo_seguro=cotacao["tipo_seguro"], ativo=True, seguradora__ativa=True
    ).select_related("seguradora")

    if request.method == "GET":
        contexto = {
            "cliente": cliente,
            "bem": bem,
            "cotacao": cotacao,
            "cotacao_id": cotacao_id,
            "planos_disponiveis": planos_disponiveis,
        }
        return render(request, "cotacoes/fechar_negocio.html", contexto)

    # --- POST: cria a Apólice de verdade ---
    plano = get_object_or_404(Plano, pk=request.POST["plano_id"])
    hoje = date.today()

    numero_apolice = f"AP-{hoje.year}-{random.randint(100000, 999999)}"
    valor_premio = cotacao["resultado_calculo"]["premio"]
    valor_comissao = round(float(valor_premio) * float(plano.comissao_efetiva()) / 100, 2)

    Apolice.objects.create(
        cliente=cliente,
        bem=bem,
        seguradora=plano.seguradora,
        plano=plano,
        cotacao_mongo_id=str(cotacao_id),
        numero_apolice=numero_apolice,
        valor_premio=valor_premio,
        valor_franquia=cotacao["resultado_calculo"]["franquia"],
        valor_comissao=valor_comissao,
        data_inicio=hoje,
        data_fim=hoje + timedelta(days=365),
        status="ativa",
    )

    messages.success(request, f"Apólice {numero_apolice} emitida com sucesso!")
    return redirect("dashboard")


# ---------------------------------------------------------------------------
# RF06 - Dashboard (indicadores agregados a partir do Mongo)
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    cotacoes = nosql.listar_todas_cotacoes()

    total = len(cotacoes)
    aprovadas = sum(1 for c in cotacoes if c["parecer_ia"]["status"] == "Aprovada")
    faturamento_estimado = sum(c["resultado_calculo"]["margem"] for c in cotacoes)

    # Monta a lista de cotações recentes já com nome do cliente e tipo do bem,
    # pra exibir numa tabela sem o template precisar consultar o banco.
    recentes = []
    for c in cotacoes[:10]:
        cliente = Cliente.objects.filter(pk=c["cliente_id"]).first()
        recentes.append({
            "cliente_nome": cliente.nome if cliente else "Cliente removido",
            "tipo_seguro": c["tipo_seguro"],
            "valor_bem": c["dados"].get("valor_bem", 0),
            "status_ia": c["parecer_ia"]["status"],
            "premio": c["resultado_calculo"]["premio"],
            "cotacao_id": str(c["_id"]),
        })

    apolices_ativas = Apolice.objects.filter(status="ativa")
    comissao_realizada = sum(a.valor_comissao for a in apolices_ativas)

    contexto = {
        "total_cotacoes": total,
        "taxa_aprovacao": round((aprovadas / total * 100), 1) if total else 0,
        "faturamento_estimado": round(faturamento_estimado, 2),
        "clientes_ativos": Cliente.objects.filter(ativo=True).count(),
        "cotacoes_recentes": recentes,
        "apolices_ativas_count": apolices_ativas.count(),
        "comissao_realizada": round(comissao_realizada, 2),
    }
    return render(request, "cotacoes/dashboard.html", contexto)