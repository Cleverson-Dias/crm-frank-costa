"""
utils.py
--------
Funções auxiliares de normalização de dados.

Usadas antes de qualquer gravação no banco envolvendo CPF ou telefone,
para evitar que o mesmo CPF seja tratado como "diferente" só por causa
de pontuação ou espaços digitados de forma inconsistente
(ex: "289.891.008-28" vs "28989100828" vs "289.891.008-28 " com espaço).
"""

import re


def somente_digitos(texto: str) -> str:
    """Remove tudo que não for dígito. Ex: '289.891.008-28' -> '28989100828'."""
    return re.sub(r"\D", "", texto or "")