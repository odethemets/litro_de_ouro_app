# Auditoria técnica — Litro de Ouro

Destinatário: Codex web. Referência: 15/11/2026, America/Fortaleza. Raiz: `C:/litro_de_ouro`. Auditoria de leitura e testes isolados; nenhum código de produto foi corrigido. As modificações encontradas já existiam antes desta análise.

## Conclusão

O aplicativo tem um fluxo integrado de sessão, catálogo, Mapa/Feed, cadastro, favoritos, votos, Karma, central de avisos, assistente e foto. A implementação atual inclui também executor de alertas, prévia OSM e CORS/saúde, que foram acrescentados antes desta auditoria, apesar de a aplicação do executor ter ficado interrompida neste chat anterior.

Na versão atual passaram **113 testes frontend**, **211 casos unittest backend em 12 suítes**, mais **dois scripts de assertivas** (IA e geofence). TypeScript, ESLint e exportação web passaram. Os testes automatizados não demonstram login/e-mail, voz, foto, GPS físico ou provedores funcionando no aparelho. Duas reproduções isoladas adicionais confirmaram lacunas do cadastro: HTTP 408 classificado como rejeição definitiva e ausência de consulta da disponibilidade no servidor.

O backend em execução respondeu 200 em `/health/live` e `/health/ready`. Consulta local de leitura confirmou **59 postos, 55 com ID OSM e 4 com prefixo [TESTE]**, migrações 001–004 registradas como aplicadas e **1 evento pendente**. A fila não foi processada. O executor está instalado e o diagnóstico funciona; não havia executor contínuo entre os processos do container inspecionado.

É possível continuar testes locais isolados. Para piloto online, ainda faltam configuração/homologação e decisões operacionais; o transferidor de quatro tabelas não cobre o schema atual. Recomenda-se primeiro corrigir a consistência do cadastro, sem refazer os blocos já aplicados. O pacote de fontes exatos está em `ARQUIVOS_PARA_PROXIMO_BLOCO.md`.

## 1. Versão e alcance

- Git: branch `main`, HEAD `0ec3c786b2f07e32c7e06d0cf73da5c9b9ee9194`; tracking local indica um commit atrás de origin/main. Não houve fetch, portanto isso não atesta estado remoto atualizado.
- Árvore extensa de modificações/arquivos novos; 35 entradas rastreadas alteradas/excluídas no diff inicial. Dois workflows antigos em `back_end/.github/workflows/` estão excluídos; workflows atuais estão na raiz `.github/workflows/`. Novos arquivos não aparecem no diff de HEAD. Ver `GIT_STATUS.log`, `GIT_DIFF_STAT.log`; `git diff --check` exit 0, com avisos LF/CRLF.
- `FONTES_INICIO.json` identifica fontes, configurações não secretas e migrações por SHA-256. `VERIFICACAO_FINAL.json` confere preservação desses arquivos. O inventário não inclui conteúdo de env, dumps, certificados privados ou fotos.
- Instrução local lida: `front_end/AGENTS.md`. Nenhum fonte Expo/RN foi editado e não houve migração de navegação. React Navigation é a implementação atual, independentemente da preferência Router escrita no arquivo.
- Node 24.11.0; instalados Expo 58.0.25, React 19.3.0, RN 0.88.1, Axios 1.21.0, TypeScript 6.0.3. `package.json`/lock identificados no manifesto; nenhum pacote instalado.
- Runtime Docker: Python 3.12.16, Flask 3.0.3, PyMySQL 1.1.0, google-genai 2.34.0, Pillow 13.0.0, gunicorn 22.0.0, Flask-Cors 4.0.1. Pillow está sem pin em requirements; é risco de reprodutibilidade futura, não falha observada.
- Imagem do container observado: `sha256:3867bfc2fd0ce7673cd86be328b798ba5a40a700f7b99d1f7bbff7eaf499fcf6`. O label Compose de imagem tem outro ID; o valor `.Image` é a identificação efetiva observada. Isso por si só não comprova erro.
- Compose efetivo: `compose.yaml` + `docker/compose.testes-precos.yaml`. Backend em 5001→5000 nas interfaces IPv4/IPv6; MySQL somente 127.0.0.1:3307→3306. Cinco pastas app/services/scripts/tests/migrations montadas read-only, além da CA. Não foi impressa a configuração resolvida completa.
- Sete hashes de arquivos no container coincidem com o disco (`COMPARACAO_RUNTIME.json`). A fábrica importada num novo processo no container veio de `/app/app/__init__.py`; o servidor ativo respondeu às rotas novas. Isso não é uma inspeção da memória de cada worker. Não houve restart/build.

