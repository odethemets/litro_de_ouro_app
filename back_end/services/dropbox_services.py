import os
import dropbox
import uuid

def upload_foto_totem(file_stream, filename):
    token = os.getenv("DROPBOX_TOKEN")
    if not token:
        print("Aviso: DROPBOX_TOKEN não configurado no .env")
        return None

    try:
        # Liga ao Dropbox
        dbx = dropbox.Dropbox(token)
        
        # Gera um nome único para a imagem não sobrescrever outras
        extensao = filename.split('.')[-1]
        nome_unico = f"totem_{uuid.uuid4().hex}.{extensao}"
        caminho_dropbox = f"/litro_de_ouro_totens/{nome_unico}"

        # Faz o Upload
        dbx.files_upload(file_stream.read(), caminho_dropbox)
        
        # Cria o link de visualização da prova
        link = dbx.sharing_create_shared_link(caminho_dropbox).url
        
        # Troca 'dl=0' por 'raw=1' para renderizar direto na web se precisarmos
        link_direto = link.replace("?dl=0", "?raw=1")
        
        return link_direto
    except Exception as e:
        print(f"Erro no Dropbox: {e}")
        return None