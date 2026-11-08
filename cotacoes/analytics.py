from typing import Optional


PARECERES_FAVORAVEIS = frozenset({
    "Aprovada",
    "Aprovada com Fator de Risco",
    "Cobertura Autorizada",
    "Atendimento Liberado",
})


def calcular_taxa_retencao(renovadas: int, elegiveis: int) -> Optional[float]:
    if renovadas < 0 or elegiveis < 0 or renovadas > elegiveis:
        raise ValueError("A quantidade de renovações deve estar entre zero e o total elegível.")
    if elegiveis == 0:
        return None
    return round(renovadas / elegiveis * 100, 1)