## 2. Arquitetura e integração real

`front_end/package.json:main` → Expo AppEntry → `App.tsx` → provedores Theme/Auth/SafeArea → `routes/index.tsx` → AuthRoutes ou AppRoutes. INITIALIZING tem recuperação explícita; visitante e autenticado acessam consulta; Adicionar/IA/Perfil passam por AcessoRestrito.

`routes/app.routes.tsx` registra Mapa como ConsultaPostos e Feed como ConsultaPostos em modo lista. FavoritosProvider e FiltrosPostosProvider envolvem as abas. A pilha de perfil registra Conta, Atividade, Histórico de Karma, Ranking, Configurações, Dados Pessoais, Apagar Conta, Aparência, Favoritos, Redefinir Senha, Notificações e Preferências.

`back_end/app/__init__.py:create_app` configura SECRET_KEY, chama configurar_web uma vez e registra dez blueprints. `RUNTIME.json` lista caminhos/métodos/endpoints reais. `app/db.py` usa o conector compartilhado; este usa DictCursor, TLS com verificação de hostname e CA, autocommit=False, timeout conexão 10 s e leitura/escrita 30 s. DATABASE_URL prevalece sobre DB_*. O runtime auditado foi validado como `db`/`litro_de_ouro_dev` antes de consultar agregados.

### Fluxos centrais

1. **Sessão/conta:** Login/código → api → auth.py → validação de campos e locks da conta → hash de senha/código → commit → e-mail externo quando cabível → JWT → signIn valida `/auth/perfil` antes de publicar token. controleSessao usa revisão para descartar resposta antiga; sessao.ts serializa armazenamento. Nativo SecureStore, web AsyncStorage; chave derivada da API. API.ts só injeta token ativo e rejeita em 401 a sessão correspondente ao Bearer original. Falha transitória na inicialização preserva armazenamento e oferece tentar novamente.
2. **Catálogo:** filtros → FiltrosPostosContext → GET /postos → validar_filtros → consultar_catalogo → três SELECTs em lote (postos, ofertas, últimos preços) → lerCatalogo → cartões/mapa. Sem chamada OSM/Mapbox nesse GET. Localização inexistente não envia coordenada fictícia. Ao focar Mapa/Feed, recarregar incrementa revisão; requests antigos são abortados.
3. **Preço:** detalhes → navegar Adicionar com posto/produto/solicitação → formulário → criarEnvioPreco → GPS → conferir token atual → POST /precos → decorator JWT/versão → registrar_preco_validado → locks usuário e posto → geofence/cooldown → INSERT preço + score 1 + Karma +5/histórico + evento → commit → confirmação 201 validada → recarregar catálogo. Erro 5xx/sem resposta gera estado incerto; HTTP 408 é exceção defeituosa descrita em A02. Não há chave de idempotência de requisição; cooldown não equivale a exatamente uma vez.
4. **Oferta/voto:** confirmar oferta requer revisão/GPS; mantém negativa explícita e repetição idempotente. Voto consulta somente quando solicitado, por registo_id exato. POST lê autor, descarta snapshot inicial, trava conta autora → registro → voto; repetição não altera, troca aplica delta. Commit inclui score/Karma/histórico. Falha faz rollback; resposta perdida exige consultar, sem retentativa automática.
5. **Avisos:** cadastro grava evento na mesma transação → processar_pendentes recebe a conexão → trava evento por ID crescente e preferências elegíveis → favorito posto E produto, opt-in, queda/intervalo → INSERT aviso único usuário/registro → marca evento → commit por evento. Sem destinatários também marca/processa. Sem filtro que exclua o autor; ele pode receber se elegível. Intervalo usa tempo do aviso, não agenda um aviso atrasado. Evento inválido permanece pendente e interrompe a rodada.
6. **Assistente:** tela por token/status → texto ou transcrição revisada → serviço captura token/filtros/GPS → POST /ia/consultar → comando objetivo local ou Gemini sob limite → validação estrita dos filtros → catálogo real → prévia até 20 → confirmação aplica ao mesmo contexto Mapa/Feed. Mudança de filtros/GPS bloqueia aplicar prévia velha. Cancelamento não garante cancelamento da chamada externa no servidor.
7. **Foto:** galeria → validar metadados → usuário escolhe Ler → Blob/arquivo preparado antes do GPS → multipart com Bearer/signal → JWT/posto/geofence → Pillow → Gemini → normalizar quatro líquidos → upload somente se guardar_comprovante=true → revisão → usar preenche preço/URL; cadastrar é uma ação separada. Falha de Dropbox não perde preços. Link inválido é descartado no cliente. A URL permitida não é prova criptográfica de autoria/propriedade da foto.
8. **OSM:** job CLI → revisar_osm com arquivo ou Overpass municipal → normalização/limite municipal → opcional comparação read-only com conexão verificada → fonte/relatório/manifesto. Importar novos e completar metadados são scripts distintos e potencialmente escrevem; não estão acoplados ao GET /postos. Nenhum foi ativado pela auditoria.

