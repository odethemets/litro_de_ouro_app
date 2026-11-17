-- Migração 002 compativel com MySQL e TiDB; executar pelo migrar_banco.py.
ALTER TABLE `postos`
    ADD COLUMN `marca` VARCHAR(120) NULL DEFAULT NULL,
    ADD COLUMN `marca_origem` ENUM('osm', 'manual') NULL DEFAULT NULL;

ALTER TABLE `postos`
    ADD KEY `idx_postos_marca` (`marca`);