"""Política real e DML SQLite; GitHub e servidor TiDB simulados."""

from argparse import Namespace
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import test_osm_online as fixture

from scripts import operar_osm_github as runner
from services import operacao_osm as policy
from services.osm_online import FalhaOSM, sincronizar


def ambiente():
    return {
        "OSM_APLICAR": "true",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_RUN_ID": "100",
        "GITHUB_REPOSITORY": "exemplo/projeto",
    }


class PoliticaTests(unittest.TestCase):
    def test_limites_recusam_excesso_e_booleanos(self):
        casos = [(21, 0), (0, 1001), (True, 0), (-1, 0)]

        for novos, metas in casos:
            with self.subTest(novos=novos, metas=metas):
                with self.assertRaises(policy.ErroOperacao):
                    policy.validar_limites({
                        "status": "ok",
                        "catalogo": {"novos": novos},
                        "metadados_planejados": metas,
                    })

    def test_preview_falha_nao_pode_autorizar_escrita(self):
        with self.assertRaises(policy.ErroOperacao):
            policy.validar_limites({
                "status": "interrompido",
            })

    def test_historico_bloqueia_falha_ate_conferencia_explicita(self):
        consulta = Mock(return_value={
            "workflow_runs": [
                {"id": 99, "conclusion": "failure"},
            ]
        })
        env = ambiente()

        with self.assertRaisesRegex(
            policy.ErroOperacao, "conferencia_manual"
        ):
            policy.verificar_historico(env, consulta)

        env["OSM_FALHA_REVISADA_RUN_ID"] = "99"
        policy.verificar_historico(env, consulta)

    def test_nova_falha_nao_e_liberada_por_revisao_antiga(self):
        env = dict(
            ambiente(),
            OSM_FALHA_REVISADA_RUN_ID="90",
        )
        consulta = Mock(return_value={
            "workflow_runs": [
                {"id": 95, "conclusion": "cancelled"},
            ]
        })

        with self.assertRaises(policy.ErroOperacao):
            policy.verificar_historico(env, consulta)

    def test_reexecucao_e_outra_branch_nao_escrevem(self):
        casos = [
            ("GITHUB_RUN_ATTEMPT", "2"),
            ("GITHUB_REF", "refs/heads/teste"),
        ]

        for campo, valor in casos:
            with self.subTest(campo=campo):
                with self.assertRaises(policy.ErroOperacao):
                    policy.verificar_historico(
                        dict(ambiente(), **{campo: valor}),
                        Mock(),
                    )

    def test_historico_sucesso_e_atual_em_execucao_sao_aceitos(self):
        consulta = Mock(return_value={
            "workflow_runs": [
                {"id": 100, "conclusion": None},
                {"id": 99, "conclusion": "success"},
            ]
        })

        policy.verificar_historico(ambiente(), consulta)

    def test_backup_deve_pertencer_ao_run_atual_e_nao_estar_expirado(self):
        dados = {
            "id": 50,
            "name": "osm-backup-100-1",
            "expired": False,
            "workflow_run": {"id": 100},
        }

        policy.verificar_artefato(
            ambiente(),
            "50",
            Mock(return_value=dados),
        )

        mudancas = [
            {"expired": True},
            {"name": "outro"},
            {"workflow_run": {"id": 99}},
        ]

        for mudanca in mudancas:
            with self.subTest(mudanca=mudanca):
                with self.assertRaises(policy.ErroOperacao):
                    policy.verificar_artefato(
                        ambiente(),
                        "50",
                        Mock(return_value={
                            **dados,
                            **mudanca,
                        }),
                    )

    def test_ausencia_de_backup_remoto_nao_e_aceita(self):
        for ident in (None, "", "0", "texto"):
            with self.subTest(ident=ident):
                with self.assertRaises(policy.ErroOperacao):
                    policy.verificar_artefato(
                        ambiente(), ident, Mock()
                    )

    def test_backup_exige_hash_destino_fonte_e_janela(self):
        agora = datetime.now(timezone.utc)

        original = {
            "versao": 1,
            "capturado_em_utc": agora.isoformat(),
            "estado": {
                "banco": "catalogo",
                "fonte_sha256": "f" * 64,
            },
        }

        bruto = json.dumps(original).encode()
        sha = hashlib.sha256(bruto).hexdigest()

        policy.validar_backup(
            bruto, sha, "catalogo", "f" * 64, agora
        )

        casos = [
            ("a" * 64, "catalogo", "f" * 64, agora),
            (sha, "outro", "f" * 64, agora),
            (sha, "catalogo", "b" * 64, agora),
            (
                sha,
                "catalogo",
                "f" * 64,
                agora + timedelta(hours=3),
            ),
        ]

        for hash_, banco, fonte, instante in casos:
            with self.subTest(banco=banco, fonte=fonte):
                with self.assertRaises(policy.ErroOperacao):
                    policy.validar_backup(
                        bruto, hash_, banco, fonte, instante
                    )

    def test_conta_de_escrita_nunca_usa_fallback_de_leitura(self):
        env = {
            "OSM_DB_USER": "leitor",
            "OSM_DB_PASSWORD": "segredo-leitor",
        }

        self.assertEqual(
            runner.credenciais(env, False)["DB_USER"],
            "leitor",
        )
        self.assertEqual(
            runner.credenciais(env, True)["DB_USER"],
            "",
        )

    def test_modo_padrao_e_leitura(self):
        self.assertFalse(runner.definir_escrita({}))

        with self.assertRaises(policy.ErroOperacao):
            runner.definir_escrita({
                "OSM_APLICAR": "talvez",
            })

    def test_backup_nao_inclui_identidade_de_autor_manual(self):
        dados = {
            "banco": "catalogo",
            "fonte_sha256": "f" * 64,
            "postos": [],
            "ofertas": [{
                "posto_id": 1,
                "combustivel_codigo": "diesel",
                "manual_atualizado_por": 12345,
                "disponivel_manual": 0,
            }],
        }

        resultado = policy.minimizar_estado(dados)

        self.assertNotIn(
            "manual_atualizado_por",
            resultado["ofertas"][0],
        )
        self.assertEqual(
            resultado["ofertas"][0]["disponivel_manual"],
            0,
        )


class TransacaoTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture.OSMTests(
            "test_previa_inclui_metadados_dos_novos_sem_escrever"
        )
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)

        self.banco = self.base.banco
        self.raiz = self.base.pasta / "operacao"
        self.preparo = self.raiz / "preparar"
        self.preparo.mkdir(parents=True)

        self.env = ambiente()

        def executar(*args, **kwargs):
            return sincronizar(
                *args,
                **kwargs,
                verificar=Mock(),
            )

        self.patch_core = patch.object(
            runner,
            "sincronizar",
            side_effect=executar,
        )
        self.patch_core.start()
        self.addCleanup(self.patch_core.stop)

        for nome in (
            "verificar_historico",
            "verificar_artefato",
        ):
            substituicao = patch.object(runner, nome)
            substituicao.start()
            self.addCleanup(substituicao.stop)

    def preparar(self):
        return runner.preparar(
            self.banco,
            self.base.fonte,
            self.base.lugares,
            self.base.migracoes,
            "catalogo",
            self.preparo,
            True,
            self.env,
        )

    def aplicar(self):
        pasta = self.raiz / "aplicar"
        pasta.mkdir()

        bruto = (
            self.preparo / "backup_catalogo.json"
        ).read_bytes()

        args = Namespace(
            artefato_backup="50",
            backup_sha256=hashlib.sha256(bruto).hexdigest(),
        )

        return runner.aplicar(
            self.banco,
            self.base.fonte,
            self.base.lugares,
            self.base.migracoes,
            "catalogo",
            pasta,
            self.raiz,
            args,
            self.env,
        )

    def test_ciclo_completo_e_repeticao_sem_novos(self):
        self.assertEqual(
            self.preparar()["catalogo"]["novos"], 1
        )

        self.assertFalse(any(
            sql.startswith(("INSERT", "UPDATE", "DELETE"))
            for sql in self.banco.sql
        ))

        resultado = self.aplicar()

        self.assertEqual(
            resultado["catalogo"]["inseridos"], 1
        )
        self.assertEqual(
            resultado["metadados_aplicados"], 2
        )

        repeticao = self.base.executar()

        self.assertEqual(
            repeticao["catalogo"]["novos"], 0
        )
        self.assertEqual(
            repeticao["metadados_planejados"], 0
        )

    def test_falha_de_persistencia_local_do_backup_impede_preparacao(self):
        with patch.object(
            runner,
            "gravar",
            side_effect=OSError("sem-disco"),
        ):
            with self.assertRaises(OSError):
                self.preparar()

        quantidade = self.banco.db.execute(
            "SELECT COUNT(*) FROM postos"
        ).fetchone()[0]

        self.assertEqual(quantidade, 0)

    def test_plano_diferente_causa_rollback_dos_inserts(self):
        self.preparar()

        arquivo = self.preparo / "backup_catalogo.json"
        dados = json.loads(arquivo.read_text())

        dados["previa"]["plano_metadados"][0]["valor"] = (
            "Outra marca"
        )

        arquivo.write_text(json.dumps(dados))

        with self.assertRaises(FalhaOSM) as falha:
            self.aplicar()

        self.assertEqual(
            falha.exception.codigo,
            "plano_mudou_apos_a_previa",
        )
        self.assertFalse(falha.exception.commit_incerto)

        self.assertTrue(any(
            sql.lstrip().startswith("INSERT INTO postos")
            for sql in self.banco.sql
        ))

        quantidade = self.banco.db.execute(
            "SELECT COUNT(*) FROM postos"
        ).fetchone()[0]

        self.assertEqual(quantidade, 0)

    def test_mudanca_manual_apos_backup_bloqueia_sem_sobrescrever(self):
        self.base.executar(True)
        self.preparar()

        self.banco.db.execute(
            "UPDATE postos "
            "SET marca='Minha marca',marca_origem='manual'"
        )

        with self.assertRaises(FalhaOSM) as falha:
            self.aplicar()

        self.assertEqual(
            falha.exception.codigo,
            "estado_mudou_apos_o_backup",
        )

        marca = self.banco.db.execute(
            "SELECT marca FROM postos"
        ).fetchone()[0]

        self.assertEqual(marca, "Minha marca")

    def test_erro_na_confirmacao_do_commit_nao_repete_escrita(self):
        self.preparar()
        self.banco.falhar_commit = True

        with self.assertRaises(FalhaOSM) as falha:
            self.aplicar()

        self.assertTrue(falha.exception.commit_incerto)

        quantidade = self.banco.db.execute(
            "SELECT COUNT(*) FROM postos"
        ).fetchone()[0]

        self.assertEqual(quantidade, 1)
        self.assertEqual(runner.sincronizar.call_count, 2)

    def test_limiar_inferior_ao_plano_impede_commit(self):
        self.preparar()
        self.env["OSM_MAX_NOVOS"] = "0"

        with self.assertRaises(policy.ErroOperacao):
            self.aplicar()

        quantidade = self.banco.db.execute(
            "SELECT COUNT(*) FROM postos"
        ).fetchone()[0]

        self.assertEqual(quantidade, 0)

    def ambiente_cli(self):
        self.banco.nome = "litro_de_ouro"

        env = dict(
            ambiente(),
            OSM_APLICAR="false",
            OSM_BANCO_ESPERADO="litro_de_ouro",
            OSM_FONTE_ARQUIVO=str(self.base.arquivo),
            OSM_FONTE_SHA256=hashlib.sha256(
                self.base.arquivo.read_bytes()
            ).hexdigest(),
            OSM_SAIDA=str(self.base.pasta / "cli"),
        )

        for prefixo in ("OSM_", "OSM_WRITE_"):
            env.update({
                prefixo + "DB_HOST": "banco.exemplo",
                prefixo + "DB_PORT": "4000",
                prefixo + "DB_USER": "operador",
                prefixo + "DB_PASSWORD": "SEGREDO_NAO_LOGAR",
                prefixo + "DB_NAME": "litro_de_ouro",
            })

        return env

    def test_cli_prepara_aplica_e_confere_sem_expor_credenciais(self):
        env = self.ambiente_cli()
        saida = io.StringIO()

        with (
            patch.object(
                runner,
                "get_db_connection",
                return_value=self.banco,
            ) as conectar,
            patch("sys.stdout", saida),
        ):
            self.assertEqual(
                runner.main(["--fase", "preparar"], env),
                0,
            )

            backup = (
                Path(env["OSM_SAIDA"])
                / "preparar/backup_catalogo.json"
            )

            env["OSM_APLICAR"] = "true"

            args = [
                "--fase",
                "aplicar",
                "--backup-sha256",
                hashlib.sha256(
                    backup.read_bytes()
                ).hexdigest(),
                "--artefato-backup",
                "50",
            ]

            self.assertEqual(runner.main(args, env), 0)

            self.assertEqual(
                runner.main(["--fase", "conferir"], env),
                0,
            )

        self.assertNotIn(
            "SEGREDO_NAO_LOGAR",
            saida.getvalue(),
        )

        self.assertEqual(
            [
                chamada.kwargs["read_only"]
                for chamada in conectar.call_args_list
            ],
            [True, False, True],
        )

        resultado = json.loads(
            (
                Path(env["OSM_SAIDA"])
                / "conferir/relatorio.json"
            ).read_text()
        )

        self.assertEqual(
            resultado["metadados_planejados"], 0
        )
        self.assertEqual(
            resultado["catalogo"]["novos"], 0
        )

    def test_cli_nao_aplica_quando_flag_esta_desligada(self):
        env = self.ambiente_cli()

        with (
            patch.object(
                runner, "get_db_connection"
            ) as conectar,
            patch("sys.stdout", io.StringIO()),
        ):
            self.assertEqual(
                runner.main(["--fase", "aplicar"], env),
                1,
            )

        conectar.assert_not_called()

    def test_cli_commit_incerto_e_registrado_e_nao_repetido(self):
        env = self.ambiente_cli()

        with (
            patch.object(
                runner,
                "get_db_connection",
                return_value=self.banco,
            ),
            patch("sys.stdout", io.StringIO()),
        ):
            self.assertEqual(
                runner.main(["--fase", "preparar"], env),
                0,
            )

            backup = (
                Path(env["OSM_SAIDA"])
                / "preparar/backup_catalogo.json"
            )

            env["OSM_APLICAR"] = "true"
            self.banco.falhar_commit = True

            args = [
                "--fase",
                "aplicar",
                "--backup-sha256",
                hashlib.sha256(
                    backup.read_bytes()
                ).hexdigest(),
                "--artefato-backup",
                "50",
            ]

            self.assertEqual(runner.main(args, env), 1)

        resultado = json.loads(
            (
                Path(env["OSM_SAIDA"])
                / "aplicar/relatorio.json"
            ).read_text()
        )

        self.assertEqual(
            resultado["status"], "commit_incerto"
        )
        self.assertEqual(
            runner.sincronizar.call_count, 2
        )

        quantidade = self.banco.db.execute(
            "SELECT COUNT(*) FROM postos"
        ).fetchone()[0]

        self.assertEqual(quantidade, 1)


if __name__ == "__main__":
    unittest.main()