## 3. Matriz de funcionalidades

Referências abaixo são relativas à raiz auditada; símbolos e linhas centrais aparecem nos achados e nos fontes anexos. “Teste” refere-se às evidências desta auditoria, não a totais históricos.

| Recurso | Arquivos/símbolos | Integração real | Evidência atual | O que falta | Próxima ação |
| --- | --- | --- | --- | --- | --- |
| Login/cadastro/código/recuperação | routes/auth.routes.tsx; auth.py login/confirmar_email/cadastro/recuperar_senha/redefinir_senha | Telas e rotas registradas | Leitura de código; testes frontend de contratos/sessão | E-mail e fluxo completo reais | configuração + teste real |
| Limites auth | auth.py:108,150,273; conta.py:_autorizar_senha | 60 s reemissão; código 15 min/5 tentativas; login 5 falhas→15 min; senha nova 6–1024 | Inspeção estática | Cobertura backend de abuso/IP/distribuição não demonstrada; sem rate-limit global identificado | código/teste real conforme risco do piloto |
| JWT e visitante | decorator.py:11; controleSessao.ts:29; sessao.ts; API.ts | JWT HS256 7 dias, versão no DB; visitante token null | Testes fundação; conector/rotas inspecionados | E2E de duas sessões | teste real |
| Persistência/recuperação | AuthContext; controleSessao; sessao | Valida perfil antes de liberar; SecureStore/AsyncStorage por API; serialização e revisão | Testes frontend atuais | Dispositivo/armazenamento negado reais | teste real |
| Nome/e-mail/senha | conta.py:153,195,327; DadosPessoais; RedefinirSenhaConta | Nome autenticado; troca e-mail exige senha e código HMAC, versão invalida sessões; redefinição por código | Rotas/imports e testes cliente | E-mail real e testes backend completos de conta | configuração + teste real |
| Apagar conta | conta.py:419; ApagarConta | Senha + APAGAR; lock e DELETE transacional/cascatas; disponibilidade manual preservada sem autor | Código/schema; integração histórica não reexecutada | Score/Karma após apagar votante, fotos/backups | decisão + correção + operação |
| Filtros/bandeira | catalogo_postos.py:36,86; filtros-postos; FiltrosPostosContext | Seleção múltipla OR entre ofertas, cruzada com marca; referência deve integrar seleção quando não vazia | 25 casos catálogo backend + frontend | Caso acima de 500 candidatos | código/teste escala |
| Referência/sem preço | catalogoPostos.ts ofertaReferencia/lerCatalogo; catálogo backend | Referência única; padrão gasolina comum; sem substituição de preço | Testes catálogo | Sem homologação visual | teste real |
| Oferta ≠ preço | segmentosPosto/rotuloPreco; consultar_catalogo | Triestado; manual precede OSM; barrinhas só oferta true/interseção | Testes catálogo e leitura | Regra servidor cadastro divergente | correção A01 |
| Classificação preço | catalogoPostos.ts:158 classificarPreco | Faixa min–max da consulta, não média/mediana; detalhes abaixo | Código/testes | Amostra municipal completa não garantida | decisão de produto |
| Cores/unidades | COMBUSTIVEIS; theme/design.ts | Seis cores exatas solicitadas; L/m³/kWh; comparação mesma referência | Inspeção/testes | Contraste/tamanho real | teste real |
| Eletropostos/mistos | ConsultaPostos pinos; produtosCadastro; precos.py:274 | Raio no ícone por tipo ou oferta elétrica true; cadastro elétrico exige tipo Eletroposto | Código | Locais mistos com oferta elétrica em posto convencional não têm cadastro elétrico | decisão + código |
| Mapa web/nativo | MapaLeaflet.web.tsx / MapaLeaflet.tsx; mapaHtml | iframe sandbox e WebView usam mesmo HTML Leaflet | Imports ativos/build | Renderização/tiles/provedor reais | teste real + configuração |
| Clusters/decluttering | mapaHtml:renderizarPostos | Grade projetada 100×72 px abaixo de zoom 17; selecionado isolado; rótulos colidentes omitidos | Análise do algoritmo, não teste visual | Sobreposição de pontos coincidentes em zoom alto | teste real/decisão |
| Lista/detalhes/busca | ConsultaPostos lista/escolher/detalhes; ListaPostosConsulta | Busca por nome só Feed; lateral desktop 360 px; modal mobile; retorno e rolagem | Imports/código | “Região” não acompanha bbox visível | decisão/código |
| Imersivo/emergência | ConsultaPostos/layout | Controles de filtros/GPS/lista/legenda; sem modo imersivo ou botão de emergência encontrados no fluxo ativo | Busca/inspeção | Funcionalidades não implementadas no fluxo atual | decisão + código |
| Acessibilidade/temas | design/AppButton; ThemeContext; layout; mapaHtml | Botões comuns ≥48 px, temas e SafeArea; mapa usa cores fixas | Código e lint, sem auditoria visual | Fonte ampliada, contraste, teclado/leitor de tela; mapa não recebe tema | teste real + código visual |
| GPS cadastro | utils/localizacao; geofence.py:107 | Cliente idade≤15 s/precisão≤150 m; servidor distância+folga≤100 m e simulada | Scripts geofence/contratos | GPS físico; servidor não autentica origem do GPS nem exige timestamp | teste real/decisão |
| Raio | geofence.py:41; override Docker | Padrão 500 m; runtime 50 km de desenvolvimento | Runtime aviso/Compose | Ajuste explícito de produção e homologação presencial | configuração + teste real |
| Cadastro/Karma/evento | precos.py:114; atividade_alertas:6 | Commit atômico, +5 e score inicial1; cooldown padrão15 min | Código; contratos cliente | Disponibilidade no servidor, timeout ambíguo, banco concorrente atual | correção + teste isolado |
| Votos | votos.py:35; votar-preco.tsx | Autor bloqueado; repetição/swap; score ±1 e Karma autor±2; swap ±2/±4 | Código/testes frontend; MySQL concorrente não reexecutado | Exclusão votante/ordem global de locks | decisão + testes descartáveis |
| Ranking/histórico | participacao.py ranking/karma; Raking; HistoricoKarma | Ranking público top50; histórico conta último100 + saldo | Rotas/imports | Paginação além dos limites | decisão + código |
| Favoritos/preferências | FavoritosContext; participacao.py | Persistência servidor por conta, confirma resposta, não otimista irrevogável | Testes conta/participação frontend | Texto antigo “neste dispositivo” em Configurações contradiz servidor | correção editorial |
| Central avisos | notificacoes/marcar_lida; Notificacoes | Lista último100; total não lidas; marcação por conta | Código/testes cliente | Mais de100 sem cursor; não existe push | decisão + código/teste real |
| Fila e executor | atividade_alertas.py:21; executor_alertas; executar_alertas | Diagnóstico/rodada/ciclo disponíveis; contrato conn, limite e retorno eventos | 17+9 testes incluídos nos211; diagnóstico read-only atual | Integração adaptador MySQL/ciclo gerenciado não executada | teste descartável + ativação futura |
| Assistente texto | Assistente; assistente.ts; comandos_ia; assistente.py | Prévia/revisão/token/contexto; catálogo separado do modelo | 10 testes sessão; código | Teste real Gemini; teste assistente.test.cjs citado em entrega antiga segue ausente | configuração + teste real/cobertura |
| Voz | voz.web.ts / voz.ts | Web Speech API em contexto seguro; nativo retorna indisponível, ditado teclado | 3 testes simulados voz | Microfone/navegador/aparelho | teste real; captura nativa é futuro código |
| Gemini | ia.py; requirements | google.genai compatível; timeout foto45 s, assistente12 s; 12 usos/hora por processo compartilhados | SDK instalado e testes simulados | Chave/modelo explícito ausentes no runtime; quota multiworker não global | configuração + teste real |
| Foto/comprovante | leitor-totem; leituraTotem; leitura_totem; ia.py | R$1–25 OCR, quatro líquidos, 8MB/24MP/1600px; sem EXIF/ICC; consentimento defaultoff | 17 testes frontend foto;8 Pillow; script IA | GPS/foto/Dropbox real; retenção/exclusão externa | configuração + teste real/decisão |
| Custo do trajeto | Inicio legado; mapbox_service | Sem tela/API ativa de custo por rota; detalhe abre Google Maps | Grafo/imports/busca | Rota ida/consumo por L,m³,kWh/preço e contrato Mapbox | decisão + código + configuração |
| CORS/saúde | infra_web; create_app | Uma configuração; produção exige HTTPS origens exatas; OPTIONS/JWT/PATCH/PUT/DELETE; nativo sem Origin |17 testes HTTP Flask+mocks; saúde real200 | APP_ENV/CORS produção não definidos | configuração, não regressão local |
| Migrações/TLS | 001–004; contrato/migrations/database | MySQL8.4.13, quatro registros/checksums; TLS no conector | Read-only e testes infra | TiDB/FKs/locks/DDL não homologados remotamente | teste real/decisão |
| Transferência | transferencia_banco TABLES | CLI existe, limitado a quatro tabelas | Leitura e27 testes escopo antigo | Schema ampliado, plano de restauração | código A03 + teste descartável |
| OSM prévia | revisar_osm/executar_job_osm | Arquivo/Overpass, comparação somente leitura, artefatos |11+13 testes; hash municipal confirmado | Cobertura/atualidade remota não verificada | teste real/revisão catálogo |
| OSM escrita/metadados | importar_postos_osm/completar_catalogo_osm | Aplicar explícito; novos separados de enriquecimento; ambiguidades não fundidas |20+33 testes mocks | Compatibilidade GET_LOCK/TiDB e operação online | código/configuração/teste real |
| Workflows | .github/workflows/osm_sync.yml e osm_diagnostico.yml | Prévia cron condicionada por variável; manual; artefatos30dias | Leitura YAML; não acionados | Secrets/vars/remoto não verificados | configuração/ativação posterior |
| Render/Vercel | Dockerfile; vercel.json; check-vercel-env | Vercel valida URL públicaHTTPS; Docker bind fixo5000; sem render.yaml encontrado | Código/build local | PORT/health/deploy/URLs online, domínios e secrets | configuração + teste real |
| Privacidade | ApagarConta; leitor/assistente; Configurações | Avisos parciais IA/Dropbox/exclusão; sem tela de política/controlador localizada | Inspeção técnica | Política acessível, controlador completo, retenção, backups, provedores | decisão + código/operacional |

