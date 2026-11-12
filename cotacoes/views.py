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
from django.core.exceptions import ValidationError
from django.db import transaction
from django.views.decorators.http import require_http_methods
from django.utils.dateparse import parse_date

from .models import (
    Cliente,
    Bem,
    Seguradora,
    Plano,
    Apolice,
    Cotacao,
    TipoSeguro,
    TIPOS_SEGURO_ATIVOS,
)
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
        tipo_pessoa = request.POST.get("tipo_pessoa", "pf")
        nome = request.POST.get("nome", "").strip()
        cpf = somente_digitos(request.POST.get("cpf", ""))
        cnpj = somente_digitos(request.POST.get("cnpj", ""))
        telefone = somente_digitos(request.POST.get("telefone", ""))
        if tipo_pessoa not in {"pf", "pj"}:
            messages.error(request, "Selecione pessoa física ou pessoa jurídica.")
            return render(request, "cotacoes/cliente_form.html", {"form_data": request.POST})
        if not nome:
            messages.error(request, "Informe o nome do cliente.")
            return render(request, "cotacoes/cliente_form.html", {"form_data": request.POST})
        if tipo_pessoa == "pf" and len(cpf) != 11:
            messages.error(request, "Informe um CPF com 11 dígitos.")
            return render(request, "cotacoes/cliente_form.html", {"form_data": request.POST})
        data_nascimento = parse_date(request.POST.get("data_nascimento", ""))
        if tipo_pessoa == "pf" and data_nascimento is None:
            messages.error(request, "Informe uma data de nascimento válida.")
            return render(request, "cotacoes/cliente_form.html", {"form_data": request.POST})
        if tipo_pessoa == "pj" and len(cnpj) != 14:
            messages.error(request, "Informe um CNPJ com 14 dígitos.")
            return render(request, "cotacoes/cliente_form.html", {"form_data": request.POST})

        identificador_existe = (
            Cliente.objects.filter(cpf=cpf).exists()
            if tipo_pessoa == "pf"
            else Cliente.objects.filter(cnpj=cnpj).exists()
        )
        if identificador_existe:
            mensagem = "CPF" if tipo_pessoa == "pf" else "CNPJ"
            messages.error(request, f"Já existe um cliente cadastrado com esse {mensagem}.")
            return render(request, "cotacoes/cliente_form.html", {"form_data": request.POST})

        cliente = Cliente(
            tipo_pessoa=tipo_pessoa,
            nome=nome,
            cpf=cpf or None,
            cnpj=cnpj or None,
            data_nascimento=data_nascimento,
            email=request.POST.get("email", ""),
            telefone=telefone,
            endereco=request.POST.get("endereco", "").strip(),
            cidade=request.POST.get("cidade", "").strip(),
            estado=request.POST.get("estado", "").strip().upper(),
            cep=request.POST.get("cep", "").strip(),
            profissao=request.POST.get("profissao", "").strip(),
            corretor_responsavel=request.user,
            observacoes=request.POST.get("observacoes", "").strip(),
        )
        try:
            cliente.full_clean()
        except ValidationError as erro:
            for campo, mensagens_campo in erro.message_dict.items():
                for mensagem in mensagens_campo:
                    messages.error(request, mensagem)
            return render(request, "cotacoes/cliente_form.html", {"form_data": request.POST})
        cliente.save()
        messages.success(request, "Cliente cadastrado com sucesso.")
        return redirect("listar_clientes")
    return render(request, "cotacoes/cliente_form.html", {"form_data": {}})


