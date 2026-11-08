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
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from .models import Cliente, Bem, Seguradora, Plano, Apolice, TIPOS_SEGURO_ATIVOS
from .analytics import PARECERES_FAVORAVEIS
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
    nome = request.POST.get("nome", "").strip()
    cpf = somente_digitos(request.POST.get("cpf", ""))
    email = request.POST.get("email", "")
    telefone = somente_digitos(request.POST.get("telefone", ""))
    tipo_seguro = request.POST.get("tipo_seguro", "")
    try:
        if not nome:
            raise ValueError("Informe o nome do segurado.")
        if len(cpf) != 11:
            raise ValueError("Informe um CPF com 11 dígitos.")
        if tipo_seguro not in dict(TIPOS_SEGURO_ATIVOS):
            raise ValueError("Selecione um ramo de seguro válido.")
        idade = int(request.POST["idade"])
        valor_informado = Decimal(request.POST["valor_bem"])
        dias_contrato = int(request.POST.get("dias_contrato") or 0) if tipo_seguro == "saude" else 0
        valor_estimado = valor_informado * 12 if tipo_seguro == "saude" else valor_informado
        if idade < 0 or idade > 120 or not valor_informado.is_finite() or valor_informado <= 0:
            raise ValueError("Confira a idade e o valor informado.")
        if valor_estimado > Decimal("9999999999.99"):
            raise ValueError("O valor informado excede o limite aceito para esta cotação.")
        if dias_contrato < 0:
            raise ValueError("Os dias de contrato não podem ser negativos.")
    except (KeyError, InvalidOperation, ValueError):
        messages.error(request, "Informe um ramo, idade e valor válidos para a cotação.")
        return render(request, "cotacoes/cotacao_form.html")

    dados_especificos = {}
    if tipo_seguro == "auto":
        dados_especificos = {"uso_veiculo": request.POST.get("uso_veiculo", "")}
        valor_bem = float(valor_informado)
    elif tipo_seguro == "vida":
        valor_bem = float(valor_informado)
        dados_especificos = {
            "capital_segurado": valor_bem,
            "dps_completa": request.POST.get("dps_completa") == "on",
            "dps_compativel": request.POST.get("dps_compativel") == "on",
            "tabagismo": request.POST.get("tabagismo") == "on",
            "alcool_elevado": request.POST.get("alcool_elevado") == "on",
            "doenca_relevante_declarada": request.POST.get("doenca_relevante_declarada") == "on",
            "internacao_recente": request.POST.get("internacao_recente") == "on",
            "profissao_risco": request.POST.get("profissao_risco") == "on",
            "esporte_radical": request.POST.get("esporte_radical") == "on",
        }
    else:
        valor_bem = float(valor_informado * 12)
        dados_especificos = {
            "operacao": "atendimento",
            "segmentacao_contratada": request.POST.get("segmentacao_contratada", ""),
            "tipo_atendimento": request.POST.get("tipo_atendimento", ""),
            "dias_contrato": dias_contrato,
            "cobertura_exigida": request.POST.get("cobertura_exigida", ""),
            "no_rol_ans": request.POST.get("no_rol_ans") == "on",
            "dentro_abrangencia": request.POST.get("dentro_abrangencia") == "on",
            "dlp_declarada": request.POST.get("dlp_declarada") == "on",
            "relacionado_dlp": request.POST.get("relacionado_dlp") == "on",
            "alta_complexidade": request.POST.get("alta_complexidade") == "on",
        }

    hoje = date.today()
    try:
        data_nascimento_aproximada = hoje.replace(year=hoje.year - idade)
    except ValueError:
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
        descricao=f"{cliente.nome} - {dict(Bem.TIPO_CHOICES).get(tipo_seguro, tipo_seguro)}",
        valor_estimado=valor_estimado,
    )

    perfil = {"idade": idade, "valor_bem": valor_bem, "tipo_seguro": tipo_seguro, **dados_especificos}

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
        "tipo_seguro": tipo_seguro,
        "pode_fechar": parecer["status"] not in {
            "Recusada",
            "Não Coberto",
            "Pendência de Dados",
            "Erro de Parâmetro",
        },
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

    if Apolice.objects.filter(cotacao_mongo_id=str(cotacao_id)).exists():
        messages.warning(request, "Esta cotação já foi fechada e possui apólice emitida.")
        return redirect("dashboard")

    parecer_ia = cotacao.get("parecer_ia") or {}
    if parecer_ia.get("status") in {
        "Recusada",
        "Não Coberto",
        "Pendência de Dados",
        "Erro de Parâmetro",
    }:
        messages.error(request, "Esta cotação não pode virar apólice com o parecer atual.")
        return redirect("dashboard")

    cliente = get_object_or_404(Cliente, pk=cotacao.get("cliente_id"))
    bem = get_object_or_404(Bem, pk=cotacao.get("bem_id"))
    planos_disponiveis = Plano.objects.filter(
        tipo_seguro=cotacao.get("tipo_seguro"), ativo=True, seguradora__ativa=True
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
    plano = get_object_or_404(
        Plano,
        pk=request.POST["plano_id"],
        tipo_seguro=cotacao.get("tipo_seguro"),
        ativo=True,
        seguradora__ativa=True,
    )
    hoje = date.today()

    calc = cotacao.get("resultado_calculo") or {}
    numero_apolice = f"AP-{hoje.year}-{random.randint(100000, 999999)}"
    valor_premio = calc.get("premio_bruto") or calc.get("premio", 0)
    valor_franquia = calc.get("franquia", 0)
    valor_comissao = round(float(valor_premio) * float(plano.comissao_efetiva()) / 100, 2)

    Apolice.objects.create(
        cliente=cliente,
        bem=bem,
        seguradora=plano.seguradora,
        plano=plano,
        cotacao_mongo_id=str(cotacao_id),
        numero_apolice=numero_apolice,
        valor_premio=valor_premio,
        valor_franquia=valor_franquia,
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
    cotacoes = nosql.listar_todas_cotacoes() or []

    total = len(cotacoes)

    # Contagem segura de cotações aprovadas
    aprovadas = sum(
        1 for c in cotacoes
        if isinstance(c.get("parecer_ia"), dict)
        and c["parecer_ia"].get("status") in PARECERES_FAVORAVEIS
    )

    # Cálculo seguro do faturamento estimado (suporta 'comissao_corretora' ou 'margem')
    faturamento_estimado = 0.0
    for c in cotacoes:
        calc = c.get("resultado_calculo")
        if isinstance(calc, dict):
            faturamento_estimado += float(calc.get("comissao_corretora") or calc.get("margem") or 0)

    # Monta a lista de cotações recentes
    ids_fechados = set(Apolice.objects.values_list("cotacao_mongo_id", flat=True))
    recentes = []
    for c in cotacoes[:10]:
        cliente_id = c.get("cliente_id")
        cliente = Cliente.objects.filter(pk=cliente_id).first() if cliente_id else None

        calc = c.get("resultado_calculo") if isinstance(c.get("resultado_calculo"), dict) else {}
        parecer = c.get("parecer_ia") if isinstance(c.get("parecer_ia"), dict) else {}
        dados_bem = c.get("dados_bem") or c.get("dados") or {}

        cot_id_str = str(c.get("_id", ""))

        recentes.append({
            "cliente_nome": cliente.nome if cliente else "Cliente removido",
            "tipo_seguro": dict(Bem.TIPO_CHOICES).get(
                c.get("tipo_seguro"), c.get("tipo_seguro", "N/A")
            ),
            "valor_bem": dados_bem.get("valor_fipe") or dados_bem.get("valor_bem", 0),
            "status_ia": parecer.get("status", "N/A"),
            "premio": calc.get("premio_bruto") or calc.get("premio", 0),
            "cotacao_id": cot_id_str,
            "fechada": cot_id_str in ids_fechados,
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