### Fórmula, amostra e custos

`classificarPreco` considera preços da mesma referência com data válida, não mais de 5 s no futuro e até 72 h de idade. Calcula `(preço−mínimo)/(máximo−mínimo)`: ≤0,33 verde #166534, ≤0,66 amarelo #8A6500, restante vermelho #B42318. Menos de dois preços ou todos iguais: neutro #171923; sem preço/fora do período: cinza #596273. Não é selo de confiança. A amostra é o resultado da consulta atual, não todos os postos da cidade e não apenas os visíveis no viewport. Pinos e cartões usam esse resultado; IA usa sua prévia, cuja amostra pode ser menor.

Cores de produto conferidas: comum #1D4ED8, aditivada #0891B2, etanol #7C3AED, diesel #374151, GNV #8B5E3C, energia #C026D3. Seleção/foco usa outra camada visual. Há tabela duplicada de cores em theme/design.ts e catalogoPostos.ts, hoje consistente.

Catálogo limita candidatos por ID a500 antes dos filtros finais/ordenação: em expansão pode omitir resultados melhores ou da bandeira desejada. Hoje há59, portanto não se demonstrou truncamento local. Três SELECTs não significam custo constante: último preço usa subconsulta correlacionada. Classificar cada pino varre a lista (O(n²)); etiquetas do mapa também podem exigir comparações quadráticas. Sem benchmark, não se afirma lentidão ou consumo excessivo medido. Lista usa ScrollView/map, não virtualização por janela.

