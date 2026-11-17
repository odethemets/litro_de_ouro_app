# Evidências atuais — auditoria de 15/11/2026

Destinatário: Codex web. Todos os comandos abaixo foram executados nesta auditoria, salvo a seção explícita de pendências. Raiz Windows `C:/litro_de_ouro`; frontend `C:/litro_de_ouro/front_end`; backend `/app` no container já em execução. Sem instalação de pacotes, restart, build de imagem, migração, cadastro ou processamento da fila real.

## Segurança e interpretação

Antes de executar, foram lidos o runner e as fronteiras dos testes: testes backend `test_*.py` usam bancos fake/Mock/patch, arquivos temporários e provedores simulados. `test_ia.py` substitui sys.modules; o runner lança cada arquivo em processo separado. A fixture `integracao_participacao.py` e o script `transferencia_tidb.py` não casam com esse glob e não foram executados. Testes frontend usam VM/transpile, mocks de hooks/picker/API e adapters Axios; o teste de Blob passa arquivo local e não executa fetch remoto.

Testes podem criar temporários descartáveis; evidências persistentes foram direcionadas à pasta da auditoria. ESLint foi chamado diretamente sem cache e TypeScript sem incremental; a exportação foi direcionada à subpasta export-web, sem sobrescrever dist. Nenhum patch de implementação foi gerado. Logs foram revisados: mensagens de teste usam dados sintéticos e nomes de env, sem valores secretos. Não exportados registros pessoais.

Não somar execuções/reproduções extras aos totais das suítes. Zero testes descobertos não foi contado como aprovação.

## Frontend

| Comando (diretório front_end) | Resultado | Duração disponível | Tipo/limite | Arquivo |
| --- | --- | --- | --- | --- |
| `node node_modules/typescript/bin/tsc --noEmit --incremental false` | exit0 | >10s na chamada inicial; total de parede não instrumentado | Estático; não renderiza | TYPESCRIPT.log |
| `node node_modules/eslint/bin/eslint.js . --no-cache` | exit0 | >10s inicial; total não instrumentado | Mesma configuração ESLint do projeto, sem wrapper expo/cache | LINT.log |
| `node --test tests/*.test.cjs` | exit0,113/113 | 3,225s informado pelo runner | Contratos/serviços/hooks/API simulados; Blob/FormData/Axios reais em casos específicos | TESTES_FRONTEND.log |
| `CI=1 EXPO_NO_TELEMETRY=1 EXPO_NO_CACHE=1 node node_modules/expo/bin/cli export --platform web --output-dir ../docs/auditorias/2026-11-15-geral/export-web` | exit0 | >10s inicial; total não instrumentado | Compilação web, não teste do navegador/aparelho | EXPORT_WEB.log |

As envs de CI/telemetria/cache foram definidas apenas no processo PowerShell do comando. Não houve edição de arquivos env. A compilação carregou a configuração local existente. O teste isolado de configuração em produção encontrou recusa do esquema HTTP (CONFIG_BUILD.json); o sucesso do export não contradiz essa recusa em runtime.

Suítes frontend encontradas: fundacao, conta, catalogo, cadastro-preco, participacao, assistente-sessao, voz-revisao, leitura-totem e leitor-totem-sessao. São113 casos totais; nomes e resultados estão no log completo. Não existe `assistente.test.cjs` nesta árvore; não foi inventado ou contado. Não há teste visual dos clusters/tema/mapa nem E2E completo de autenticação.

## Backend isolado

Comando na raiz:

```powershell
docker compose -f compose.yaml -f docker/compose.testes-precos.yaml --env-file docker/local/.env exec -T backend python -B scripts/testar_offline.py
```

Resultado exit0. O runner glob inclui todos os14 arquivos abaixo, em processos separados; passa GEOFENCE_RAIO_M=500 e PYTHONPATH somente ao ambiente dos testes. Duração total de parede não foi instrumentada (chamada inicial excedeu10s); durações internas abaixo são as informadas por unittest e não incluem todos os imports.

| Arquivo | Casos unittest | Duração interna | Fronteiras |
| --- | ---: | ---: | --- |
| test_catalogo_postos.py |25|2,570s|Consultas simuladas; contratos reais|
| test_completar_catalogo_osm.py |33|0,037s|Banco/source fake, backup temporário|
| test_executar_alertas_cli.py |9|0,012s|CLI/dependências/sinais simulados|
| test_executar_job_osm.py |13|0,029s|Subprocesso/ambiente simulados; temporários|
| test_executor_alertas.py |17|0,021s|Conexão/processador/tempo simulados|
| test_infra_banco.py |23|0,214s|Driver/banco simulados, TLS/config/planos|
| test_infra_web.py |17|0,437s|Flask/CORS reais; banco fake|
| test_leitura_totem.py |8|0,059s|Pillow real/imagens sintéticas; caso de limite de pixels com mock|
| test_osm_batch.py |20|0,032s|HTTP/banco simulados, arquivos temporários|
| test_revisar_osm.py |11|0,029s|Conector/source simulados; fonte/manifesto temporários|
| test_transferencia_tidb.py |27|0,172s|Conexões fake; não acessa TiDB|
| test_verificar_assistente.py |8|0,001s|Módulos sintéticos; sem Gemini|
| test_geofence.py |não se aplica|não informado|Script de assertivas de geofence|
| test_ia.py |não se aplica|não informado|Script de assertivas; Flask/Pillow reais, JWT/banco/Gemini/Dropbox simulados|

