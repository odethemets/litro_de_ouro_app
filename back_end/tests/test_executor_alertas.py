"""Conexão e processador simulados; sem avisos reais ou espera de relógio."""
from datetime import datetime
from pathlib import Path
import ssl
import sys
from threading import Event
import unittest
from unittest.mock import MagicMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.executor_alertas import (
    Configuracao,
    FalhaExecucao,
    diagnosticar,
    executar_ciclo,
    executar_rodada,
    transitorio,
)


class ErroMySQL(Exception):
    pass


# Registra consultas sem acessar um banco real.
def conexao(banco="dev", pendentes=3):
    conn = MagicMock()

    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect = [
        {"banco": banco},
        {
            "pendentes": pendentes,
            "mais_antigo": datetime(2026, 11, 14, 12),
        },
    ]

    return conn, cursor


class RodadaTests(unittest.TestCase):
    def test_diagnostico_so_select_e_sem_commit(self):
        conn, cursor = conexao()
        conectar = Mock(return_value=conn)

        resultado = diagnosticar(Configuracao("dev"), conectar)

        conectar.assert_called_once_with(read_only=True)
        self.assertEqual(resultado["pendentes"], 3)
        self.assertEqual(
            resultado["evento_mais_antigo_utc"],
            "2026-11-14T12:00:00+00:00",
        )

        self.assertTrue(all(
            chamada.args[0].lstrip().startswith("SELECT")
            for chamada in cursor.execute.call_args_list
        ))

        conn.commit.assert_not_called()
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()

    def test_destino_diferente_nao_processa(self):
        conn, _ = conexao("outro")
        processar = Mock()

        with self.assertRaises(FalhaExecucao) as capturado:
            executar_rodada(
                Configuracao("dev"),
                Mock(return_value=conn),
                processar,
                Event(),
            )

        self.assertFalse(capturado.exception.transitoria)
        self.assertEqual(capturado.exception.confirmados, 0)

        processar.assert_not_called()
        conn.close.assert_called_once()

    def test_mesma_conexao_e_um_evento_por_chamada(self):
        conn, _ = conexao()
        processar = Mock(side_effect=[1, 1, 0])

        resultado = executar_rodada(
            Configuracao("dev"),
            Mock(return_value=conn),
            processar,
            Event(),
        )

        self.assertEqual(resultado["eventos_processados"], 2)
        self.assertEqual(processar.call_count, 3)

        self.assertTrue(all(
            chamada.args == (conn,)
            and chamada.kwargs == {"limite": 1}
            for chamada in processar.call_args_list
        ))

        conn.commit.assert_not_called()
        conn.close.assert_called_once()

    def test_limite_de_eventos_e_respeitado(self):
        conn, _ = conexao()
        processar = Mock(return_value=1)

        resultado = executar_rodada(
            Configuracao("dev", limite=2),
            Mock(return_value=conn),
            processar,
            Event(),
        )

        self.assertEqual(resultado["eventos_processados"], 2)
        self.assertEqual(processar.call_count, 2)

    def test_sinal_antes_da_rodada_nao_abre_conexao(self):
        parar = Event()
        parar.set()

        conectar = Mock()
        processar = Mock()

        resultado = executar_rodada(
            Configuracao("dev"),
            conectar,
            processar,
            parar,
        )

        self.assertTrue(resultado["interrompido"])
        self.assertFalse(resultado["destino_conferido"])

        conectar.assert_not_called()
        processar.assert_not_called()

    def test_sinal_durante_evento_impede_proximo_evento(self):
        conn, _ = conexao()
        parar = Event()

        def processar(_conn, limite):
            self.assertEqual(limite, 1)
            parar.set()
            return 1

        resultado = executar_rodada(
            Configuracao("dev"),
            Mock(return_value=conn),
            processar,
            parar,
        )

        self.assertEqual(resultado["eventos_processados"], 1)
        self.assertTrue(resultado["interrompido"])
        conn.close.assert_called_once()

    def test_falha_parcial_preserva_contagem_confirmada(self):
        conn, _ = conexao()

        processar = Mock(side_effect=[
            1,
            1,
            ErroMySQL(1213, "detalhe-sensivel"),
        ])

        with self.assertRaises(FalhaExecucao) as capturado:
            executar_rodada(
                Configuracao("dev"),
                Mock(return_value=conn),
                processar,
                Event(),
            )

        erro = capturado.exception

        self.assertTrue(erro.transitoria)
        self.assertTrue(erro.incerta)
        self.assertEqual(erro.confirmados, 2)
        self.assertNotIn("detalhe-sensivel", str(erro.dados()))

        conn.close.assert_called_once()

    def test_retorno_incompativel_nao_e_aceito(self):
        for retorno in (None, True, 2, -1, {"processados": 1}):
            conn, _ = conexao()

            with self.subTest(retorno=retorno):
                with self.assertRaises(FalhaExecucao) as capturado:
                    executar_rodada(
                        Configuracao("dev"),
                        Mock(return_value=conn),
                        Mock(return_value=retorno),
                        Event(),
                    )

                self.assertFalse(capturado.exception.transitoria)
                self.assertTrue(capturado.exception.incerta)
                conn.close.assert_called_once()

    def test_falha_no_rollback_preserva_erro_principal(self):
        conn, _ = conexao("outro")
        conn.rollback.side_effect = ErroMySQL(2013, "segredo")

        with self.assertRaises(FalhaExecucao) as capturado:
            executar_rodada(
                Configuracao("dev"),
                Mock(return_value=conn),
                Mock(),
                Event(),
            )

        self.assertEqual(
            capturado.exception.tipo,
            "DestinoIncorreto",
        )
        self.assertFalse(capturado.exception.transitoria)
        conn.close.assert_called_once()

    def test_falha_de_limpeza_preserva_contagem(self):
        conn, _ = conexao()
        conn.close.side_effect = ErroMySQL(2013, "segredo")

        with self.assertRaises(FalhaExecucao) as capturado:
            executar_rodada(
                Configuracao("dev", limite=1),
                Mock(return_value=conn),
                Mock(return_value=1),
                Event(),
            )

        self.assertEqual(capturado.exception.confirmados, 1)
        self.assertFalse(capturado.exception.incerta)

    def test_parametros_invalidos_nao_conectam(self):
        for extra in (
            {"limite": 0},
            {"limite": True},
            {"intervalo": 0},
            {"max_falhas": 21},
            {"recuo": 0},
        ):
            conectar = Mock()

            with self.subTest(extra=extra):
                with self.assertRaises(ValueError):
                    executar_rodada(
                        Configuracao("dev", **extra),
                        conectar,
                        Mock(),
                        Event(),
                    )

                conectar.assert_not_called()