JWT demanda uma conexão/SELECT de versão por request protegido além da conexão da operação. Favoritos GET também trava a conta em `_executar`; leitores podem competir com gravações. Fila faz consultas por destinatário para intervalo, uma transação por evento; nenhum benchmark/concurrency test real novo. Saúde cacheia5s por processo sob Lock e fecha/rollback da conexão, mas verifica registro de migrações, não equivalência completa de todas as colunas/índices físicos.

Leitor envia imagem≤8MB; backend valida24MP antes do load e usa JPEG draft, mas pode decodificar/transformar buffers múltiplos. Não há medida de pico RAM. Timeout cliente60s não desfaz commit/upload; aviso de resultado incerto precisa ser conservador. E-mail HTTPS tem timeout10s e limite de resposta64KB. Foto e texto não consultaram provedores nesta auditoria.

## 4. Achados priorizados

### A01 — Cadastro não revalida disponibilidade do produto

- Prioridade: P1, integridade da regra de produto. Tipo: correção/código.
- Arquivo/símbolo: `back_end/app/rotas/precos.py:114 registrar_preco_validado`, particularmente tipo do posto em274 e INSERT em337; cliente `front_end/src/services/cadastroPreco.ts:57 produtosCadastro` exclui oferta false.
- Evidência/reprodução: `reproduzir_oferta.py`, `REPRO_OFERTA.json`. Função real em contexto Flask, banco/Karma simulados; oferta false disponível no simulador se consultada. Retornou201, commit/Karma simulados1, nenhuma consulta a postos_combustiveis. Não testa banco real nem JWT (chama lógica já autorizada diretamente).
- Atual/esperado: servidor verifica classe convencional/elétrica, mas não negativa explícita do produto; cliente rejeita. Um catálogo desatualizado ou chamada direta passa por esse filtro apenas no cliente. Esperado, mantendo regra atual: recusar false, permitir desconhecido sem convertê-lo em confirmado.
- Impacto/limite: cadastro e Karma para produto proibido pela interface; não houve inserção real. Se produto permitir preço observado apesar de oferta false, isso precisa ser decisão explícita e interface consistente.
- Correção mínima proposta: ler disponibilidade efetiva (manual precede OSM) dentro da transação/ordem de locks, antes de INSERT. Não alterar oferta como efeito colateral.
- Teste: false manual/OSM → recusa sem preço/Karma/evento; null permitido; concorrência de mudança de disponibilidade em MySQL descartável.

