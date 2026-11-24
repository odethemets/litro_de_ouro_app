"""Permissão de cadastro calculada pela conta autenticada, nunca pelo cliente."""
from typing import TypedDict

from services.servicos_postos import administradores


class PoliticaPrecos(TypedDict):
    administrativo: bool
    exige_gps: bool
    karma_por_preco: int


def politica_precos(usuario_id: int) -> PoliticaPrecos:
    administrativo = usuario_id in administradores()
    return {
        "administrativo": administrativo,
        "exige_gps": not administrativo,
        "karma_por_preco": 0 if administrativo else 5,
    }