class CicloTests(unittest.TestCase):
    def test_recuo_crescente_e_limite_de_falhas(self):
        esperar = Mock(return_value=False)
        emitir = Mock()

        rodada = Mock(
            side_effect=FalhaExecucao(
                ErroMySQL(2003, "segredo")
            )
        )

        codigo = executar_ciclo(
            Configuracao("dev", max_falhas=3),
            rodada,
            Event(),
            emitir,
            esperar,
        )

        self.assertEqual(codigo, 1)
        self.assertEqual(rodada.call_count, 3)
        self.assertEqual(
            [c.args[0] for c in esperar.call_args_list],
            [5, 10],
        )

    def test_falha_permanente_nao_repete(self):
        esperar = Mock()

        rodada = Mock(
            side_effect=FalhaExecucao(
                ErroMySQL(1045, "senha-nao-imprimir")
            )
        )

        codigo = executar_ciclo(
            Configuracao("dev"),
            rodada,
            Event(),
            Mock(),
            esperar,
        )

        self.assertEqual(codigo, 2)
        rodada.assert_called_once()
        esperar.assert_not_called()

    def test_sucesso_reinicia_contador_de_falhas(self):
        parar = Event()
        esperas = []
        resultados = iter(["falha", "falha", "ok", "falha", "fim"])

        def rodada():
            resultado = next(resultados)

            if resultado == "falha":
                raise FalhaExecucao(TimeoutError())

            if resultado == "fim":
                parar.set()

            return {"eventos_processados": 0}

        codigo = executar_ciclo(
            Configuracao("dev"),
            rodada,
            parar,
            Mock(),
            lambda segundos: esperas.append(segundos) or False,
        )

        self.assertEqual(codigo, 0)
        self.assertEqual(esperas, [5, 10, 30, 5])

    def test_espera_interrompida_nao_repete_rodada(self):
        rodada = Mock(return_value={"eventos_processados": 0})

        codigo = executar_ciclo(
            Configuracao("dev"),
            rodada,
            Event(),
            Mock(),
            Mock(return_value=True),
        )

        self.assertEqual(codigo, 0)
        rodada.assert_called_once()

    def test_teto_do_recuo_e_300_segundos(self):
        esperar = Mock(return_value=False)

        rodada = Mock(
            side_effect=FalhaExecucao(
                ErroMySQL(1213, "privado")
            )
        )

        executar_ciclo(
            Configuracao("dev", max_falhas=6, recuo=60),
            rodada,
            Event(),
            Mock(),
            esperar,
        )

        self.assertEqual(
            [c.args[0] for c in esperar.call_args_list],
            [60, 120, 240, 300, 300],
        )

    def test_certificado_invalido_nao_repete(self):
        try:
            try:
                raise ssl.SSLCertVerificationError(
                    "certificado-sintetico"
                )
            except ssl.SSLCertVerificationError as causa:
                raise ErroMySQL(2003, "conexao") from causa

        except ErroMySQL as erro:
            self.assertFalse(transitorio(erro))

        self.assertTrue(transitorio(ConnectionError()))
        self.assertFalse(transitorio(ErroMySQL(1146, "tabela")))


if __name__ == "__main__":
    unittest.main()