def montar_perfil_cotacao(dados, tipo_seguro, ano_atual=None):
    if tipo_seguro not in dict(TIPOS_SEGURO_ATIVOS):
        raise ValueError("Selecione um ramo de seguro válido.")
    if tipo_seguro not in {"auto", "vida", "saude"}:
        raise ValueError(
            "Este ramo está cadastrado, mas ainda não possui uma análise automática configurada."
        )

    try:
        idade = int(dados.get("idade", ""))
    except (TypeError, ValueError) as erro:
        raise ValueError("Informe uma idade válida para a cotação.") from erro
    if idade < 0 or idade > 120:
        raise ValueError("Confira a idade informada.")

    perfil = {"idade": idade, "tipo_seguro": tipo_seguro}
    valor_informado = None
    if tipo_seguro != "saude" or (dados.get("possui_contrato") == "sim" and dados.get("valor_bem")):
        try:
            valor_informado = Decimal(dados.get("valor_bem", ""))
        except (InvalidOperation, TypeError, ValueError) as erro:
            raise ValueError("Informe um valor válido para a cotação.") from erro
        if not valor_informado.is_finite() or valor_informado <= 0:
            raise ValueError("Confira o valor informado.")
        if valor_informado > Decimal("9999999999.99"):
            raise ValueError("O valor informado excede o limite aceito para esta cotação.")
    if tipo_seguro == "auto":
        marca = dados.get("marca_veiculo", "").strip()
        modelo = dados.get("modelo_veiculo", "").strip()
        uso_veiculo = dados.get("uso_veiculo", "")
        try:
            ano_modelo = int(dados.get("ano_modelo", ""))
            tempo_habilitacao = int(dados.get("tempo_habilitacao_anos", ""))
            sinistros = int(dados.get("sinistros_ultimos_3_anos", ""))
        except (TypeError, ValueError) as erro:
            raise ValueError("Confira o ano do veículo, o tempo de habilitação e os sinistros.") from erro

        referencia = ano_atual or date.today().year
        if not marca or not modelo:
            raise ValueError("Informe a marca e o modelo do veículo.")
        if len(marca) > 80 or len(modelo) > 100:
            raise ValueError("A marca ou o modelo do veículo excede o limite de caracteres.")
        if ano_modelo < 1900 or ano_modelo > referencia + 1:
            raise ValueError("Informe um ano de fabricação/modelo válido.")
        if uso_veiculo not in {"passeio", "trabalho", "carga"}:
            raise ValueError("Selecione um uso válido para o veículo.")
        if tempo_habilitacao < 0 or tempo_habilitacao > idade:
            raise ValueError("Confira o tempo de habilitação do condutor principal.")
        if sinistros not in {0, 1, 2, 3}:
            raise ValueError("Informe uma faixa válida de sinistros nos últimos 3 anos.")

        condutor_adicional = dados.get("condutor_adicional") == "on"
        idade_adicional = None
        if condutor_adicional:
            try:
                idade_adicional = int(dados.get("idade_condutor_adicional", ""))
            except (TypeError, ValueError) as erro:
                raise ValueError("Informe a idade do condutor adicional.") from erro
            if idade_adicional < 18 or idade_adicional > 120:
                raise ValueError("A idade do condutor adicional deve estar entre 18 e 120 anos.")

        perfil.update({
            "valor_bem": float(valor_informado),
            "marca_veiculo": marca,
            "modelo_veiculo": modelo,
            "ano_modelo": ano_modelo,
            "ano_referencia": referencia,
            "uso_veiculo": uso_veiculo,
            "uso_profissional": uso_veiculo in {"trabalho", "carga"},
            "condutor_adicional": condutor_adicional,
            "idade_condutor_adicional": idade_adicional,
            "tempo_habilitacao_anos": tempo_habilitacao,
            "sinistros_ultimos_3_anos": sinistros,
        })
        return perfil, valor_informado, valor_informado, f"{marca} {modelo} - {ano_modelo}"

    if tipo_seguro == "vida":
        capital_segurado = float(valor_informado)
        perfil.update({
            "valor_bem": capital_segurado,
            "capital_segurado": capital_segurado,
            "dps_completa": dados.get("dps_completa") == "on",
            "dps_compativel": dados.get("dps_compativel") == "on",
            "tabagismo": dados.get("tabagismo") == "on",
            "alcool_elevado": dados.get("alcool_elevado") == "on",
            "doenca_relevante_declarada": dados.get("doenca_relevante_declarada") == "on",
            "internacao_recente": dados.get("internacao_recente") == "on",
            "profissao_risco": dados.get("profissao_risco") == "on",
            "esporte_radical": dados.get("esporte_radical") == "on",
        })
        return perfil, valor_informado, valor_informado, "Capital segurado"

    possui_contrato = dados.get("possui_contrato")
    if possui_contrato not in {"sim", "nao"}:
        raise ValueError("Informe se existe plano de saúde vigente.")
    segmentacao = dados.get("segmentacao_contratada", "")
    cobertura = dados.get("cobertura_exigida", "")
    if segmentacao not in {
        "ambulatorial",
        "hospitalar",
        "hospitalar_obstetricia",
        "odontologico",
        "ambulatorial_odontologico",
        "ambulatorial_hospitalar",
        "ambulatorial_hospitalar_obstetricia",
        "hospitalar_obstetricia_odontologico",
        "hospitalar_odontologico",
        "ambulatorial_hospitalar_odontologico",
        "ambulatorial_hospitalar_obstetricia_odontologico",
        "referencia",
    }:
        raise ValueError("Selecione uma segmentação válida para o plano de saúde.")
    if cobertura not in {"ambulatorial", "hospitalar", "obstetricia", "odontologica"}:
        raise ValueError("Selecione uma cobertura válida.")
    perfil.update({
        "possui_contrato": possui_contrato == "sim",
        "segmentacao_contratada": segmentacao,
        "cobertura_exigida": cobertura,
    })
    if possui_contrato == "nao":
        tipo_contratacao = dados.get("tipo_contratacao", "")
        if tipo_contratacao not in {"individual_familiar", "coletivo_empresarial", "coletivo_adesao"}:
            raise ValueError("Selecione a modalidade da nova contratação.")
        try:
            quantidade_vidas = int(dados.get("quantidade_vidas_nova", ""))
        except (TypeError, ValueError) as erro:
            raise ValueError("Informe a quantidade de vidas da nova contratação.") from erro
        if quantidade_vidas < 1:
            raise ValueError("A quantidade de vidas deve ser pelo menos 1.")
        perfil.update({"operacao": "nova_contratacao", "tipo_contratacao": tipo_contratacao,
                       "quantidade_vidas": quantidade_vidas, "valor_bem": None})
        return perfil, None, None, "Nova contratação de plano de saúde"

    data_inicio = parse_date(dados.get("data_inicio_contrato", ""))
    tipo_atendimento = dados.get("tipo_atendimento", "")
    if data_inicio is None or data_inicio > date.today():
        raise ValueError("Informe uma data de início válida, que não seja futura.")
    if tipo_atendimento not in {"demais", "urgencia_emergencia", "parto"}:
        raise ValueError("Selecione o tipo de atendimento a analisar.")
    premio_anual_estimado = valor_informado * 12 if valor_informado is not None else None
    if premio_anual_estimado is not None and premio_anual_estimado > Decimal("9999999999.99"):
        raise ValueError("O valor informado excede o limite aceito para esta cotação.")
    dias_contrato = (date.today() - data_inicio).days
    perfil.update({
        "valor_bem": None,
        "mensalidade_mensal": float(valor_informado) if valor_informado is not None else None,
        "premio_anual_estimado": float(premio_anual_estimado) if premio_anual_estimado is not None else None,
        "operacao": "atendimento",
        "tipo_atendimento": tipo_atendimento,
        "dias_contrato": dias_contrato,
        "data_inicio_contrato": data_inicio.isoformat(),
        "no_rol_ans": dados.get("no_rol_ans") == "on",
        "dentro_abrangencia": dados.get("dentro_abrangencia") == "on",
        "dlp_declarada": dados.get("dlp_declarada") == "on",
        "relacionado_dlp": dados.get("relacionado_dlp") == "on",
        "alta_complexidade": dados.get("alta_complexidade") == "on",
    })
    return perfil, None, valor_informado, "Plano de saúde"


