from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .analytics import calcular_taxa_retencao, gerar_comissoes_demonstracao
from .motor_ia import avaliar_elegibilidade, calcular_proposta
from .models import RenovacaoApolice


class MotorPorRamoTests(SimpleTestCase):
    def test_auto_uses_auto_rules_and_rate(self):
        perfil = {"tipo_seguro": "auto", "idade": 35, "valor_bem": 80_000}

        parecer = avaliar_elegibilidade(perfil)
        proposta = calcular_proposta("auto", 80_000, 1)

        self.assertEqual(parecer["status"], "Aprovada")
        self.assertEqual(proposta["premio"], 3600.0)

    def test_life_uses_capital_segurado_rules_and_rate(self):
        perfil = {
            "tipo_seguro": "vida",
            "idade": 35,
            "capital_segurado": 300_000,
            "valor_bem": 300_000,
        }

        parecer = avaliar_elegibilidade(perfil)
        proposta = calcular_proposta("vida", 300_000, 1)

        self.assertEqual(parecer["status"], "Aprovada")
        self.assertEqual(proposta["premio"], 2400.0)

    def test_health_uses_annualized_premium_without_auto_franchise(self):
        perfil = {
            "tipo_seguro": "saude",
            "idade": 35,
            "segmentacao_contratada": "referencia",
            "tipo_atendimento": "demais",
            "dias_contrato": 365,
        }

        parecer = avaliar_elegibilidade(perfil)
        proposta = calcular_proposta("saude", 2400, 1)

        self.assertEqual(parecer["status"], "Cobertura Autorizada")
        self.assertEqual(proposta, {"premio": 2400, "franquia": 0.0, "margem": 0.0})


class TaxaRetencaoTests(SimpleTestCase):
    def test_retention_uses_renewed_over_resolved_eligible(self):
        self.assertEqual(calcular_taxa_retencao(20, 25), 80.0)

    def test_retention_is_undefined_without_eligible_policies(self):
        self.assertIsNone(calcular_taxa_retencao(0, 0))

    def test_retention_rejects_impossible_counts(self):
        with self.assertRaises(ValueError):
            calcular_taxa_retencao(3, 2)


class ComissoesDemonstracaoTests(SimpleTestCase):
    def test_generates_three_branches_for_each_of_the_last_24_months(self):
        linhas = gerar_comissoes_demonstracao(date(2026, 11, 9))
        valores_por_mes = defaultdict(Decimal)
        ramos_por_mes = defaultdict(set)

        for mes, ramo, valor in linhas:
            valores_por_mes[mes] += valor
            ramos_por_mes[mes].add(ramo)

        self.assertEqual(len(linhas), 24 * 3)
        self.assertEqual(len(valores_por_mes), 24)
        self.assertEqual(min(valores_por_mes), date(2024, 12, 1))
        self.assertEqual(max(valores_por_mes), date(2026, 11, 1))
        for mes, total in valores_por_mes.items():
            with self.subTest(mes=mes):
                self.assertGreaterEqual(total, Decimal("6000"))
                self.assertLessEqual(total, Decimal("12000"))
                self.assertEqual(ramos_por_mes[mes], {"auto", "vida", "saude"})

    def test_monthly_values_are_repeatable(self):
        referencia = date(2026, 11, 9)

        self.assertEqual(
            gerar_comissoes_demonstracao(referencia),
            gerar_comissoes_demonstracao(referencia),
        )

    def test_rejects_non_positive_month_count(self):
        with self.assertRaises(ValueError):
            gerar_comissoes_demonstracao(date(2026, 11, 9), 0)


class RenovacaoApoliceTests(SimpleTestCase):
    def test_completed_renewal_requires_new_policy(self):
        renovacao = RenovacaoApolice(status="renovada")

        with self.assertRaises(ValidationError):
            renovacao.clean()

    def test_renewal_cannot_point_to_the_original_policy(self):
        renovacao = RenovacaoApolice(
            apolice_id=1,
            apolice_renovada_id=1,
            status="renovada",
        )

        with self.assertRaises(ValidationError):
            renovacao.clean()
