"""
views.py
--------
Camada de controle (MTV) que conecta a interface web às três peças de
negócio: cadastros (Postgres/models.py), cálculo + IA (motor_ia.py) e
persistência de cotações (Mongo/nosql.py).
"""

import json
from datetime import date

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_http_methods

from .models import Cliente, Bem
from . import motor_ia
from . import nosql
from .utils import somente_digitos


def home(request):
    """Landing page institucional (a tela que você já tinha pronta)."""
    return render(request, "cotacoes/home.html")


# ---------------------------------------------------------------------------
# RF01 - Gestão de Clientes
# ---------------------------------------------------------------------------

def listar_clientes(request):
    clientes = Cliente.objects.filter(ativo=True)
    return render(request, "cotacoes/clientes_list.html", {"clientes": clientes})


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
# RF06 - Dashboard (indicadores agregados a partir do Mongo)
# ---------------------------------------------------------------------------

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
        })

    contexto = {
        "total_cotacoes": total,
        "taxa_aprovacao": round((aprovadas / total * 100), 1) if total else 0,
        "faturamento_estimado": round(faturamento_estimado, 2),
        "clientes_ativos": Cliente.objects.filter(ativo=True).count(),
        "cotacoes_recentes": recentes,
    }
    return render(request, "cotacoes/dashboard.html", contexto)