def contexto_formulario_cotacao(request):
    return {
        "form_data": request.POST if request.method == "POST" else {},
        "seguradoras_disponiveis": Seguradora.objects.filter(ativa=True).order_by("nome"),
        "planos_disponiveis": Plano.objects.filter(
            ativo=True,
            seguradora__ativa=True,
            tipo_seguro__in=("auto", "vida", "saude"),
        ).select_related("seguradora", "tipo"),
    }


def criar_cotacao_manual_pj(request):
    formulario = contexto_formulario_cotacao(request)
    nome = request.POST.get("nome", "").strip()
    cnpj = somente_digitos(request.POST.get("cnpj", ""))
    tipo_seguro = request.POST.get("tipo_seguro", "")
    if not nome:
        messages.error(request, "Informe a razão social.")
        return render(request, "cotacoes/cotacao_form.html", formulario)
    if len(cnpj) != 14:
        messages.error(request, "Informe um CNPJ com 14 dígitos.")
        return render(request, "cotacoes/cotacao_form.html", formulario)
    if tipo_seguro not in {"auto", "vida", "saude"}:
        messages.error(request, "Selecione Automóvel, Vida ou Saúde para esta cotação.")
        return render(request, "cotacoes/cotacao_form.html", formulario)

    tipo = get_object_or_404(TipoSeguro, codigo=tipo_seguro, ativo=True)
    seguradora_id = request.POST.get("seguradora_id", "")
    plano_id = request.POST.get("plano_id", "")
    if bool(seguradora_id) != bool(plano_id):
        messages.error(request, "Selecione seguradora e plano juntos ou deixe ambos sem seleção.")
        return render(request, "cotacoes/cotacao_form.html", formulario)

    plano = None
    seguradora = None
    if plano_id:
        if not seguradora_id.isdecimal() or not plano_id.isdecimal():
            messages.error(request, "Selecione uma seguradora e um plano válidos.")
            return render(request, "cotacoes/cotacao_form.html", formulario)
        plano = Plano.objects.filter(
            pk=plano_id,
            tipo_seguro=tipo_seguro,
            ativo=True,
            seguradora__ativa=True,
        ).select_related("seguradora").first()
        if plano is None or str(plano.seguradora_id) != seguradora_id:
            messages.error(request, "O plano selecionado não pertence ao ramo e à seguradora informados.")
            return render(request, "cotacoes/cotacao_form.html", formulario)
        seguradora = plano.seguradora

    quantidade_vidas = None
    if tipo_seguro == "saude":
        try:
            quantidade_vidas = int(request.POST.get("quantidade_vidas", ""))
        except (TypeError, ValueError):
            quantidade_vidas = 0
        if quantidade_vidas < 1:
            messages.error(request, "Informe a quantidade de vidas do contrato empresarial.")
            return render(request, "cotacoes/cotacao_form.html", formulario)
        if seguradora and "bradesco" in seguradora.nome.casefold() and quantidade_vidas < 2:
            messages.error(
                request,
                "Bradesco Saúde não aceita cotação individual; informe pelo menos duas vidas.",
            )
            return render(request, "cotacoes/cotacao_form.html", formulario)

    email = request.POST.get("email", "").strip()
    telefone = somente_digitos(request.POST.get("telefone", ""))
    atividade_empresa = request.POST.get("atividade_empresa", "").strip()
    cliente = Cliente.objects.filter(cnpj=cnpj).first()
    if cliente is None:
        cliente = Cliente(
            tipo_pessoa="pj",
            nome=nome,
            cnpj=cnpj,
            email=email,
            telefone=telefone,
            endereco=request.POST.get("endereco", "").strip(),
            cidade=request.POST.get("cidade", "").strip(),
            estado=request.POST.get("estado", "").strip().upper(),
            cep=request.POST.get("cep", "").strip(),
            profissao=atividade_empresa,
            corretor_responsavel=request.user,
        )
        try:
            cliente.full_clean()
        except ValidationError as erro:
            for mensagens_campo in erro.message_dict.values():
                for mensagem in mensagens_campo:
                    messages.error(request, mensagem)
            return render(request, "cotacoes/cotacao_form.html", formulario)
        cliente.save()
    else:
        atualizou = False
        for campo, valor in (
            ("email", email),
            ("telefone", telefone),
            ("corretor_responsavel", request.user),
        ):
            if valor and not getattr(cliente, campo):
                setattr(cliente, campo, valor)
                atualizou = True
        if atualizou:
            cliente.save()

    descricao_risco = request.POST.get("descricao_risco", "").strip()
    cobertura_solicitada = request.POST.get("cobertura_solicitada", "").strip()
    dados = {
        "origem_cotacao": "manual_pj",
        "tipo_pessoa": "pj",
        "cnpj": cnpj,
        "atividade_empresa": atividade_empresa,
        "contato_nome": request.POST.get("contato_nome", "").strip(),
        "quantidade_vidas": quantidade_vidas,
        "descricao_risco": descricao_risco,
        "cobertura_solicitada": cobertura_solicitada,
        "observacoes": request.POST.get("observacoes", "").strip(),
    }
    bem = Bem.objects.create(
        cliente=cliente,
        tipo=tipo_seguro,
        descricao=f"{nome} - {tipo.nome}"[:200],
    )
    cotacao = Cotacao(
        cliente=cliente,
        tipo_seguro=tipo,
        seguradora=seguradora,
        plano=plano,
        corretor_responsavel=request.user,
        status="rascunho",
        quantidade_vidas=quantidade_vidas,
        dados_especificos=dados,
        observacoes=request.POST.get("observacoes", "").strip(),
    )
    try:
        cotacao.full_clean()
    except ValidationError as erro:
        for mensagens_campo in erro.message_dict.values():
            for mensagem in mensagens_campo:
                messages.error(request, mensagem)
        return render(request, "cotacoes/cotacao_form.html", formulario)
    resultado_calculo = (
        motor_ia.calcular_proposta("saude", None, 1.0)
        if tipo_seguro == "saude"
        else {}
    )
    if tipo_seguro == "saude":
        resultado_calculo["mensagem"] = "Aguardando cotação da seguradora."
    cotacao_id = nosql.salvar_cotacao(
        cliente_id=cliente.id,
        bem_id=bem.id,
        tipo_seguro=tipo_seguro,
        dados=dados,
        resultado_calculo=resultado_calculo,
        parecer_ia={"status": "Aguardando cotação da seguradora"},
    )
    cotacao.cotacao_mongo_id = str(cotacao_id)
    cotacao.save()
    return render(
        request,
        "cotacoes/cotacao_manual_resultado.html",
        {
            "cliente": cliente,
            "cotacao": cotacao,
            "cotacao_id": cotacao_id,
            "tipo_seguro": tipo,
            "plano": plano,
        },
    )