### A02 — HTTP 408 libera nova tentativa após resultado potencialmente incerto

- Prioridade: P2. Tipo: correção.
- Arquivo/símbolo: `front_end/src/services/cadastroPreco.ts:250 criarEnvioPreco`; `screens/AdicionarPreco/index.tsx:118 bloqueado`.
- Evidência: `reproduzir_408.cjs` e `REPRO_408.json`, serviço real transpilado e HTTP simulado: tipo observado rejeitado, um POST simulado, sem rede.
- Atual/esperado: qualquer4xx vira rejeitado; UI só bloqueia incerto. Timeout HTTP não comprova ausência de commit, especialmente em intermediários. Esperado: 408 segue conferência da atividade antes de reenviar.
- Impacto/limite: risco de nova tentativa/confusão após processamento; cooldown15min reduz repetição, não prova idempotência. Não se reproduziu preço duplicado real.
- Correção mínima: excluir408 da classificação de recusa definitiva e preservar estado incerto. Testar408,400,409,429,5xx,timeout sem resposta e confirmação201 inválida.

### A03 — Transferidor TiDB não cobre o schema ampliado

- Prioridade: P1 para migração/piloto; sem bloquear laboratório. Tipo: código/teste real.
- Arquivo/símbolo: `back_end/services/transferencia_banco.py:19 TABLES`; validações em406,439,479,901. Migrações001–004 e tabelas em RUNTIME.json.
- Evidência: configuração fixa de postos,usuarios,registos_preco,votos_registos. Há15 tabelas locais, incluindo marcador local e registro de migrações; várias tabelas de produto fora do conjunto. Testes27 validam o escopo antigo, não migração integral.
- Atual/esperado: ferramenta de quatro tabelas não deve ser tratada como transferência completa; pode recusar schema diferente pelas próprias guardas. Não executada, portanto não se afirma perda já ocorrida.
- Correção proposta: planejar conjunto de tabelas por dependência, política para dados transitórios e excluir marcadores locais; verificar contagens/checksums, migrações e restore antes do corte. Teste MySQL→TiDB descartável, nunca base do responsável.

### A04 — Exclusão de votante pode deixar score/Karma derivados sem correspondência

- Prioridade: P2, risco estático/decisão de produto. Tipo: decisão + possível correção.
- Arquivos: `conta.py:430 apagar`, `docker/schema_base.sql:40–47`, `votos.py:63–76`.
- Evidência: DELETE usuário cascata votos; score e Karma do autor foram incrementados separadamente. Não há compensação/recomputação em apagar. Sem execução real de exclusão nesta auditoria.
- Cenário seguro proposto: duas contas sintéticas, voto em registro de outra conta, apagar votante, comparar contagem/score/Karma. Esperado precisa ser definido: preservar contribuição anonimamente ou desfazer consistentemente. Hoje a contagem pode perder o voto enquanto score/Karma ficam.
- Correção mínima depende da política; exigir teste transacional e concorrente antes de implementar. Não prometer “saldo inconsistente” em todas as exclusões: depende de vínculos e política desejada.

### A05 — Build web passa com URL local que o módulo recusa em produção

- Prioridade: P1 para servir este artefato; configuração, não regressão de código.
- Arquivo: `front_end/src/services/configuracao.ts:1–18`; `scripts/check-vercel-env.cjs` e `vercel.json`.
- Evidência: CONFIG_BUILD.json registra apenas presença/esquema: URL local HTTP; import isolado com __DEV__=false lança erro esperado. Exportação transpila, sem provar inicialização no navegador.
- Atual/esperado: bundle local não deve ser tomado como homologação da aplicação publicada. Configurar endpoint HTTPS para build de produção; não enfraquecer a validação para esconder o problema. Teste de import/build com HTTPS seguido de smoke visual. Nenhum valor secreto foi exposto ou env alterado.

