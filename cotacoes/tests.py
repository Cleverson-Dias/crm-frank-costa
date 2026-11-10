from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .analytics import calcular_taxa_retencao, gerar_comissoes_demonstracao
from .motor_ia import avaliar_elegibilidade, calcular_proposta
from .models import Cliente, Cotacao, Plano, RenovacaoApolice, Seguradora, TipoSeguro
from .views import montar_perfil_cotacao


class FormularioCotacaoTests(SimpleTestCase):
    def test_unimplemented_active_branch_is_not_treated_as_health(self):
        with self.assertRaisesMessage(ValueError, "ainda não possui uma análise automática"):
            montar_perfil_cotacao({"idade": "35", "valor_bem": "1000"}, "residencial")

    def test_auto_profile_captures_vehicle_and_driver_data(self):
        perfil, valor_estimado, _, descricao = montar_perfil_cotacao(
            {
                "idade": "35",
                "valor_bem": "85000",
                "marca_veiculo": "Toyota",
                "modelo_veiculo": "Corolla XEi",
                "ano_modelo": "2022",
                "uso_veiculo": "trabalho",
                "tempo_habilitacao_anos": "10",
                "sinistros_ultimos_3_anos": "1",
                "condutor_adicional": "on",
                "idade_condutor_adicional": "22",
            },
            "auto",
            ano_atual=2026,
        )

        self.assertEqual(valor_estimado, Decimal("85000"))
        self.assertEqual(descricao, "Toyota Corolla XEi - 2022")
        self.assertEqual(perfil["marca_veiculo"], "Toyota")
        self.assertEqual(perfil["ano_modelo"], 2022)
        self.assertTrue(perfil["uso_profissional"])
        self.assertEqual(perfil["idade_condutor_adicional"], 22)

    def test_life_profile_does_not_include_vehicle_fields(self):
        perfil, valor_estimado, _, _ = montar_perfil_cotacao(
            {"idade": "35", "valor_bem": "300000", "dps_completa": "on"},
            "vida",
            ano_atual=2026,
        )

        self.assertEqual(valor_estimado, Decimal("300000"))
        self.assertEqual(perfil["capital_segurado"], 300000)
        self.assertNotIn("marca_veiculo", perfil)
        self.assertNotIn("uso_veiculo", perfil)

    def test_health_profile_annualizes_monthly_premium_without_vehicle_fields(self):
        perfil, valor_estimado, valor_mensal, _ = montar_perfil_cotacao(
            {
                "idade": "35",
                "valor_bem": "850",
                "segmentacao_contratada": "referencia",
                "tipo_atendimento": "demais",
                "cobertura_exigida": "ambulatorial",
                "dias_contrato": "120",
            },
            "saude",
            ano_atual=2026,
        )

        self.assertEqual(valor_mensal, Decimal("850"))
        self.assertEqual(valor_estimado, Decimal("10200"))
        self.assertEqual(perfil["valor_bem"], 10200)
        self.assertNotIn("marca_veiculo", perfil)

    def test_auto_requires_vehicle_identification(self):
        with self.assertRaisesMessage(ValueError, "Informe a marca e o modelo do veículo."):
            montar_perfil_cotacao(
                {
                    "idade": "35",
                    "valor_bem": "85000",
                    "marca_veiculo": "",
                    "modelo_veiculo": "Corolla",
                    "ano_modelo": "2022",
                    "uso_veiculo": "passeio",
                    "tempo_habilitacao_anos": "10",
                    "sinistros_ultimos_3_anos": "0",
                },
                "auto",
                ano_atual=2026,
            )


class MotorPorRamoTests(SimpleTestCase):
    def test_auto_uses_auto_rules_and_rate(self):
        perfil = {"tipo_seguro": "auto", "idade": 35, "valor_bem": 80_000}

        parecer = avaliar_elegibilidade(perfil)
        proposta = calcular_proposta("auto", 80_000, 1)

        self.assertEqual(parecer["status"], "Aprovada")
        self.assertEqual(proposta["premio"], 3600.0)

    def test_auto_additional_young_driver_receives_risk_factor(self):
        parecer = avaliar_elegibilidade({
            "tipo_seguro": "auto",
            "idade": 35,
            "valor_bem": 80_000,
            "idade_condutor_adicional": 22,
        })

        self.assertEqual(parecer["status"], "Aprovada com Fator de Risco")
        self.assertEqual(parecer["regra_id"], "R-011")

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


class CadastroComercialTests(SimpleTestCase):
    def test_person_company_requires_cnpj_instead_of_cpf(self):
        cliente = Cliente(tipo_pessoa="pj", nome="Empresa")

        with self.assertRaises(ValidationError) as contexto:
            cliente.clean()

        self.assertIn("cnpj", contexto.exception.message_dict)

    def test_person_company_rejects_personal_document(self):
        cliente = Cliente(
            tipo_pessoa="pj",
            nome="Empresa",
            cpf="12345678901",
            cnpj="12345678000199",
        )

        with self.assertRaises(ValidationError) as contexto:
            cliente.clean()

        self.assertIn("cpf", contexto.exception.message_dict)

    def test_unknown_commission_remains_unset(self):
        seguradora = Seguradora(nome="Seguradora", cnpj="123")
        plano = Plano(
            seguradora=seguradora,
            tipo_seguro="vida",
            nome="Produto",
        )

        self.assertIsNone(plano.comissao_efetiva())

    def test_bradesco_health_quote_requires_multiple_lives(self):
        cliente = Cliente(
            id=1,
            tipo_pessoa="pj",
            nome="Empresa",
            cnpj="12345678000199",
        )
        tipo = TipoSeguro(id=1, codigo="saude", nome="Saúde")
        seguradora = Seguradora(id=1, nome="Bradesco Saúde", cnpj=None)
        cotacao = Cotacao(
            cliente=cliente,
            tipo_seguro=tipo,
            seguradora=seguradora,
            quantidade_vidas=1,
        )

        with self.assertRaisesMessage(ValidationError, "pelo menos duas vidas"):
            cotacao.clean()

        cotacao.quantidade_vidas = 2
        cotacao.clean()
