-- Referência municipal estimada.
-- Não é registro observado nem confirma disponibilidade.

CREATE TABLE referencias_medias_iniciais (
    posto_id INT NOT NULL,

    combustivel_codigo VARCHAR(32)
        CHARACTER SET ascii
        COLLATE ascii_bin
        NOT NULL,

    preco DECIMAL(5,2) NOT NULL,

    municipio_referencia VARCHAR(100) NOT NULL,

    uf_referencia CHAR(2)
        CHARACTER SET ascii
        COLLATE ascii_bin
        NOT NULL,

    periodo_inicio DATE NOT NULL,
    periodo_fim DATE NOT NULL,
    amostra INT UNSIGNED NOT NULL,

    fonte_sha256 CHAR(64)
        CHARACTER SET ascii
        COLLATE ascii_bin
        NOT NULL,

    snapshot_sha256 CHAR(64)
        CHARACTER SET ascii
        COLLATE ascii_bin
        NOT NULL,

    criado_em DATETIME NOT NULL,

    PRIMARY KEY (
        posto_id,
        combustivel_codigo
    ),

    KEY idx_rmi_combustivel (
        combustivel_codigo
    ),

    CONSTRAINT fk_rmi_posto
        FOREIGN KEY (posto_id)
        REFERENCES postos(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_rmi_produto
        FOREIGN KEY (combustivel_codigo)
        REFERENCES combustiveis(codigo)
)
ENGINE=InnoDB
DEFAULT CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;