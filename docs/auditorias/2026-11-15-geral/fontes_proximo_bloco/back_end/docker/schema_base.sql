-- Esquema exclusivo do MySQL local ficticio, anterior as migracoes 001/002.
CREATE TABLE postos (
 id INT NOT NULL AUTO_INCREMENT,
 mapbox_id VARCHAR(100) DEFAULT NULL,
 nome VARCHAR(150) NOT NULL,
 endereco VARCHAR(255) DEFAULT '', bairro VARCHAR(100) DEFAULT '',
 cidade VARCHAR(100) DEFAULT 'João Pessoa', uf VARCHAR(2) DEFAULT 'PB',
 latitude DECIMAL(10,8) NOT NULL, longitude DECIMAL(11,8) NOT NULL,
 horario_funcionamento VARCHAR(50) DEFAULT '24 Horas',
 tipo_posto ENUM('Convencional','Eletroposto') DEFAULT 'Convencional',
 PRIMARY KEY (id), UNIQUE KEY mapbox_id (mapbox_id),
 UNIQUE KEY uq_postos_mapbox_id (mapbox_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE usuarios (
 id INT NOT NULL AUTO_INCREMENT, nome VARCHAR(100) NOT NULL,
 email VARCHAR(100) NOT NULL, senha VARCHAR(255) DEFAULT NULL,
 criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
 plano VARCHAR(50) DEFAULT 'gratis', karma INT DEFAULT 0,
 email_verificado TINYINT(1) DEFAULT 0,
 token_verificacao VARCHAR(64) DEFAULT NULL,
 token_recuperacao VARCHAR(64) DEFAULT NULL, token_expiracao DATETIME DEFAULT NULL,
 PRIMARY KEY (id), UNIQUE KEY email (email), UNIQUE KEY idx_email_unico (email),
 KEY idx_email_verificado (email_verificado),
 KEY idx_token_verificacao (token_verificacao),
 KEY idx_token_recuperacao (token_recuperacao)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE registos_preco (
 id INT NOT NULL AUTO_INCREMENT, posto_id INT NOT NULL, usuario_id INT NOT NULL,
 tipo_combustivel VARCHAR(50) NOT NULL, preco DECIMAL(5,2) NOT NULL,
 confianca_score INT DEFAULT 1, data_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
 foto_url VARCHAR(500) DEFAULT NULL, PRIMARY KEY (id),
 KEY usuario_id (usuario_id),
 KEY idx_registos_posto_tipo_data (posto_id,tipo_combustivel,data_registro),
 CONSTRAINT registos_preco_ibfk_1 FOREIGN KEY (posto_id) REFERENCES postos(id) ON DELETE CASCADE,
 CONSTRAINT registos_preco_ibfk_2 FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE votos_registos (
 id INT NOT NULL AUTO_INCREMENT, registo_id INT NOT NULL, usuario_id INT NOT NULL,
 tipo_voto ENUM('positivo','negativo') NOT NULL,
 created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY (id), UNIQUE KEY uq_usuario_registo (usuario_id,registo_id),
 UNIQUE KEY uq_voto_unico (registo_id,usuario_id),
 CONSTRAINT votos_registos_ibfk_1 FOREIGN KEY (registo_id) REFERENCES registos_preco(id) ON DELETE CASCADE,
 CONSTRAINT votos_registos_ibfk_2 FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;