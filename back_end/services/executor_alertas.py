"""Operação da fila existente; sem novas regras de assinatura ou transporte push."""
from dataclasses import dataclass
from datetime import datetime, timezone
import ssl


class DestinoIncorreto(ValueError):
    pass


class ContratoFilaInvalido(ValueError):
    pass


@dataclass(frozen=True)
class Configuracao:
    banco: str
    limite: int = 100
    intervalo: int = 30
    max_falhas: int = 5
    recuo: int = 5

    # Impede lote ilimitado e consultas em laço sem espera.
    def validar(self):
        if (
            not isinstance(self.banco, str)
            or not 1 <= len(self.banco) <= 64
            or self.banco != self.banco.strip()
            or any(ord(c) < 32 or ord(c) == 127 for c in self.banco)
        ):
            raise ValueError("Informe o nome exato do banco esperado.")

        for valor, minimo, maximo in (
            (self.limite, 1, 1000),
            (self.intervalo, 5, 3600),
            (self.max_falhas, 1, 20),
            (self.recuo, 1, 60),
        ):
            if type(valor) is not int or not minimo <= valor <= maximo:
                raise ValueError("Parâmetros do executor fora dos limites.")


# Identifica códigos sem usar mensagens privadas de conexão.
def codigo_mysql(erro):
    valor = erro.args[0] if getattr(erro, "args", None) else None
    return valor if type(valor) is int and 1000 <= valor <= 2999 else None


def transitorio(erro):
    atual, vistos = erro, set()

    for _ in range(8):
        if atual is None or id(atual) in vistos:
            break

        vistos.add(id(atual))

        if isinstance(atual, ssl.SSLCertVerificationError):
            return False

        atual = atual.__cause__ or atual.__context__

    if isinstance(erro, (DestinoIncorreto, ContratoFilaInvalido)):
        return False

    if codigo_mysql(erro) in {
        1040, 1205, 1213, 2002, 2003, 2006, 2013, 2055
    }:
        return True

    return isinstance(erro, (TimeoutError, ConnectionError, OSError))


class FalhaExecucao(RuntimeError):
    # Não serializa o texto da exceção de conexão.
    def __init__(self, erro, confirmados=0, incerta=False):
        super().__init__("Não foi possível concluir a operação da fila.")
        self.tipo = type(erro).__name__
        self.codigo = codigo_mysql(erro)
        self.transitoria = transitorio(erro)
        self.confirmados = confirmados
        self.incerta = incerta

    def dados(self):
        return {
            "erro_tipo": self.tipo,
            "codigo_mysql": self.codigo,
            "transitoria": self.transitoria,
            "eventos_confirmados_minimos": self.confirmados,
            "ultima_operacao_incerta": self.incerta,
        }


# Confere a mesma conexão que será entregue ao processador.
def conferir_banco(conn, esperado):
    with conn.cursor() as cursor:
        cursor.execute("SELECT DATABASE() AS banco")
        registro = cursor.fetchone()

    if not isinstance(registro, dict) or registro.get("banco") != esperado:
        raise DestinoIncorreto(
            "A conexão não corresponde ao banco esperado."
        )


# Fecha mesmo quando rollback falha e preserva a primeira falha.
def encerrar_conexao(conn, falha=None, confirmados=0):
    if conn is not None:
        for acao in (conn.rollback, conn.close):
            try:
                acao()
            except Exception as erro:
                if falha is None:
                    falha = FalhaExecucao(erro, confirmados, False)

    return falha


# Consulta a fila sem processar eventos ou criar notificações.
def diagnosticar(config, conectar):
    config.validar()
    conn, falha, dados = None, None, None

    try:
        conn = conectar(read_only=True)
        conferir_banco(conn, config.banco)

        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) AS pendentes,
                       MIN(criado_em) AS mais_antigo
                FROM eventos_preco
                WHERE processado_em IS NULL
            """)
            registro = cursor.fetchone()

        if (
            not isinstance(registro, dict)
            or type(registro.get("pendentes")) is not int
            or registro["pendentes"] < 0
        ):
            raise ContratoFilaInvalido("Resumo da fila inválido.")

        data = registro.get("mais_antigo")

        if isinstance(data, datetime):
            # Os eventos existentes são gravados em UTC.
            if data.tzinfo is None:
                data = data.replace(tzinfo=timezone.utc)

            data = data.astimezone(timezone.utc).isoformat()
        else:
            data = None

        dados = {
            "destino_conferido": True,
            "pendentes": registro["pendentes"],
            "evento_mais_antigo_utc": data,
        }

    except Exception as erro:
        falha = FalhaExecucao(erro)

    finally:
        falha = encerrar_conexao(conn, falha)

    if falha is not None:
        raise falha from None

    return dados


# Uma chamada por evento permite parar entre transações.
def executar_rodada(config, conectar, processar, parar):
    config.validar()

    if parar.is_set():
        return {
            "eventos_processados": 0,
            "interrompido": True,
            "destino_conferido": False,
        }

    conn, falha = None, None
    confirmados, incerta = 0, False

    try:
        conn = conectar()
        conferir_banco(conn, config.banco)
        conn.rollback()

        for _ in range(config.limite):
            if parar.is_set():
                break

            incerta = True
            quantidade = processar(conn, limite=1)

            if type(quantidade) is not int or quantidade not in (0, 1):
                raise ContratoFilaInvalido(
                    "O processador deve devolver zero ou um evento."
                )

            incerta = False
            confirmados += quantidade

            if quantidade == 0:
                break

    except Exception as erro:
        falha = FalhaExecucao(erro, confirmados, incerta)

    finally:
        falha = encerrar_conexao(conn, falha, confirmados)

    if falha is not None:
        raise falha from None

    return {
        "eventos_processados": confirmados,
        "interrompido": parar.is_set(),
        "destino_conferido": True,
    }


# Aplica espera interrompível e recuo limitado após falhas temporárias.
def executar_ciclo(config, rodada, parar, emitir, esperar=None):
    config.validar()
    esperar = parar.wait if esperar is None else esperar
    falhas = 0

    while not parar.is_set():
        try:
            dados = rodada()
            falhas = 0
            emitir({"status": "rodada_concluida", **dados})
            espera = config.intervalo

        except FalhaExecucao as erro:
            falhas += 1

            emitir({
                "status": "falha_rodada",
                "falhas_consecutivas": falhas,
                **erro.dados(),
            })

            if not erro.transitoria:
                return 2

            if falhas >= config.max_falhas:
                emitir({"status": "limite_de_falhas"})
                return 1

            espera = min(config.recuo * (2 ** (falhas - 1)), 300)

        if not parar.is_set() and esperar(espera):
            break

    emitir({"status": "executor_encerrado"})
    return 0