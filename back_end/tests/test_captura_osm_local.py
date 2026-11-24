"""Testes da captura municipal local, com transporte simulado."""
import builtins
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def fonte(agora=None) -> dict[str, Any]:
    agora = (
        datetime.now(timezone.utc)
        if agora is None
        else agora
    )

    return {
        "osm3s": {
            "timestamp_osm_base": agora.isoformat(),
        },
        "elements": [
            {
                "type": "area",
                "id": 3600000001,
                "tags": {
                    "boundary": "administrative",
                    "admin_level": "8",
                    "IBGE:GEOCODIGO": "2507507",
                },
            },
            {
                "type": "node",
                "id": 123,
                "lat": -7.1,
                "lon": -34.9,
                "tags": {
                    "amenity": "fuel",
                    "name": "Posto teste",
                },
            },
        ],
    }


def bruto(dados) -> bytes:
    return (
        json.dumps(dados, ensure_ascii=False) + "\n"
    ).encode("utf-8")


class CapturaLocalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = Path(self.tmp.name)

        spec = importlib.util.spec_from_file_location(
            "captura_local",
            ROOT / "scripts/capturar_osm_local.py",
        )

        if spec is None or spec.loader is None:
            raise RuntimeError(
                "Script de captura indisponivel"
            )

        self.mod = importlib.util.module_from_spec(spec)
        original = builtins.__import__

        def importar(nome, *args, **kwargs):
            if nome in (
                "app",
                "pymysql",
                "services.database",
                "dotenv",
            ):
                raise AssertionError(
                    "Captura nao deve importar app/banco/.env"
                )

            return original(nome, *args, **kwargs)

        with patch(
            "builtins.__import__",
            side_effect=importar,
        ):
            spec.loader.exec_module(self.mod)

    def executar(
        self,
        dados: bytes,
        *,
        http=200,
        curl=0,
        versao="1.1",
        ip="2001:db8::1",
    ) -> tuple[
        int,
        dict[str, Any],
        Path,
        list[list[str]],
    ]:
        saida = self.pasta / "saida"
        chamadas: list[list[str]] = []

        def executar(argv, **opcoes):
            chamadas.append(list(argv))

            Path(
                argv[argv.index("--output") + 1]
            ).write_bytes(dados)

            return subprocess.CompletedProcess(
                argv,
                curl,
                stdout=json.dumps({
                    "response_code": http,
                    "http_version": versao,
                    "remote_ip": ip,
                    "ssl_verify_result": 0,
                    "time_total": 0.9,
                    "campo_extra": "VALOR-FICTICIO",
                }),
                stderr="VALOR-FICTICIO",
            )

        with patch(
            "sys.stdout",
            new_callable=io.StringIO,
        ) as stdout:
            codigo = self.mod.main(
                ["--saida", str(saida), "--ipv6"],
                executar=executar,
            )

        relatorio = json.loads(
            (saida / "relatorio.json").read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(relatorio, dict):
            raise AssertionError(
                "Relatorio precisa ser objeto JSON"
            )

        self.assertNotIn(
            "VALOR-FICTICIO",
            stdout.getvalue(),
        )
        self.assertFalse(
            relatorio["mysql_consultado"]
        )
        self.assertFalse(
            relatorio["gravacao_banco_habilitada"]
        )
        self.assertFalse(
            (saida / "resposta.tmp").exists()
        )

        return codigo, relatorio, saida, chamadas

    def test_sucesso_preserva_bytes_hash_e_perfil(self):
        original = bruto(fonte())

        codigo, relatorio, saida, chamadas = (
            self.executar(original)
        )

        self.assertEqual(codigo, 0)
        self.assertEqual(relatorio["status"], "ok")
        self.assertTrue(
            relatorio["consulta_municipal_validada"]
        )
        self.assertEqual(
            (saida / "fonte.json").read_bytes(),
            original,
        )

        sha = hashlib.sha256(original).hexdigest()

        self.assertEqual(
            relatorio["sha256_fonte"],
            sha,
        )

        manifesto = json.loads(
            (saida / "manifesto.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(
            manifesto["arquivos"]["fonte.json"],
            sha,
        )
        self.assertEqual(len(chamadas), 1)

        comando = chamadas[0]

        for item in (
            "--http1.1",
            "--ipv6",
            "=https",
            "POST",
        ):
            self.assertIn(item, comando)

        for item in (
            "--insecure",
            "-k",
            "--location",
        ):
            self.assertNotIn(item, comando)

        self.assertIn(
            '["IBGE:GEOCODIGO"="2507507"]',
            self.mod.CONSULTA,
        )

    def test_timeout_nao_publica_fonte(self):
        codigo, relatorio, saida, _ = self.executar(
            b"",
            http=0,
            curl=28,
            versao="0",
        )

        self.assertEqual(codigo, 1)
        self.assertFalse(
            relatorio["consulta_municipal_validada"]
        )
        self.assertFalse(
            (saida / "fonte.json").exists()
        )
        self.assertFalse(
            (saida / "manifesto.json").exists()
        )

    def test_http2_nao_e_confirmacao_do_perfil(self):
        codigo, _, saida, _ = self.executar(
            bruto(fonte()),
            versao="2",
        )

        self.assertEqual(codigo, 1)
        self.assertFalse(
            (saida / "fonte.json").exists()
        )

    def test_ipv6_solicitado_precisa_ser_confirmado(self):
        codigo, _, saida, _ = self.executar(
            bruto(fonte()),
            ip="192.0.2.1",
        )

        self.assertEqual(codigo, 1)
        self.assertFalse(
            (saida / "fonte.json").exists()
        )

    def test_html_e_nan_sao_recusados(self):
        entradas = (
            b"<html>erro</html>",
            b'{"elements":[],"n":NaN}',
        )

        for valor in entradas:
            with self.subTest(valor=valor):
                with self.assertRaises(
                    self.mod.ErroCaptura
                ):
                    self.mod.validar_fonte(valor)

    def test_limites_de_bytes_e_elementos(self):
        entradas = (
            b"",
            b"x" * (self.mod.MAX_BYTES + 1),
        )

        for valor in entradas:
            with self.assertRaises(
                self.mod.ErroCaptura
            ):
                self.mod.validar_fonte(valor)

        dados = fonte()
        dados["elements"] *= 2501

        with self.assertRaises(
            self.mod.ErroCaptura
        ):
            self.mod.validar_fonte(bruto(dados))

    def test_municipio_errado_e_area_ausente(self):
        for tipo in (
            "errado",
            "ausente",
            "duplicada",
        ):
            dados = fonte()

            if tipo == "errado":
                dados["elements"][0]["tags"][
                    "IBGE:GEOCODIGO"
                ] = "outro"
            elif tipo == "ausente":
                dados["elements"].pop(0)
            else:
                dados["elements"].append(
                    dados["elements"][0]
                )

            with self.assertRaises(
                self.mod.ErroCaptura
            ):
                self.mod.validar_fonte(bruto(dados))

    def test_geometria_fora_do_recorte_e_booleanos(self):
        for lat in (0, -8, True, None):
            dados = fonte()
            dados["elements"][1]["lat"] = lat

            with self.assertRaises(
                self.mod.ErroCaptura
            ):
                self.mod.validar_fonte(bruto(dados))

    def test_identificador_booleano_e_duplicado(self):
        for duplicar in (False, True):
            dados = fonte()

            if duplicar:
                dados["elements"].append(
                    dados["elements"][1]
                )
            else:
                dados["elements"][1]["id"] = True

            with self.assertRaises(
                self.mod.ErroCaptura
            ):
                self.mod.validar_fonte(bruto(dados))

    def test_way_com_centro_valido(self):
        dados = fonte()

        dados["elements"][1] = {
            "type": "way",
            "id": 321,
            "center": {
                "lat": -7.1,
                "lon": -34.9,
            },
            "tags": {
                "amenity": "charging_station",
            },
        }

        resultado = self.mod.validar_fonte(
            bruto(dados)
        )

        self.assertEqual(
            resultado["elementos_locais"],
            1,
        )

    def test_fonte_antiga_futura_sem_fuso_ou_sem_data(self):
        agora = datetime.now(timezone.utc)

        datas = (
            (
                agora - timedelta(days=31)
            ).isoformat(),
            (
                agora + timedelta(minutes=6)
            ).isoformat(),
            agora.replace(
                tzinfo=None
            ).isoformat(),
            None,
        )

        for valor in datas:
            dados = fonte()
            dados["osm3s"][
                "timestamp_osm_base"
            ] = valor

            with self.assertRaises(
                self.mod.ErroCaptura
            ):
                self.mod.validar_fonte(
                    bruto(dados),
                    agora=agora,
                )

    def test_remark_impede_arquivamento(self):
        dados = fonte()
        dados["remark"] = "consulta incompleta"

        codigo, relatorio, saida, _ = self.executar(
            bruto(dados)
        )

        self.assertEqual(codigo, 1)
        self.assertFalse(
            relatorio["consulta_municipal_validada"]
        )
        self.assertFalse(
            (saida / "fonte.json").exists()
        )

    def test_saida_existente_preserva_conteudo(self):
        marcador = self.pasta / "manter.txt"
        marcador.write_text(
            "original",
            encoding="utf-8",
        )

        with patch(
            "sys.stdout",
            new_callable=io.StringIO,
        ):
            codigo = self.mod.main(
                ["--saida", str(self.pasta)],
                executar=lambda *args, **kwargs: self.fail(
                    "Nao deve acessar rede"
                ),
            )

        self.assertEqual(codigo, 2)
        self.assertEqual(
            marcador.read_text(encoding="utf-8"),
            "original",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2) 