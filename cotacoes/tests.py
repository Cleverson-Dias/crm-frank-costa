from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .analytics import calcular_taxa_retencao
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
