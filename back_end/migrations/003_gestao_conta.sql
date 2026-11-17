-- Executar pelo migrador; não repetir DDL parcial automaticamente.
ALTER TABLE usuarios
    ADD COLUMN versao_token INT NOT NULL DEFAULT 0,
    ADD COLUMN tentativas_codigo INT NOT NULL DEFAULT 0,
    ADD COLUMN codigo_emitido_em DATETIME NULL,
    ADD COLUMN falhas_login INT NOT NULL DEFAULT 0,
    ADD COLUMN login_bloqueado_ate DATETIME NULL;

CREATE TABLE trocas_email (
    usuario_id INT NOT NULL,
    novo_email VARCHAR(100) NOT NULL,
    codigo_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    expira_em DATETIME NOT NULL,
    solicitado_em DATETIME NOT NULL,
    tentativas INT NOT NULL DEFAULT 0,
    PRIMARY KEY (usuario_id),
    CONSTRAINT fk_troca_email_usuario FOREIGN KEY (usuario_id)
        REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;