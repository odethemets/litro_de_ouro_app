"""Diagnóstico por padrão; os modos explícitos processam a central de avisos."""
import argparse
from datetime import datetime, timezone
import importlib
import inspect
import json
from pathlib import Path
import signal
import sys
from threading import Event

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.executor_alertas import (
    Configuracao,
    ContratoFilaInvalido,
    FalhaExecucao,
    diagnosticar,
    executar_ciclo,
    executar_rodada,
)


# Exige o processador atual, que recebe a conexão verificada.
def dependencias():
    banco = importlib.import_module("services.database")
    atividade = importlib.import_module("services.atividade_alertas")

    processar = getattr(atividade, "processar_pendentes", None)

    if not callable(processar):
        raise ContratoFilaInvalido(
            "Processador atual da fila não encontrado."
        )

    try:
        inspect.signature(processar).bind(object(), limite=1)
    except (TypeError, ValueError):
        raise ContratoFilaInvalido(
            "Assinatura do processador incompatível."
        ) from None

    return banco.get_db_connection, processar


# Não imprime preços, nomes, SQL ou mensagens privadas de conexão.
def emitir(dados):
    print(
        json.dumps(
            {
                "instante_utc": datetime.now(timezone.utc).isoformat(),
                **dados,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


# Os handlers sinalizam a parada; não interrompem uma transação à força.
def instalar_sinais(parar):
    anteriores = {}

    for nome in ("SIGINT", "SIGTERM"):
        tipo = getattr(signal, nome, None)

        if tipo is not None:
            anteriores[tipo] = signal.getsignal(tipo)
            signal.signal(tipo, lambda _s, _f: parar.set())

    return anteriores


def restaurar_sinais(anteriores):
    for tipo, anterior in anteriores.items():
        signal.signal(tipo, anterior)


# O nome exato do banco é obrigatório em todos os modos.
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--banco",
        required=True,
        help="Nome exato do banco esperado.",
    )

    modos = parser.add_mutually_exclusive_group()

    modos.add_argument(
        "--uma-rodada",
        action="store_true",
        help="Processa até --limite eventos e termina.",
    )

    modos.add_argument(
        "--continuo",
        action="store_true",
        help="Processa periodicamente até interrupção/falha.",
    )

    parser.add_argument("--limite", type=int, default=100)
    parser.add_argument("--intervalo", type=int, default=30)
    parser.add_argument("--max-falhas", type=int, default=5)
    parser.add_argument("--recuo", type=int, default=5)

    args = parser.parse_args(argv)

    config = Configuracao(
        args.banco,
        args.limite,
        args.intervalo,
        args.max_falhas,
        args.recuo,
    )

    modo = (
        "continuo"
        if args.continuo
        else "uma_rodada"
        if args.uma_rodada
        else "diagnostico"
    )

    anteriores = {}

    try:
        config.validar()
        conectar, processar = dependencias()

        if modo == "diagnostico":
            emitir({
                "status": "ok",
                "modo": modo,
                "assinatura_processador_compativel": True,
                **diagnosticar(config, conectar),
            })
            return 0

        parar = Event()
        anteriores = instalar_sinais(parar)

        def rodada():
            return executar_rodada(
                config,
                conectar,
                processar,
                parar,
            )

        if modo == "uma_rodada":
            emitir({
                "status": "ok",
                "modo": modo,
                **rodada(),
            })
            return 0

        emitir({
            "status": "executor_iniciado",
            "modo": modo,
            "limite": config.limite,
            "intervalo_segundos": config.intervalo,
        })

        return executar_ciclo(
            config,
            rodada,
            parar,
            emitir,
        )

    except FalhaExecucao as erro:
        emitir({
            "status": "falha",
            "modo": modo,
            **erro.dados(),
        })
        return 1 if erro.transitoria else 2

    except Exception as erro:
        emitir({
            "status": "configuracao_ou_contrato_invalido",
            "modo": modo,
            "erro_tipo": type(erro).__name__,
        })
        return 2

    finally:
        restaurar_sinais(anteriores)


if __name__ == "__main__":
    raise SystemExit(main())