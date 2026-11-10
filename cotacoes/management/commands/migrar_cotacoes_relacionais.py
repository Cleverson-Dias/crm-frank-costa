from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django.db import transaction

from cotacoes import nosql
from cotacoes.analytics import PARECERES_FAVORAVEIS
from cotacoes.models import Apolice, Cliente, Cotacao, TipoSeguro


STATUS_NEGADOS = {
    "Recusada",
    "Não Coberto",
    "Pendência de Dados",
    "Erro de Parâmetro",
    "rejected",
    "denied",
}
STATUS_APROVADOS = PARECERES_FAVORAVEIS | {
    "approved",
    "approved with risk factor",
}


def decimal_ou_none(valor):
    if valor is None:
        return None
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not numero.is_finite():
        return None
    return numero


class Command(BaseCommand):
    help = (
        "Importa os resumos relacionais das cotações antigas do MongoDB. "
        "Executa somente uma prévia, a menos que --apply seja informado."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Grava os registros relacionais; sem esta opção, apenas mostra a prévia.",
        )

    def handle(self, *args, **options):
        aplicar = options["apply"]
        documentos = nosql.get_db().cotacoes.find({}).sort("criado_em", 1)
        total = 0
        prontos = 0
        importados = 0
        existentes = 0
        ignorados = 0

        for documento in documentos:
            total += 1
            mongo_id = str(documento.get("_id", ""))
            if not mongo_id:
                ignorados += 1
                continue
            if Cotacao.objects.filter(cotacao_mongo_id=mongo_id).exists():
                existentes += 1
                continue

            try:
                cliente_id = int(documento["cliente_id"])
            except (KeyError, TypeError, ValueError):
                ignorados += 1
                self.stderr.write(f"Cotação {mongo_id}: cliente_id inválido; ignorada.")
                continue
            cliente = Cliente.objects.filter(pk=cliente_id).first()
            tipo = TipoSeguro.objects.filter(
                codigo=documento.get("tipo_seguro", ""),
                ativo=True,
            ).first()
            if cliente is None or tipo is None:
                ignorados += 1
                motivo = "cliente não encontrado" if cliente is None else "ramo não cadastrado/ativo"
                self.stderr.write(f"Cotação {mongo_id}: {motivo}; ignorada.")
                continue

            apolice = Apolice.objects.filter(cotacao_mongo_id=mongo_id).first()
            if apolice and apolice.cotacao_id:
                ignorados += 1
                self.stderr.write(
                    f"Cotação {mongo_id}: a apólice já está ligada a outra cotação; ignorada."
                )
                continue
            dados = documento.get("dados") or documento.get("dados_bem") or {}
            if not isinstance(dados, dict):
                dados = {"dados_legados": str(dados)}
            calculo = documento.get("resultado_calculo") or {}
            parecer = documento.get("parecer_ia") or {}
            if not isinstance(calculo, dict):
                calculo = {}
            if not isinstance(parecer, dict):
                parecer = {}
            parecer_status = parecer.get("status", "")
            if not isinstance(parecer_status, str):
                parecer_status = ""

            if apolice:
                status = "convertida"
            elif parecer_status in STATUS_APROVADOS:
                status = "aprovada"
            elif parecer_status in STATUS_NEGADOS:
                status = "recusada"
            else:
                status = "rascunho"

            cotacao = Cotacao(
                cliente=cliente,
                tipo_seguro=tipo,
                seguradora=apolice.seguradora if apolice else None,
                plano=apolice.plano if apolice else None,
                status=status,
                valor_estimado=decimal_ou_none(
                    calculo.get("premio_bruto") or calculo.get("premio")
                ),
                valor_final=apolice.valor_premio if apolice else None,
                valor_franquia=(
                    apolice.valor_franquia
                    if apolice
                    else decimal_ou_none(calculo.get("franquia"))
                ),
                dados_especificos=dados,
                cotacao_mongo_id=mongo_id,
            )
            try:
                cotacao.full_clean()
            except ValidationError as erro:
                ignorados += 1
                self.stderr.write(
                    f"Cotação {mongo_id}: dados relacionais inválidos "
                    f"({erro}); ignorada."
                )
                continue
            prontos += 1
            if not aplicar:
                continue

            with transaction.atomic():
                cotacao.save()
                if apolice and not apolice.cotacao_id:
                    apolice.cotacao = cotacao
                    apolice.save(update_fields=["cotacao"])
                criado_em = documento.get("criado_em")
                if isinstance(criado_em, datetime):
                    Cotacao.objects.filter(pk=cotacao.pk).update(
                        data_cotacao=criado_em.date()
                    )
            importados += 1

        modo = "Gravação concluída" if aplicar else "Prévia concluída (nenhuma gravação)"
        self.stdout.write(self.style.SUCCESS(
            f"{modo}: {total} documentos analisados; "
            f"{prontos} elegíveis; {importados} importados; "
            f"{existentes} já vinculados; {ignorados} ignorados."
        ))
