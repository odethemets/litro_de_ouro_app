"""Contrato da solicitação e permissões administrativas; sem Flask ou banco."""
import math
import os
import re

from services.catalogo_postos import CATALOGO


class RecusaServico(ValueError):
    def __init__(self, mensagem, status=400, codigo="SOLICITACAO_INVALIDA"):
        super().__init__(mensagem)
        self.status, self.codigo = status, codigo


def administradores():
    bruto = os.getenv("ADMIN_USUARIO_IDS", "").strip()
    if not bruto:
        return frozenset()
    partes = bruto.split(",")
    if len(partes) > 100 or any(
        not re.fullmatch(r"[1-9][0-9]{0,9}", p.strip())
        or int(p.strip()) > 2147483647 for p in partes
    ):
        raise RecusaServico("Configuração administrativa inválida.", 503, "ADMIN_INDISPONIVEL")
    return frozenset(int(p.strip()) for p in partes)


def exigir_admin(usuario_id):
    if usuario_id not in administradores():
        raise RecusaServico("Esta ação exige acesso administrativo.", 403, "ACESSO_NEGADO")


def texto(valor, limite, obrigatorio=False):
    if not isinstance(valor, str) or len(valor.strip()) > limite or any(
        ord(c) < 32 and c not in "\n\r\t" or ord(c) == 127 for c in valor
    ):
        raise RecusaServico("Informe um texto válido de até " + str(limite) + " caracteres.")
    valor = valor.strip()
    if obrigatorio and not valor:
        raise RecusaServico("Informe o motivo da rejeição.")
    return valor


def validar_envio(dados):
    codigo = dados.get("codigo")
    chave = dados.get("chave_cliente")
    if not isinstance(codigo, str) or codigo not in CATALOGO:
        raise RecusaServico("Selecione um serviço do catálogo.")
    if not isinstance(chave, str) or not re.fullmatch(r"[a-f0-9]{32}", chave):
        raise RecusaServico("Identificador de envio inválido.")
    if dados.get("consentimento") != "true" or dados.get("presenca_observada") != "true":
        raise RecusaServico("Confirme a presença observada e o envio da foto para revisão.")
    if dados.get("simulada") != "false":
        raise RecusaServico("Localização simulada ou não verificada.", 403, "GPS_SIMULADO")
    try:
        precisao = float(dados.get("precisao_m", ""))
        if not math.isfinite(precisao) or precisao < 0:
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        raise RecusaServico("Informe a precisão da localização atual.") from None
    return codigo, chave, texto(dados.get("observacao", ""), 500), precisao


def validar_decisao(dados):
    if not isinstance(dados, dict) or set(dados) - {"decisao", "motivo", "foto_revisada"}:
        raise RecusaServico("Envie uma decisão válida.")
    decisao = dados.get("decisao")
    if decisao not in ("aprovar", "rejeitar"):
        raise RecusaServico("Escolha aprovar ou rejeitar.")
    if decisao == "aprovar" and dados.get("foto_revisada") is not True:
        raise RecusaServico("Revise a foto e confirme que ela comprova o serviço.")
    motivo = texto(dados.get("motivo", ""), 500, decisao == "rejeitar")
    return "aprovada" if decisao == "aprovar" else "rejeitada", motivo


def oferta_efetiva(oferta):
    manual = oferta.get("disponivel_manual")
    return manual if manual is not None else oferta.get("disponivel_osm")


def produto_compativel(tipo_posto, codigo, disponivel=None):
    if not isinstance(codigo, str) or codigo not in CATALOGO:
        return False
    if tipo_posto == "Eletroposto":
        return codigo == "recarga_eletrica"
    # Posto convencional pode oferecer recarga sem perder os demais produtos.
    return codigo != "recarga_eletrica" or disponivel == 1