-- Conteudo versionado: executar pelo scripts/migrar_banco.py.
-- DDL possui commits implicitos; falha parcial exige revisao, nao repeticao cega.
CREATE TABLE `combustiveis` (
    `codigo` VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    `nome` VARCHAR(50) NOT NULL,
    `unidade` VARCHAR(8) NOT NULL,
    PRIMARY KEY (`codigo`)
) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO `combustiveis` (`codigo`, `nome`, `unidade`) VALUES
    ('gasolina_comum', 'Gasolina Comum', 'L'),
    ('gasolina_aditivada', 'Gasolina Aditivada', 'L'),
    ('etanol', 'Etanol', 'L'),
    ('diesel', 'Diesel', 'L'),
    ('gnv', 'GNV', 'm³'),
    ('recarga_eletrica', 'Recarga Elétrica', 'kWh');

CREATE TABLE `postos_combustiveis` (
    `posto_id` INT NOT NULL,
    `combustivel_codigo` VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    `disponivel_osm` TINYINT NULL DEFAULT NULL,
    `osm_verificado_em` DATETIME NULL DEFAULT NULL,
    `disponivel_manual` TINYINT NULL DEFAULT NULL,
    `manual_atualizado_em` DATETIME NULL DEFAULT NULL,
    `manual_atualizado_por` INT NULL DEFAULT NULL,
    PRIMARY KEY (`posto_id`, `combustivel_codigo`),
    KEY `idx_pc_combustivel` (`combustivel_codigo`),
    KEY `idx_pc_responsavel` (`manual_atualizado_por`),
    CONSTRAINT `ck_pc_disponivel_osm`
        CHECK (`disponivel_osm` IS NULL OR `disponivel_osm` IN (0, 1)),
    CONSTRAINT `ck_pc_disponivel_manual`
        CHECK (`disponivel_manual` IS NULL OR `disponivel_manual` IN (0, 1)),
    CONSTRAINT `fk_pc_posto` FOREIGN KEY (`posto_id`) REFERENCES `postos` (`id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `fk_pc_combustivel` FOREIGN KEY (`combustivel_codigo`)
        REFERENCES `combustiveis` (`codigo`) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `fk_pc_responsavel` FOREIGN KEY (`manual_atualizado_por`)
        REFERENCES `usuarios` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;