# ---------------------------------------------------------------------------
# RF02 + RF03 + RF04 + RF05 - Nova cotação (o fluxo central do sistema)
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def nova_cotacao(request):
    if request.method == "GET":
        return render(
            request,
            "cotacoes/cotacao_form.html",
            contexto_formulario_cotacao(request),
        )

    # --- POST: processa a simulação completa ---
    tipo_pessoa = request.POST.get("tipo_pessoa", "pf")
    if tipo_pessoa not in {"pf", "pj"}:
        messages.error(request, "Selecione pessoa física ou pessoa jurídica.")
        return render(
            request,
            "cotacoes/cotacao_form.html",
            contexto_formulario_cotacao(request),
        )
    if tipo_pessoa == "pj":
        return criar_cotacao_manual_pj(request)

    nome = request.POST.get("nome", "").strip()
    cpf = somente_digitos(request.POST.get("cpf", ""))
    email = request.POST.get("email", "")
    telefone = somente_digitos(request.POST.get("telefone", ""))
    tipo_seguro = request.POST.get("tipo_seguro", "")
    if not nome:
        messages.error(request, "Informe o nome do segurado.")
        return render(
            request,
            "cotacoes/cotacao_form.html",
            contexto_formulario_cotacao(request),
        )
    if len(cpf) != 11:
        messages.error(request, "Informe um CPF com 11 dígitos.")
        return render(
            request,
            "cotacoes/cotacao_form.html",
            contexto_formulario_cotacao(request),
        )
    try:
        perfil, valor_estimado, valor_informado, descricao_bem = montar_perfil_cotacao(
            request.POST, tipo_seguro
        )
    except ValueError as erro:
        messages.error(request, str(erro))
        return render(
            request,
            "cotacoes/cotacao_form.html",
            contexto_formulario_cotacao(request),
        )

    seguradora_id = request.POST.get("seguradora_id") or None
    plano_id = request.POST.get("plano_id") or None
    seguradora = None
    plano = None
    if bool(seguradora_id) != bool(plano_id):
        messages.error(request, "Selecione a seguradora e o plano ou deixe ambos sem seleção.")
        return render(
            request,
            "cotacoes/cotacao_form.html",
            contexto_formulario_cotacao(request),
        )
    if plano_id:
        if not seguradora_id.isdecimal() or not plano_id.isdecimal():
            messages.error(request, "Selecione uma seguradora e um plano válidos.")
            return render(
                request,
                "cotacoes/cotacao_form.html",
                contexto_formulario_cotacao(request),
            )
        plano = Plano.objects.filter(
            pk=plano_id,
            tipo_seguro=tipo_seguro,
            ativo=True,
            seguradora__ativa=True,
        ).select_related("seguradora").first()
        if not plano or str(plano.seguradora_id) != str(seguradora_id):
            messages.error(request, "O plano selecionado não pertence ao ramo e à seguradora informados.")
            return render(
                request,
                "cotacoes/cotacao_form.html",
                contexto_formulario_cotacao(request),
            )
        seguradora = plano.seguradora
        segmentacao_plano = plano.segmentacao_assistencial
        segmentacao_informada = perfil.get("segmentacao_contratada")
        if tipo_seguro == "saude" and segmentacao_plano and segmentacao_informada != segmentacao_plano:
            messages.error(
                request,
                "A segmentaÃ§Ã£o selecionada nÃ£o corresponde Ã  cadastrada para este plano. Confira o contrato.",
            )
            return render(
                request,
                "cotacoes/cotacao_form.html",
                contexto_formulario_cotacao(request),
            )
        if (
            tipo_seguro == "saude"
            and "bradesco" in seguradora.nome.casefold()
        ):
            messages.error(
                request,
                "Bradesco Saúde não aceita cotação individual. Use o fluxo empresarial para cotação com vidas.",
            )
            return render(
                request,
                "cotacoes/cotacao_form.html",
                contexto_formulario_cotacao(request),
            )

    valor_bem = perfil["valor_bem"]

    hoje = date.today()
    try:
        data_nascimento_aproximada = hoje.replace(year=hoje.year - perfil["idade"])
    except ValueError:
        data_nascimento_aproximada = hoje.replace(
            year=hoje.year - perfil["idade"], day=28
        )

    cliente, criado = Cliente.objects.get_or_create(
        cpf=cpf,
        defaults={
            "tipo_pessoa": "pf",
            "nome": nome,
            "data_nascimento": data_nascimento_aproximada,
            "email": email,
            "telefone": telefone,
            "corretor_responsavel": request.user,
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
        if not cliente.corretor_responsavel_id:
            cliente.corretor_responsavel = request.user
            atualizou = True
        if atualizou:
            cliente.save()

    descricao_bem_registro = (
        f"{cliente.nome} - {descricao_bem}"
        if tipo_seguro == "auto"
        else f"{cliente.nome} - {dict(Bem.TIPO_CHOICES).get(tipo_seguro, tipo_seguro)}"
    )
    bem = Bem.objects.create(
        cliente=cliente,
        tipo=tipo_seguro,
        descricao=descricao_bem_registro[:200],
        valor_estimado=valor_estimado,
    )

    # 1) IA Simbólica decide o parecer (RF04/RF05)
    parecer = motor_ia.avaliar_elegibilidade(perfil)

    # 2) Motor de cálculo usa o parecer para ajustar o prêmio (RF03)
    fator_risco = motor_ia.fator_risco_por_perfil(perfil, parecer)
    if perfil.get("operacao") == "nova_contratacao":
        resultado_calculo = motor_ia.calcular_proposta(tipo_seguro, None, fator_risco)
        resultado_calculo["mensagem"] = "Aguardando cotação da operadora."
    elif tipo_seguro == "saude":
        resultado_calculo = motor_ia.calcular_proposta(
            tipo_seguro,
            valor_informado,
            fator_risco,
            periodicidade="mensal",
        )
        if valor_informado is None:
            resultado_calculo["mensagem"] = "Valor da mensalidade não informado."
    elif valor_bem is None:
        resultado_calculo = motor_ia.calcular_proposta(tipo_seguro, None, fator_risco)
        resultado_calculo["mensagem"] = "Valor não informado."
    else:
        resultado_calculo = motor_ia.calcular_proposta(
            tipo_seguro, valor_bem, fator_risco, idade=perfil.get("idade")
        )

    # 3) Persiste a cotação completa no Mongo, schema-less (RF02)
    cotacao_id = nosql.salvar_cotacao(
        cliente_id=cliente.id,
        bem_id=bem.id,
        tipo_seguro=tipo_seguro,
        dados={**perfil, "valor_informado": float(valor_informado) if valor_informado is not None else None},
        resultado_calculo=resultado_calculo,
        parecer_ia=parecer,
    )
    tipo = get_object_or_404(TipoSeguro, codigo=tipo_seguro, ativo=True)
    if perfil.get("operacao") == "nova_contratacao":
        status = "aguardando"
    else:
        status = "aprovada" if parecer["status"] in PARECERES_FAVORAVEIS else "recusada"
    Cotacao.objects.create(
        cliente=cliente,
        tipo_seguro=tipo,
        seguradora=seguradora,
        plano=plano,
        corretor_responsavel=request.user,
        status=status,
        valor_estimado=resultado_calculo.get("premio_bruto")
        or resultado_calculo.get("premio"),
        valor_franquia=resultado_calculo.get("franquia"),
        percentual_comissao=plano.comissao_efetiva() if plano else None,
        dados_especificos={**perfil, "valor_informado": float(valor_informado) if valor_informado is not None else None},
        cotacao_mongo_id=str(cotacao_id),
    )

    contexto = {
        "cliente": cliente,
        "bem": bem,
        "tipo_seguro": tipo_seguro,
        "operacao": perfil.get("operacao"),
        "pode_fechar": perfil.get("operacao") != "nova_contratacao" and parecer["status"] not in {
            "Recusada",
            "Não Coberto",
            "Pendência de Dados",
            "Erro de Parâmetro",
        },
        "parecer": parecer,
        "resultado_calculo": resultado_calculo,
        "exibe_estimativa": resultado_calculo.get("premio") is not None,
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

    cotacao_relacional = Cotacao.objects.filter(
        cotacao_mongo_id=str(cotacao_id)
    ).first()
    dados_cotacao = cotacao.get("dados") or {}
    cotacao_manual = dados_cotacao.get("origem_cotacao") == "manual_pj"
    if cotacao_manual and (
        cotacao_relacional is None
        or cotacao_relacional.status != "aprovada"
        or cotacao_relacional.valor_final is None
        or cotacao_relacional.valor_final <= 0
    ):
        messages.error(
            request,
            "A cotação manual precisa estar aprovada e ter o prêmio final informado antes da emissão.",
        )
        return redirect("dashboard")

    parecer_ia = cotacao.get("parecer_ia") or {}
    if not cotacao_manual and parecer_ia.get("status") in {
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
    plano_id = request.POST.get("plano_id", "")
    if not plano_id.isdecimal():
        messages.error(request, "Selecione um plano válido para emitir a apólice.")
        return redirect("fechar_negocio", cotacao_id=cotacao_id)
    plano = get_object_or_404(
        Plano,
        pk=plano_id,
        tipo_seguro=cotacao.get("tipo_seguro"),
        ativo=True,
        seguradora__ativa=True,
    )
    if (
        cotacao.get("tipo_seguro") == "saude"
        and "bradesco" in plano.seguradora.nome.casefold()
        and cliente.tipo_pessoa == "pf"
    ):
        messages.error(
            request,
            "Bradesco Saúde não aceita cotação individual; selecione um plano para contrato empresarial.",
        )
        return redirect("fechar_negocio", cotacao_id=cotacao_id)
    if (
        cotacao.get("tipo_seguro") == "saude"
        and "bradesco" in plano.seguradora.nome.casefold()
        and (cotacao_relacional is None or (cotacao_relacional.quantidade_vidas or 0) < 2)
    ):
        messages.error(
            request,
            "Bradesco Saúde exige pelo menos duas vidas para a cotação empresarial.",
        )
        return redirect("fechar_negocio", cotacao_id=cotacao_id)
    hoje = date.today()

    calc = cotacao.get("resultado_calculo") or {}
    numero_apolice = f"AP-{hoje.year}-{random.randint(100000, 999999)}"
    valor_premio = (
        cotacao_relacional.valor_final
        if cotacao_manual
        else calc.get("premio_bruto") or calc.get("premio", 0)
    )
    valor_franquia = (
        cotacao_relacional.valor_franquia or 0
        if cotacao_manual
        else calc.get("franquia", 0)
    )
    percentual_comissao = plano.comissao_efetiva()
    valor_comissao = (
        round(float(valor_premio) * float(percentual_comissao) / 100, 2)
        if percentual_comissao is not None
        else None
    )
    with transaction.atomic():
        if cotacao_relacional:
            cotacao_relacional.seguradora = plano.seguradora
            cotacao_relacional.plano = plano
            cotacao_relacional.status = "convertida"
            cotacao_relacional.valor_final = valor_premio
            cotacao_relacional.valor_franquia = valor_franquia
            cotacao_relacional.percentual_comissao = percentual_comissao
            cotacao_relacional.save()

        Apolice.objects.create(
            cliente=cliente,
            bem=bem,
            seguradora=plano.seguradora,
            plano=plano,
            cotacao=cotacao_relacional,
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
    ids_recentes = [
        str(c.get("_id", ""))
        for c in cotacoes[:10]
        if c.get("_id") is not None
    ]
    cotacoes_relacionais = {
        c.cotacao_mongo_id: c
        for c in Cotacao.objects.filter(cotacao_mongo_id__in=ids_recentes)
    }
    recentes = []
    for c in cotacoes[:10]:
        cliente_id = c.get("cliente_id")
        cliente = Cliente.objects.filter(pk=cliente_id).first() if cliente_id else None

        calc = c.get("resultado_calculo") if isinstance(c.get("resultado_calculo"), dict) else {}
        parecer = c.get("parecer_ia") if isinstance(c.get("parecer_ia"), dict) else {}
        dados_bem = c.get("dados_bem") or c.get("dados") or {}

        cot_id_str = str(c.get("_id", ""))
        cotacao_relacional = cotacoes_relacionais.get(cot_id_str)
        cotacao_manual = dados_bem.get("origem_cotacao") == "manual_pj"
        pode_fechar = (
            cotacao_relacional is not None
            and cotacao_relacional.status == "aprovada"
            and cotacao_relacional.valor_final is not None
            and cotacao_relacional.valor_final > 0
            if cotacao_manual
            else parecer.get("status") not in {
                "Recusada",
                "Não Coberto",
                "Pendência de Dados",
                "Erro de Parâmetro",
            }
        )

        recentes.append({
            "cliente_nome": cliente.nome if cliente else "Cliente removido",
            "tipo_seguro": dict(Bem.TIPO_CHOICES).get(
                c.get("tipo_seguro"), c.get("tipo_seguro", "N/A")
            ),
            "valor_bem": dados_bem.get("valor_fipe") or dados_bem.get("valor_bem"),
            "status_ia": parecer.get("status", "N/A"),
            "premio": calc.get("premio_bruto") or calc.get("premio"),
            "cotacao_id": cot_id_str,
            "fechada": cot_id_str in ids_fechados,
            "pode_fechar": pode_fechar,
        })

    apolices_ativas = Apolice.objects.filter(status="ativa")
    comissao_realizada = sum(
        (a.valor_comissao or Decimal("0"))
        for a in apolices_ativas
    )

    contexto = {
        "total_cotacoes": total,
        "taxa_aprovacao": round((aprovadas / total * 100), 1) if total else 0,
        "faturamento_estimado": round(faturamento_estimado, 2),
        "clientes_ativos": Cliente.objects.filter(ativo=True).count(),
        "cotacoes_recentes": recentes,
        "apolices_ativas_count": apolices_ativas.count(),
        "comissao_realizada": round(comissao_realizada, 2),
        "comissao_mensal_estimada": round(comissao_realizada / 12, 2),
    }
    return render(request, "cotacoes/dashboard.html", contexto)
