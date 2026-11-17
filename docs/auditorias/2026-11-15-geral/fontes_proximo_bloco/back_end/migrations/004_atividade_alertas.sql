CREATE TABLE favoritos_postos (
 usuario_id INT NOT NULL, posto_id INT NOT NULL, criado_em DATETIME NOT NULL,
 PRIMARY KEY (usuario_id,posto_id),
 CONSTRAINT fk_fp_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
 CONSTRAINT fk_fp_posto FOREIGN KEY (posto_id) REFERENCES postos(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE favoritos_combustiveis (
 usuario_id INT NOT NULL,
 combustivel_codigo VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 criado_em DATETIME NOT NULL,
 PRIMARY KEY (usuario_id,combustivel_codigo),
 CONSTRAINT fk_fc_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
 CONSTRAINT fk_fc_combustivel FOREIGN KEY (combustivel_codigo) REFERENCES combustiveis(codigo)
) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE preferencias_alertas (
 usuario_id INT NOT NULL, ativo TINYINT NOT NULL DEFAULT 0,
 somente_quedas TINYINT NOT NULL DEFAULT 1,
 intervalo_minutos INT NOT NULL DEFAULT 30,
 PRIMARY KEY (usuario_id),
 CONSTRAINT fk_pa_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE historico_karma (
 id BIGINT NOT NULL AUTO_INCREMENT, usuario_id INT NOT NULL,
 origem VARCHAR(100) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 motivo VARCHAR(100) NOT NULL, pontos INT NOT NULL, saldo_apos INT NOT NULL,
 registo_id INT NULL, criado_em DATETIME NOT NULL,
 PRIMARY KEY (id), UNIQUE KEY uq_karma_origem (usuario_id,origem),
 CONSTRAINT fk_hk_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
 CONSTRAINT fk_hk_registo FOREIGN KEY (registo_id) REFERENCES registos_preco(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO historico_karma (usuario_id,origem,motivo,pontos,saldo_apos,criado_em)
 SELECT id,'saldo-inicial','Saldo anterior ao histórico detalhado',COALESCE(karma,0),COALESCE(karma,0),UTC_TIMESTAMP()
 FROM usuarios;

CREATE TABLE eventos_preco (
 registo_id INT NOT NULL, preco_anterior DECIMAL(5,2) NULL,
 criado_em DATETIME NOT NULL, processado_em DATETIME NULL,
 PRIMARY KEY (registo_id),
 CONSTRAINT fk_ep_registo FOREIGN KEY (registo_id) REFERENCES registos_preco(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE notificacoes (
 id BIGINT NOT NULL AUTO_INCREMENT, usuario_id INT NOT NULL,
 registo_id INT NOT NULL, posto_id INT NOT NULL,
 combustivel_codigo VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 preco_anterior DECIMAL(5,2) NULL, preco_novo DECIMAL(5,2) NOT NULL,
 criado_em DATETIME NOT NULL, lida_em DATETIME NULL,
 PRIMARY KEY (id), UNIQUE KEY uq_notificacao_registo (usuario_id,registo_id),
 KEY idx_notificacao_conta_data (usuario_id,id),
 CONSTRAINT fk_n_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
 CONSTRAINT fk_n_registo FOREIGN KEY (registo_id) REFERENCES registos_preco(id) ON DELETE CASCADE,
 CONSTRAINT fk_n_posto FOREIGN KEY (posto_id) REFERENCES postos(id) ON DELETE CASCADE,
 CONSTRAINT fk_n_combustivel FOREIGN KEY (combustivel_codigo) REFERENCES combustiveis(codigo)
) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