### A06 — Ausência de política acessível e ciclo de fotos/backups

- Prioridade: P1 de preparação do piloto; decisão/código/operação. Não é parecer jurídico.
- Arquivos: `screens/Configuracoes/index.tsx`, `routes/app.routes.tsx`, `ApagarConta/index.tsx:90`, `services/dropbox_services.py:5`.
- Evidência: busca/imports não localizaram tela/link de política nem identificação completa do controlador. Serviço só faz upload/link; DELETE conta não chama remoção externa. Há aviso explícito de que imagens/backups exigem procedimento separado.
- Atual/esperado: avisos específicos são úteis mas não documentam retenção, fornecedores, direitos e exclusão operacional. E-mail público do projeto não identifica sozinho o controlador. Não se conclui conformidade ou infração jurídica a partir dessa auditoria técnica.
- Proposta: definir controlador e política de retenção/backup/links, publicar acesso nas telas e implementar procedimento auditável de remoção quando definido. Teste de navegação e ensaio de exclusão de foto sintética em ambiente apropriado.

### A07 — Limites de catálogo e central não têm continuação

- Prioridade: P2 para crescimento; risco/decisão, sem falha local reproduzida.
- Arquivos: `services/catalogo_postos.py:99` (500 candidatos antes dos filtros), `app/rotas/participacao.py:notificacoes/karma/ranking` (100/100/50).
- Cenários: posto elegível além dos500 IDs; aviso não lido anterior aos100 mais recentes. A contagem global de não lidas pode incluir itens sem acesso pela lista atual.
- Proposta: filtros/ordenação antes de limite ou paginação adequada; central com cursor e política de retenção. Testes sintéticos >500 candidatos/>100avisos, preservando autorização. Não aumentar limites sem avaliar custo.

## 5. Infraestrutura, OSM e privacidade: decisões e limites

Produção CORS exige APP_ENV=production e origens HTTPS exatas (sem regex aberta); local/test aceitam coringa. Runtime atual não define APP_ENV/CORS_ORIGINS, logo usa política local. Isso é configuração deliberada de laboratório. JWT não depende de CORS; CORS não bloqueia clientes nativos. Health ready tem resposta503 sanitizada e verificação de migrações, sem iniciar migração.

O Dockerfile expõe/binda5000 fixo; não há render.yaml. O serviço de hospedagem precisa ajustar/confirmar porta e healthcheck; ausência de manifesto não demonstra deploy quebrado. Vercel tem npm ci + guard de URL + export e rewrite SPA. Nenhum painel Render/Vercel/TiDB/GitHub foi acessado; não se afirma destino online ativo. Perfis de transferência ausentes no ambiente do container, sem extrapolar para arquivos externos/host.

No runtime faltam GEMINI_API_KEY/GEMINI_MODEL, DROPBOX_TOKEN, MAPBOX_TOKEN, GOOGLE_SCRIPT_URL/SECRET. SECRET_KEY e configuração local DB/CA estão presentes. O e-mail real usa Google Apps Script/Gmail (`email_services.py`), apesar do alias histórico enviar_email_resend em auth; RESEND não é o transporte ativo. Configuração ausente explica indisponibilidade dos ensaios completos; não autoriza preenchê-la automaticamente.

Prévia OSM atual está na raiz .github, com cron segunda09:17UTC condicionado a OSM_PREVIA_AGENDADA=true; COMPARAR_BANCO depende do input/OSM_PREVIA_COM_BANCO. Permissões contents:read, concurrency sem cancelar em andamento, artefatos30dias, timeout15min; diagnóstico Overpass é manual, sem banco. Não há defaults Aiven nos workflows atuais lidos. Os arquivos antigos duplicados estão marcados excluídos no Git, não foram apagados pela auditoria.

OSM_SYNC_ENABLED é lida pelo código legado osm_service; executar_job_osm força false no subprocesso. OSM_SYNC_APPLY aparece forçada a false no job, mas não foi encontrado consumidor operacional atual dessa flag. Nenhuma delas equivale às flags de agenda/comparação do workflow. GET /postos não chama garantir_cobertura_async; grid/mapbox legado não dispara nesse fluxo.

