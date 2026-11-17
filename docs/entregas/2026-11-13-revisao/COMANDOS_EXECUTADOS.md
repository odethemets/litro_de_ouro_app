# Comandos e destinos da revisão

Executados em 13/11/2026. Diretório padrão `C:\litro_de_ouro`, PowerShell. Segredos não foram impressos. Os parâmetros `--env-file` apontam ao arquivo privado, que não integra este pacote.

## Referência e inspeção

- Leitura dos dois anexos, comparação SHA256 (iguais), `git status --short`, `git branch --show-current`, `git rev-parse HEAD`, instruções `front_end/AGENTS.md` e fontes pertinentes.
- Cópia por lista explícita de fontes/configurações públicas para `base/`, hashes/linhas em `BASE_SHA256.json`, antes das edições pertinentes.
- Busca com `rg` dos imports Google e leitura de requisitos/Dockerfile.
- Docker: `importlib.util.find_spec('google.genai')` retornou falso antes da alteração. Consulta pública ao PyPI confirmou metadados da versão 2.34.0. Não usou chave nem fez inferência.

## SDK e runtime

```powershell
docker build --no-cache --progress plain -t litro-de-ouro-backend-local:revisao-sdk-20261113 -f back_end/Dockerfile back_end
docker run --rm --network none litro-de-ouro-backend-local:revisao-sdk-20261113 python -B scripts/verificar_sdk_ia.py
docker run --rm --network none litro-de-ouro-backend-local:revisao-sdk-20261113 python -m pip check
docker run --rm --network none litro-de-ouro-backend-local:revisao-sdk-20261113 python -m pip freeze
docker image inspect litro-de-ouro-backend-local:dev --format '{{.Id}}'
docker image tag litro-de-ouro-backend-local:dev litro-de-ouro-backend-local:antes-sdk-20261113
docker image tag litro-de-ouro-backend-local:revisao-sdk-20261113 litro-de-ouro-backend-local:dev
docker compose -f compose.yaml -f docker/compose.testes-precos.yaml --env-file docker/local/.env up -d --no-deps backend --wait --wait-timeout 90
docker compose -f compose.yaml --env-file docker/local/.env exec -T backend python -B scripts/verificar_sdk_ia.py
docker compose -f compose.yaml --env-file docker/local/.env exec -T backend python -B scripts/testar_offline.py
docker compose -f compose.yaml --env-file docker/local/.env exec -T backend python docker/verificar_local.py
```

A primeira imagem foi construída limpa; os comandos `docker run --network none` comprovam que a verificação não depende de rede. O pip baixou os pacotes somente na etapa de build. `:dev` anterior foi preservada com outra tag antes da substituição. A recriação abrangeu somente backend, sem db/inicializador ou volumes. Os testes offline foram repetidos após aplicar o SDK real. Saídas individuais nos logs deste diretório.

## Frontend

Diretório `C:\litro_de_ouro\front_end`:

```powershell
node node_modules/typescript/bin/tsc --noEmit
npm run lint
node --test tests/*.test.cjs
```

Todos retornaram zero. Os contratos/UI são testados com dados simulados; não equivalem a clique no aplicativo. Nenhum fonte frontend foi alterado nesta rodada.

## MySQL de integração

Por `docker compose exec -T db`, o cliente MySQL local recebeu a senha root pela variável já existente **dentro do container**, sem expor seu valor. Foram usados os seguintes SQLs exclusivamente no banco nomeado de testes:

```sql
CREATE DATABASE ldo_validacao_20261113_01
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL ON ldo_validacao_20261113_01.* TO litro_local;
```

Execução do teste:

```powershell
docker compose -f compose.yaml --env-file docker/local/.env exec -T -e DB_NAME=ldo_validacao_20261113_01 -e GEOFENCE_RAIO_M=500 backend python -B tests/integracao_participacao.py
```

O primeiro ciclo passou antes da substituição da imagem. Para validar também na imagem aplicada, **somente esse banco descartável** foi removido e recriado vazio, com o mesmo charset/collation, e o comando de integração foi repetido. O log final corresponde ao backend com SDK novo. O script recusa destino diferente, URL de banco alternativa ou schema não vazio. Contas, senhas e coordenadas dentro dele são dados sintéticos.

Ao final, pelo mesmo cliente administrativo local:

```sql
DROP DATABASE ldo_validacao_20261113_01;
REVOKE ALL PRIVILEGES ON ldo_validacao_20261113_01.* FROM litro_local;
```

Resultado: 14 cenários aprovados e limpeza concluída. Não foram apagados ou criados usuários/preços no banco do responsável por essa integração. O verificador local faz leituras e login da conta fictícia existente.

## Material de revisão

`git diff --no-index --binary` compara os arquivos modificados com `base/`. O novo verificador é comparado a `/dev/null`. Caminhos do cabeçalho são normalizados para `a/<arquivo>` e `b/<arquivo>`, sem mudar conteúdo dos hunks. `git apply --reverse --check` verifica que o patch corresponde aos códigos atuais; não aplica a reversão.

O diff de código é individual, não ZIP. O requisito tinha UTF-16LE e por isso o patch tem um trecho binário; `base/back_end/requirements.txt` conserva os bytes originais para revisão e reversão. Os fontes de módulos já integrados estão em `base/` e seus hashes permitem conferir a versão; nenhuma base retrospectiva foi presumida.

## Não executado / próximos comandos sugeridos

Controle do Firefox foi interrompido pela ferramenta antes de interação com a página; não houve captura de UI. Não foram executados testes em celular, provedores reais, venv Windows, deploy, cron ou push. O roteiro manual está em `OFERTAS_VOTOS_AVISOS.md`; não foi convertido em evidência executada.

Não há comando de aplicação pendente para o responsável: os códigos descritos já estão no projeto e a imagem local do SDK foi aplicada. Publicação, agendamento e novas regras de moderação continuam fora desta entrega.