Total: **211 casos unittest +2 scripts**. Log: TESTES_BACKEND.log. Não houve discovery geral de módulos misturados. Esses testes não equivalem aos cenários MySQL de concorrência/rollback da fixture de participação. Não se afirma cobertura completa backend de auth/conta/preços/votos com base apenas nos contratos frontend.

## Runtime existente e banco somente leitura

1. `docker ps --format ...` e `docker inspect ...` selecionando `.Image`, `.Config.Labels`, `.Mounts`: containers saudáveis, imagem/mounts/Compose descritos no relatório. Nenhum inspect integral de Env. `docker top ... -eo pid,comm` mostrou docker-init e dois gunicorn; sem executor de fila nesse container. A tentativa inicial com apenas comm falhou por exigência de campo PID e foi corrigida; isso não foi interpretado como ausência de processos.
2. `inspecao_runtime.py` foi enviado por stdin ao `python -B -` do backend. Importa a fábrica em novo processo, identifica rotas/pacotes/hashes e, somente após validar host db/banco litro_de_ouro_dev, abre `read_only=True,time_zone='+00:00'` para SELECT DATABASE/VERSION, contagens de catálogo, fila, registro de migrações e SHOW TABLES. Fecha com rollback/close. Resultado em RUNTIME.json, comparação dos sete hashes em COMPARACAO_RUNTIME.json. Não mede conteúdo da memória dos workers ativos.
3. Variáveis de e-mail/transferência foram verificadas por booleano de presença (`CONFIG_EXTRA.json`), sem valores. A configuração de outros provedores consta de RUNTIME.json. Não foram calculados hashes de segredos.
4. GET `http://127.0.0.1:5001/health/live` e `/health/ready`: ambos200, corpos status ok/pronto, registrados em SAUDE.json. Primeiro acesso foi recusado pelo sandbox de rede; repetido com acesso autorizado ao localhost. Não foi login nem consulta a provedor. `ready` pode usar cache5s e confere ledger de migrações, não todo o schema físico.
5. Diagnóstico real, sem flags de escrita:

```powershell
docker compose -f compose.yaml -f docker/compose.testes-precos.yaml --env-file docker/local/.env exec -T backend python -B scripts/executar_alertas.py --banco litro_de_ouro_dev
```

Resultado exit0 em cerca1s: destino conferido, assinatura compatível,1 pendente, mais antigo2026-11-14T01:08:45Z. Log DIAGNOSTICO_FILA.json às2026-11-15T06:19:35Z (03:19:35 Fortaleza). Não foi rodada nem ciclo.

Os arquivos completos dos comandos de inspeção/reprodução estão na pasta, sem credenciais. A consulta de fonte municipal foi somente hash de arquivo salvo: FONTE_OSM.json, hash igual ao informado. Não foi repetida prévia remota ou comparação dos88 elementos.

## Reproduções extras, fora dos totais

| Reprodução | Resultado | Segurança/limite |
| --- | --- | --- |
| `node docs/auditorias/2026-11-15-geral/reproduzir_408.cjs` | HTTP408 simulado resulta tipo rejeitado | Serviço real via TypeScript/VM; sem HTTP real. REPRO_408.json. Não demonstra duplicação efetiva de preço. |
| `reproduzir_oferta.py` por stdin ao Python do container, GEOFENCE_RAIO_M=500 |201,commit/Karma simulados1; nenhuma consulta de disponibilidade | Flask e função reais, banco/Karma fake; chama lógica diretamente, não homologa JWT/banco. REPRO_OFERTA.json. |
| Import isolado configuracao.ts com __DEV__=false e esquema da env local |Erro de HTTPS esperado|Sem rede, sem imprimir URL/credenciais; CONFIG_BUILD.json. É pendência de build/runtime, não pedido para relaxar a regra.|

Os dois primeiros cenários não foram adicionados às suítes de produto: servem como evidência para futura correção. Nada foi corrigido nesta auditoria.

## Não executado

- MySQL descartável/fixture participação: exigiria criar schema/aplicar migrações e dados. Escopo atual priorizou leitura e mocks; testes de14 cenários anteriores não são resultados atuais.
- Rodada/ciclo de alertas; ativação de workflow/cron; importação/enriquecimento OSM; migração/transferência/backup/restore; deploy/commit/push.
- Gemini/Dropbox/Mapbox/e-mail reais, imagem pessoal, alteração de conta/preço/voto/preferência.
- Browser/aparelho físico. Não houve tentativa visual nem captura; export não conta como UI aprovada. Roteiro por tamanho/fonte/plataforma no relatório.
- Painéis de hospedagem/GitHub/TiDB e validação de secrets externos. Ausência de variáveis no container não prova ausência no host ou serviço online.

## Preservação

FONTES_INICIO.json e VERIFICACAO_FINAL.json identificam o escopo de hashes conferido. Arquivos de testes frontend e schema base adicionados ao pacote final possuem hashes, mas o manifesto inicial foi concentrado nos fontes/runtime e não continha todos esses testes; não se apresenta comparação inicial inexistente. GIT_STATUS.log preserva o estado inicial. Fontes completos do próximo bloco são cópias, sem edições. Artefatos export-web são build local para evidência, não publicação.
