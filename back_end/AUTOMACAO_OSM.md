# Automação OSM — Litro de Ouro

## Objetivo

Importar postos e eletropostos disponíveis na OSM dentro da área
administrativa de João Pessoa.

A listagem GET /postos continua consultando somente o MySQL.
A busca externa e a importação são administrativas.

Não há migrações de banco neste bloco.

## Arquivos

- services/osm_service.py
- scripts/importar_postos_osm.py
- requirements-osm.txt
- tests/test_osm_batch.py
- ../.github/workflows/osm_sync.yml

O grid_postos.py existente deve exportar classificar_lugar.
Não é necessário substituí-lo por causa deste pacote.

## Regras de gravação

- Prévia por padrão.
- Gravação exige --aplicar.
- Somente candidatos novos com tag OSM name válida são inseridos.
- Brand/operator isolados não autorizam inclusão.
- Postos sem nome ficam no relatório.
- Ambiguidades ficam no relatório.
- Postos existentes não são atualizados.
- Não há associação automática de IDs a cadastros manuais.
- Não há exclusão automática.
- Preços, votos, karma e históricos não são modificados.

O importador compara também os candidatos nomeados entre si.
Se dois objetos OSM estiverem próximos, ambos ficam para revisão,
independentemente da ordem de processamento.

## Delimitação municipal

A consulta utiliza:

- boundary=administrative
- admin_level=8
- IBGE:GEOCODIGO=2507507

A própria área deve estar presente na resposta.
Ausência, duplicidade ou código divergente impede a importação.

Não há fallback automático para caixa retangular.

Para ways e relations, a Overpass considera a geometria do objeto.
O mapa exibe seu center. Objetos que cruzam a divisa podem exigir
revisão; não há um teste adicional do centroide contra uma malha IBGE.

A cobertura e a atualização são as da OSM. Não há garantia de que
todos os estabelecimentos reais estejam mapeados ou funcionando.

## Primeiro teste local

Execute dentro de back_end, com o ambiente virtual ativado:

```powershell
python -m py_compile services/osm_service.py scripts/importar_postos_osm.py
```

Teste mínimo da Overpass, sem MySQL:

```powershell
python scripts/importar_postos_osm.py --teste-conexao --tentativas 1
```

Esperado:

- status: ok
- etapa: teste_conexao
- mysql_consultado: false

Teste com contingência:

```powershell
python scripts/importar_postos_osm.py --teste-conexao --tentativas 2
```

## Consulta municipal sem banco

Após a conexão funcionar:

```powershell
python scripts/importar_postos_osm.py --joao-pessoa --somente-fonte --tentativas 2 --salvar-json relatorios/osm_fonte.json --relatorio relatorios/osm_fonte_teste.json
```

Confirme:

- status: ok
- municipio.codigo_ibge: 2507507
- municipio.osm_area_id preenchido
- total_lidos maior que zero
- mysql_consultado: false

Esse comando grava somente os arquivos locais solicitados.

## Configuração opcional da Overpass

No .env local:

```dotenv
OSM_OVERPASS_URLS=https://overpass-api.de/api/interpreter,https://overpass.private.coffee/api/interpreter
OSM_USER_AGENT=LitroDeOuro/1.1 (+https://github.com/odethemets/litro_de_ouro_app)
```

São aceitos de um a três URLs HTTPS /api/interpreter.

A variável antiga OSM_OVERPASS_URL continua sendo aceita como
endpoint principal quando OSM_OVERPASS_URLS não estiver definida.

A lista explícita define a ordem dos mirrors.

Há até três chamadas por operação, duas por padrão.
As novas tentativas respeitam backoff e Retry-After.
Se a espera superar --max-espera, a execução termina.
O importador não troca de mirror para contornar essa espera.

Falhas de TLS não desativam a verificação do certificado.

## Dependências para consultar o banco

```powershell
python -m pip install -r requirements-osm.txt
```

Os modos --teste-conexao e --somente-fonte não precisam do MySQL.

## Conexão com a Aiven

O importador tem conexão própria, sem iniciar o Flask.
Não modifica app/db.py.

