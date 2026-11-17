# Fontes para o próximo bloco

Destinatário: Codex web. Nenhuma correção foi aplicada na auditoria.

## Bloco recomendado

Consistência do cadastro: disponibilidade efetiva no servidor (A01) e resultado HTTP 408 incerto (A02). Manter oferta desconhecida, unidade, geofence, sessão, cooldown, Karma e evento transacionais. Não fundir com redesign, push, migração TiDB ou alteração da política de exclusão de votos. A04 precisa primeiro de decisão sobre persistência/compensação.

## Critérios de aceite

- Oferta negativa explícita é revalidada dentro da transação; desconhecido segue permitido sem confirmar oferta. Mesma regra nas duas URLs de preço.
- Produto alterado entre leitura do catálogo e cadastro recebe resposta coerente, sem preço/Karma/evento parciais.
- HTTP408 e perda da resposta de commit não liberam reenvio cego; 4xx de validação continuam corrigíveis.
- Não declarar idempotência por request enquanto não existir contrato para isso.
- Testes unitários + fixture MySQL/TLS descartável, após nova conferência de isolamento; não usar litro_de_ouro_dev para escrita de teste.

## Trechos centrais

- precos.py:114–385: validação, locks usuário/posto, ausência da consulta de disponibilidade e transação de preço/Karma/evento.
- ofertas.py: contrato de triestado e tratamento da negativa; catalogo_postos.py:86+ precedência manual/OSM e referência.
- cadastroPreco.ts:57 (produtos permitidos),114 (payload/GPS),188 e250 (envio/classificação de erro).
- AdicionarPreco/index.tsx:118–119 (incerto/bloqueado),164+ (envio),509+ (OCR/comprovante).
- integracao_participacao.py:setUpClass exige banco descartável exato e vazio; atualmente aplica schema/migrações na fixture. Não executada nesta auditoria.

## Arquivos completos atuais

Cópias byte a byte dos fontes, com caminhos preservados e SHA-256 em FONTES_PROXIMO_BLOCO.json. Não são patches nem versões sugeridas. Os testes contêm apenas fixtures sintéticas; não incluem credenciais reais ou env. Envie estes arquivos individualmente ao Codex web junto dos três documentos.

- [front_end/src/services/cadastroPreco.ts](C:/litro_de_ouro/docs/auditorias/2026-11-15-geral/fontes_proximo_bloco/front_end/src/services/cadastroPreco.ts)
- [front_end/src/screens/AdicionarPreco/index.tsx](C:/litro_de_ouro/docs/auditorias/2026-11-15-geral/fontes_proximo_bloco/front_end/src/screens/AdicionarPreco/index.tsx)
- [front_end/tests/cadastro-preco.test.cjs](C:/litro_de_ouro/docs/auditorias/2026-11-15-geral/fontes_proximo_bloco/front_end/tests/cadastro-preco.test.cjs)
- [front_end/src/services/catalogoPostos.ts](C:/litro_de_ouro/docs/auditorias/2026-11-15-geral/fontes_proximo_bloco/front_end/src/services/catalogoPostos.ts)
- [front_end/src/utils/localizacao.ts](C:/litro_de_ouro/docs/auditorias/2026-11-15-geral/fontes_proximo_bloco/front_end/src/utils/localizacao.ts)
- [front_end/src/services/API.ts](C:/litro_de_ouro/docs/auditorias/2026-11-15-geral/fontes_proximo_bloco/front_end/src/services/API.ts)
- [back_end/app/rotas/precos.py](C:/litro_de_ouro/docs/auditorias/2026-11-15-geral/fontes_proximo_bloco/back_end/app/rotas/precos.py)
- [back_end/app/rotas/ofertas.py](C:/litro_de_ouro/docs/auditorias/2026-11-15-geral/fontes_proximo_bloco/back_end/app/rotas/ofertas.py)
- [back_end/services/catalogo_postos.py](C:/litro_de_ouro/docs/auditorias/2026-11-15-geral/fontes_proximo_bloco/back_end/services/catalogo_postos.py)
- [back_end/services/atividade_alertas.py](C:/litro_de_ouro/docs/auditorias/2026-11-15-geral/fontes_proximo_bloco/back_end/services/atividade_alertas.py)
- [back_end/app/utils/geofence.py](C:/litro_de_ouro/docs/auditorias/2026-11-15-geral/fontes_proximo_bloco/back_end/app/utils/geofence.py)
- [back_end/app/utils/decorator.py](C:/litro_de_ouro/docs/auditorias/2026-11-15-geral/fontes_proximo_bloco/back_end/app/utils/decorator.py)
- [back_end/app/db.py](C:/litro_de_ouro/docs/auditorias/2026-11-15-geral/fontes_proximo_bloco/back_end/app/db.py)
- [back_end/services/database.py](C:/litro_de_ouro/docs/auditorias/2026-11-15-geral/fontes_proximo_bloco/back_end/services/database.py)
- [back_end/tests/integracao_participacao.py](C:/litro_de_ouro/docs/auditorias/2026-11-15-geral/fontes_proximo_bloco/back_end/tests/integracao_participacao.py)
- [back_end/docker/schema_base.sql](C:/litro_de_ouro/docs/auditorias/2026-11-15-geral/fontes_proximo_bloco/back_end/docker/schema_base.sql)
- [back_end/migrations/001_catalogo_disponibilidade.sql](C:/litro_de_ouro/docs/auditorias/2026-11-15-geral/fontes_proximo_bloco/back_end/migrations/001_catalogo_disponibilidade.sql)
- [back_end/migrations/004_atividade_alertas.sql](C:/litro_de_ouro/docs/auditorias/2026-11-15-geral/fontes_proximo_bloco/back_end/migrations/004_atividade_alertas.sql)

As demais dependências já existentes devem ser preservadas. O conjunto inclui o contexto de conexão/autorizações e o schema para evitar implementar a correção sobre contratos antigos. Não inclui .env, certificados, dumps ou imagens. Se o próximo bloco mudar para mapa/visual, use o grafo IMPORTS_FRONTEND.json e peça os fontes ativos específicos; não usar Inicio/Mapa legados como base.