O importador atual insere apenas novos com nome e não vincula ambiguidades automaticamente. Completar catálogo é separado, restrito ao banco local previsto, exige backup para aplicar, preserva manual, usa somente ofertas explícitas; ausência de tag não deve apagar. GET_LOCK e transações locais precisam ser avaliados no TiDB, sem pressupor equivalência. Nenhuma consulta remota OSM foi feita. O arquivo municipal presente tem SHA256 `2a8b7606f7cc47f5d76c422850dfee902dee9d2e8f88bae0407a307825e74e11`, igual ao informado. Os números88/55/9/24 são históricos; esta auditoria não repetiu essa comparação nem prova cobertura municipal completa.

Não foi executado backup/restauração/export de dados pessoais. Há ferramentas de transferência/backup pontual e fixture de integração, mas não se demonstrou plano de restore completo do schema ampliado. Os quatro [TESTE] aparecem no banco local; separação de massa pública precisa de carga inicial revisada, não de remoção automática nesta análise.

Tratamentos observados: conta/e-mail/hash senha; coordenadas em requests de consulta/cadastro/foto; histórico local de postos vistos por conta; nomes públicos em preços/ranking; texto livre para Gemini quando necessário; fala para serviço do navegador; imagem para Gemini e, por opção, link público Dropbox; tiles/CDN e rota externa podem revelar contexto de localização/IP. Não se verificou política de retenção dos provedores. Excluir conta apaga registros/vínculos por cascata, não anonimiza todo histórico nem apaga provedores/backups. Permissão do aparelho não substitui opção específica de guardar comprovante.

## 6. Código legado, manutenção e próximos passos

`IMPORTS_FRONTEND.json` registra análise estática de imports relativos (inclui tipos/variantes, não prova execução). `screens/Inicio/index.tsx` e `screens/Mapa/index.tsx` não são alcançados por App.tsx. `services/lista-postos-consulta.tsx` é duplicata fora do grafo; a ativa está em components. Templates animated-icon, themed-*, collapsible, web-badge, hooks de tema antigos e utils/cores/feedbackPostos/token também não foram alcançados. Arquivo .d.ts fora do grafo não significa inútil: pode ser consumido pelo TypeScript.

O cálculo aproximado de viagem em Inicio usa distância disponível, sem rota Mapbox ativa; não contar como custo de trajeto implementado. Helpers grid/mapbox e processar_alertas são administrativos/legados, não telas; scripts instalados não equivalem a serviços ativados.

Arquivos de código acima500 linhas no inventário: Inicio1503 (legado), AdicionarPreco902, auth.py814, grid_postos.py814, osm_service.py808, transferencia_banco.py954, importar_postos_osm.py676, test_osm_batch.py836, test_transferencia_tidb.py1037. Lockfile11413 não é candidato a refatoração manual. Sugestões futuras: formulário de preço por seções/hooks; auth por finalidade com utilitários compartilhados; importação/classificação/CLI separados; transferência por validação, cópia e prova; testes por assunto preservando isolamento. Nenhuma divisão feita.

### Respostas diretas

1. **Aplicados/integrados:** sessão/conta, consulta compartilhada, oferta/preço/voto/Karma, favoritos/central, assistente/foto, infraestrutura de saúde/CORS. Executor e prévia OSM presentes e testados como CLIs; ativação contínua não comprovada.
2. **Fora do fluxo ativo:** telas Inicio/Mapa antigas, lista em services e templates citados; cálculo de custo/Mapbox legado; scripts administrativos dependem de execução explícita. Inventário de imports anexado.
3. **Código que falta:** correções A01/A02; transferência integral; política/retencão operacional; recursos futuros custo de rota/push/voz nativa direta/imersivo/emergência. Decidir escopo antes de construir.
4. **Configuração/teste:** e-mail/Gemini/Dropbox, HTTPS/frontend/backend, CORS produção/raio, TiDB, serviços gerenciados e homologação física. Nenhum segredo preenchido.
5. **Bloqueadores:** não há bloqueador dos testes isolados que passaram. Login com verificação/e-mail e recursos externos completos não estão homologados; este build HTTP não comprova app de produção. Transferência/política/carga de teste e correções de integridade impedem declarar piloto pronto.
6. **Próximo bloco:** corrigir validação de produto no servidor e resultado incerto de cadastro, com regressões e MySQL descartável; em paralelo de planejamento, decidir política de exclusão de votos. Depois validar acesso/login no aparelho e preparar plano online/transferência. Não priorizar reescrita visual antes dessas lacunas de dados.

Não houve teste visual nesta auditoria. Roteiro: web360/768/1280px e Android/iOS, fonte100%/150%/200%, temas claros/escuros, teclado/leitor de tela; usar catálogo e gravações simulados. Testar cluster→zoom→posto coincidente, retorno dos detalhes, lista/modal, foco, formulário e troca de conta. Provedores/GPS reais exigem roteiro separado em ambiente de teste. Não há captura nem aprovação inventada.