Variáveis locais, preenchidas com os dados reais do seu serviço:

```dotenv
DB_HOST=host-do-seu-servico
DB_PORT=26841
DB_USER=avnadmin
DB_NAME=defaultdb
DB_PASSWORD=senha-configurada-localmente
DB_SSL_CA=C:/caminho/para/ca.pem
```

Use host, porta, usuário e nome do banco efetivos do seu serviço.

Obtenha o certificado CA no painel da Aiven e informe seu caminho
em DB_SSL_CA. Se a cadeia já for confiável no sistema, o caminho
pode ser omitido.

O importador verifica o certificado e o nome do servidor.
Não desative TLS para resolver erro de certificado.

Não publique senhas no Git nem envie seus valores no chat.

## Prévia com comparação no MySQL

Após salvar uma resposta municipal válida:

```powershell
python scripts/importar_postos_osm.py --arquivo relatorios/osm_fonte.json --dry-run --relatorio relatorios/osm_previa.json
```

A prévia executa consultas SELECT.
inseridos e vinculados devem permanecer em zero.

Arquivos JSON antigos sem área administrativa permitem apenas prévia.
Para aplicar uma carga, use o JSON obtido pelo modo --joao-pessoa.

## Aplicação real

Somente após revisar a prévia e decidir executar:

```powershell
python scripts/importar_postos_osm.py --arquivo relatorios/osm_fonte.json --aplicar --relatorio relatorios/osm_aplicacao.json
```

A aplicação insere novos postos com nome na mesma transação.
Não atualiza os registros existentes e não concede karma.

Uma prévia posterior deve reconhecer os identificadores inseridos.

Se houver falha de comunicação durante a confirmação do commit,
o resultado pode ficar indeterminado para o cliente. Confira o banco
antes de repetir a aplicação.

## GitHub Actions

O workflow fica na raiz do repositório:

.github/workflows/osm_sync.yml

Execução agendada:
- Segunda-feira, 09:17 UTC.
- Segunda-feira, 06:17 em João Pessoa.
- O horário está sujeito ao agendamento do GitHub.

Execução manual:
- Actions → workflow → Run workflow.
- aplicar começa desmarcado.

O cron executa somente prévia enquanto OSM_SYNC_APPLY não for true.

Uma execução manual com aplicar=true solicita gravação explicitamente,
independentemente do modo configurado para o cron.

O workflow precisa estar na branch padrão para o agendamento.
Ele não executa deploy.

## Secrets do GitHub

Em Settings → Secrets and variables → Actions:

- DB_HOST
- DB_PASSWORD
- DB_USER, opcional; padrão avnadmin
- AIVEN_CA_PEM, conteúdo integral do certificado CA

O certificado deve incluir as linhas BEGIN e END.

## Variables do GitHub

- OSM_DB_PORT, opcional; padrão 26841
- OSM_DB_NAME, opcional; padrão defaultdb
- OSM_OVERPASS_URLS, opcional
- OSM_SYNC_APPLY, começar com false

Ativar OSM_SYNC_APPLY=true habilita gravações no cron.

Comece com uma execução manual em prévia e revise seu relatório.

Os relatórios e a resposta da fonte são guardados como artifacts
por 30 dias. As execuções do workflow não se sobrepõem.

Se houver restrições de rede na Aiven, o executor precisará ter acesso
ao serviço conforme a política de rede existente.

## Testes offline

```powershell
python -B -m unittest discover -s tests -p "test_osm_batch.py"
```

Esses testes usam HTTP e banco simulados.
Não consultam a Overpass nem gravam no MySQL real.

Cobrem:

- Consulta pela área administrativa.
- Validação do município.
- User-Agent e URLs.
- Retry-After e troca limitada de mirror.
- Validação TLS.
- Exclusão de candidatos sem nome.
- Reconhecimento de identificadores existentes.
- Ambiguidades no banco e no próprio lote.
- Prévia sem gravações.
- Rollback em falhas simuladas.
- Relatórios sem credenciais.

A conexão real com a Overpass e a prévia no seu banco precisam
ser confirmadas pelos testes locais.