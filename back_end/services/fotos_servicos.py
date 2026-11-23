"""Comprovantes privados no Dropbox, separados dos links públicos dos totens."""
import os
import re
import uuid

MAX_JPEG = 2 * 1024 * 1024
PASTA = "/litro_de_ouro_servicos"


class FotoServicoIndisponivel(RuntimeError):
    pass


def _caminho(nome):
    if not isinstance(nome, str) or not re.fullmatch(r"[0-9a-f]{32}\.jpg", nome):
        raise FotoServicoIndisponivel("Identificador de comprovante inválido.")
    return PASTA + "/" + nome


def _cliente():
    import dropbox

    token = os.getenv("DROPBOX_TOKEN", "").strip()
    if not token:
        raise FotoServicoIndisponivel("Armazenamento de comprovantes indisponível.")
    return dropbox.Dropbox(token, timeout=15)


def guardar(jpeg):
    if not isinstance(jpeg, bytes) or not 0 < len(jpeg) <= MAX_JPEG or not jpeg.startswith(b"\xff\xd8"):
        raise FotoServicoIndisponivel("Comprovante preparado inválido.")
    nome = uuid.uuid4().hex + ".jpg"
    try:
        with _cliente() as cliente:
            # Só ignora o conflito específico de pasta já existente.
            from dropbox.exceptions import ApiError
            try:
                cliente.files_create_folder_v2(PASTA, autorename=False)
            except ApiError as erro:
                conflito = erro.error
                if not (conflito.is_path() and conflito.get_path().is_conflict()
                        and conflito.get_path().get_conflict().is_folder()):
                    raise
            cliente.files_upload(jpeg, _caminho(nome), autorename=False)
    except Exception:
        # Não publica mensagens do SDK, caminhos, tokens ou links compartilhados.
        raise FotoServicoIndisponivel("Não foi possível guardar a foto para revisão.") from None
    return nome


def ler(nome):
    caminho = _caminho(nome)
    resposta = None
    try:
        with _cliente() as cliente:
            download = cliente.files_download(caminho)

            if download is None:
                raise FotoServicoIndisponivel(
                    "Não foi possível abrir o comprovante."
                )

            _, resposta = download # pyright: ignore[reportGeneralTypeIssues]
            bruto = resposta.content

        if not 0 < len(bruto) <= MAX_JPEG or not bruto.startswith(b"\xff\xd8"):
            raise ValueError

        return bruto
    except Exception:
        raise FotoServicoIndisponivel(
            "Não foi possível abrir o comprovante."
        ) from None
    finally:
        if resposta is not None:
            try:
                resposta.close()
            except Exception:
                pass


def remover(nome):
    """Limpeza compensatória; nunca usada quando o resultado do commit é incerto."""
    try:
        with _cliente() as cliente:
            cliente.files_delete_v2(_caminho(nome))
    except Exception:
        return False
    return True