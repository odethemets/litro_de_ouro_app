# Explicação técnica dos módulos já integrados

Revisão própria em 13/11/2026, America/Fortaleza. Este documento explica o código copiado em `base/`, que já existia no início desta rodada. Não é uma reimplementação nem nova homologação física. Os contratos foram conferidos no código e na integração MySQL. Fontes completos em `base/<caminho-do-projeto>` permitem examinar as funções com seu contexto.

## Arquivos, símbolos e procedência

| Arquivo | Símbolos centrais | Papel / procedência na rodada anterior |
| --- | --- | --- |
| `back_end/app/__init__.py` | `create_app` | Factory existente; passou a registrar `ofertas_bp` e `votos_bp`, sem prefixos extras. |
| `back_end/app/rotas/ofertas.py` | `confirmar_oferta`, `ofertas_bp` | Arquivo novo; valida confirmação, GPS e disponibilidade anterior. |
| `back_end/app/rotas/votos.py` | `votos`, `resumo`, `votos_bp` | Arquivo novo; substitui a implementação de voto antes incluída em `precos.py` e acrescenta consulta autenticada. |
| `back_end/app/rotas/precos.py` | `registrar_preco_validado`, `registrar_preco` | Existente; grava histórico/evento junto ao preço e transfere voto ao blueprint próprio. |
| `back_end/services/atividade_alertas.py` | `registrar_karma`, `processar_pendentes` | Novo; operação transacional de Karma e fila. |
| `back_end/services/catalogo_postos.py` | `consultar_catalogo` | Existente; acrescenta `registo_id` por combustível, sem inventar disponibilidade. |
| `back_end/scripts/processar_alertas.py` | `main` | Novo; uma rodada com nome explícito do banco e limite 1–1000. |
| `back_end/scripts/testar_offline.py` | `main` | Novo; isola processos das suítes que substituem módulos Python. |
| `back_end/tests/integracao_participacao.py` | `IntegracaoParticipacao` | Novo na rodada anterior; schema completo e contas sintéticas. Nesta rodada recebeu mais um cenário de vínculo de votos. |
| `back_end/tests/test_infra_banco.py`, `test_transferencia_tidb.py` | `MigrationTests.setUp`, `StructureTests.test_previous_migration_tool_accepts_tidb_numeric_metadata` | Testes existentes: simulador limitado a 001/002 porque não implementa SQL/metadados de 003/004. |
| `front_end/src/services/catalogoPostos.ts` | `OfertaPosto`, `lerCatalogo` | Existente; preserva ID válido do preço ou usa null. |
| `front_end/src/services/ofertas.ts` | `payloadOferta`, `validarConfirmacaoOferta` | Novo; GPS atual e confirmação do mesmo posto/produto. |
| `front_end/src/services/votos.ts` | `Voto`, `AvaliacaoPreco`, `lerAvaliacao` | Novo; valida ID, contagens, score, voto e permissão. |
| `front_end/src/components/confirmar-oferta.tsx` | `ConfirmarOferta`, `ControlesOferta`, `confirmar` | Novo; revisão explícita, GPS e envio. |
| `front_end/src/components/votar-preco.tsx` | `VotarPreco`, `ControlesVoto`, `consultar` | Novo; carrega avaliações sob demanda e envia voto do registro. |
| `front_end/src/screens/ConsultaPostos/detalhes.tsx` | `DetalhesPostoConsulta` | Existente; inclui controles por produto com ID exato. |
| `front_end/src/screens/ConsultaPostos/index.tsx` | `ConsultaPostos`, `detalhes` | Existente; passa `recarregar` para `onAtualizar` da oferta. |
| `front_end/tests/participacao.test.cjs` | Oito cenários `node:test` | Novo; contratos de oferta/GPS/avaliação. |

Os fontes de suporte `app/db.py`/`services/database.py`, `token_required`, `conta.py`, `participacao.py` e migrations estão copiados na base quando pertinentes. Migrações não foram alteradas. Componentes consultam `useAuth`, o catálogo vem de `FiltrosPostosContext`; os estados de revisão/avaliação são locais ao controle. Não existe um segundo catálogo nos componentes novos.

## Oferta: fluxo e contrato

`DetalhesPostoConsulta` mostra `ConfirmarOferta` apenas para produto compatível com cadastro e disponibilidade desconhecida. Visitante vê caminho para login. Usuário autenticado abre a revisão, aciona “Verifiquei”, chama `obterPosicao("registro")` e `payloadOferta`, depois envia pela instância `api` com a sessão capturada.

```text
POST /postos/123/ofertas/gnv/confirmar  (Bearer da sessão)
{ "confirmado": true, "latitude": -7.11, "longitude": -34.86,
  "precisao_m": 10, "simulada": false }

200 { "posto_id": 123, "codigo": "gnv", "disponivel": true, "origem": "manual" }
```

IDs/coordenadas são fictícios. Os seis códigos são os de `CATALOGO`. Backend exige JSON objeto, código conhecido, `confirmado is True`, `simulada is False`, precisão numérica finita não negativa, posto existente e produto compatível com `tipo_posto`. `validar_proximidade` aplica raio configurado e precisão máxima. O timestamp tem validação de frescor no cliente (15 segundos); o servidor recebe coordenadas reportadas e não consegue provar que vieram de um GPS físico.

`token_required` verifica JWT, conta e versão de sessão em uma conexão própria, que fecha antes da operação. Na transação de oferta, lock exclusivo do posto precede leitura `FOR UPDATE` da relação produto/posto. A PK composta protege unicidade, inclusive se a relação não existia. Disponibilidade manual prevalece sobre OSM. Efetivo 0 resulta em 409; efetivo 1 confirma sem reescrever origem/auditoria; desconhecido recebe manual=1, data UTC e autor. Commit confirma essa relação; falha provoca rollback e resposta 503. Retornos antes de commit fecham a conexão e liberam os locks sem gravação.

Erros: 400 para payload/produto/compatibilidade/precisão malformada; 401 para sessão recusada; 403 para simulada/fora do raio; 422 para precisão excessiva; 404 para posto ausente; 409 para negativa efetiva; 503 para falha operacional. Validação de coordenadas pode produzir 400 conforme `GeofenceError`; problemas de configuração/dados do posto não são uma confirmação de oferta.

Não lê ou escreve preços, votos, Karma, histórico ou eventos. Após `validarConfirmacaoOferta` conferir posto/código/disponível/origem, `onAtualizar` chama `recarregar` do contexto. As barrinhas continuam `selecionados ∩ ofertas confirmadas`. Não foram confirmados produtos no Maxi automaticamente.

## Preço, histórico e evento

`POST /precos` e o alias `/postos/<id>/precos` usam `registrar_preco_validado`. A validação existente trata ID, combustível, valor 0,01–25,00 com duas casas, foto opcional, GPS e intervalo de contribuição. A alteração anterior acrescentou o lock do posto e a integração transacional:

1. Lock do usuário autor (`usuarios FOR UPDATE`), depois do posto (`postos FOR UPDATE`).
2. Validação geográfica e intervalo; consulta do último preço do mesmo posto/produto, por data e ID decrescentes.
3. Insert em `registos_preco` com score inicial 1 e data do histórico no fuso de sessão -03:00.
4. `registrar_karma` verifica origem `preco:<id>`, soma +5 no usuário, lê saldo e insere `historico_karma` com data UTC.
5. Insert em `eventos_preco`, PK `registo_id`, guardando o preço anterior e data UTC.
6. Um commit confirma preço, saldo, histórico e evento. Qualquer exceção antes dele reverte o conjunto.

A restrição única `(usuario_id,origem)` do histórico protege reprocessamento de um evento de pontos. Ela não transforma o cadastro de preço em uma API com chave de idempotência: após perda da resposta, deve-se conferir atividade antes de reenviar. O intervalo de 15 minutos protege o cadastro normal; os testes que precisam vários preços desativam esse intervalo somente por patch no processo de teste.

201 retorna IDs, Karma e distância verificada. Erros de cadastro não comprovam escrita parcial; resposta perdida depois do commit deixa um resultado incerto para o cliente. A fila ainda não foi processada nessa transação: seu evento fica pendente para o executor separado.

## Votos: fluxo, tipos e invariantes

`lerCatalogo` preserva o `registo_id` do combustível. `DetalhesPostoConsulta` só monta `VotarPreco` quando há preço e ID. Backend antigo sem ID mantém leitura do valor, mas não oferece avaliação; não se deduz ID pelo posto ou combustível.

`ControlesVoto.consultar` faz GET apenas ao clicar em consultar; o componente não consulta por montagem/cartão. POST usa o mesmo ID exibido. `lerAvaliacao` exige este contrato:

```typescript
type Voto = "positivo" | "negativo";
interface AvaliacaoPreco {
  registo_id: number;
  confianca_score: number;
  positivos: number;
  negativos: number;
  meu_voto: Voto | null;
  pode_votar: boolean;
}
```

```text
GET /precos/456/votos   (Bearer)
POST /precos/456/votar  (Bearer)  { "voto": "positivo" }

200 { "registo_id": 456, "confianca_score": 2, "positivos": 1,
      "negativos": 0, "meu_voto": "positivo", "pode_votar": true }
```

O GET não expõe o ID da conta autora. Contagens pertencem ao registro exato e incluem só votos persistidos; o score inicial 1 não conta como confirmação externa. A interface explica isso. Sem limiares de validado/contestado nem moderação automática. A política de Karma já existente foi preservada: novo voto ±1 no score e ±2 no Karma do autor; troca ±2 no score e ±4 no Karma; repetição não altera nada.

Na escrita: consulta inicial identifica autor; `rollback` descarta seu snapshot antes de aguardar locks. Em seguida, lock da conta autora, do registro, e da linha de voto da conta. O registro é rechecado porque pode ser excluído durante a espera. A restrição única de conta/registro impede duplicatas. Insert ou troca altera voto e score; o histórico usa origem `voto:<id-do-voto>:<sequencia>`, calculada sob lock do autor. A mesma transação registra Karma/saldo/histórico. `resumo` devolve estado confirmado, e commit libera tudo. Repetição retorna resumo sem novo histórico. Falha reverte voto, score e Karma juntos.

400: JSON/voto inválido ou voto próprio; 401: sessão recusada; 404: registro ausente; 503: falha operacional. SQL/segredos não são retornados ao cliente. Um novo preço tem outro ID e começa sem votos; os anteriores continuam ligados ao preço anterior, mesmo que ele já não seja o atual do catálogo.

## Fila: seleção, tempo e retomada

`processar_alertas.main` exige `--banco`, confere `SELECT DATABASE()` e limite 1–1000 antes de chamar `processar_pendentes`. Não escolhe destino online, agenda execução nem faz push. Cada evento é uma transação separada.

`processar_pendentes` seleciona o evento pendente de menor `registo_id`, com join do preço e `FOR UPDATE`. Consulta assinantes por `preferencias_alertas` + `favoritos_postos` + `favoritos_combustiveis`, todos do mesmo usuário, posto e produto; usa preferências existentes **no momento de processamento**. Os assinantes são ordenados por usuário e bloqueados pela consulta. Combustível desconhecido interrompe com rollback para revisão, em vez de descartar silenciosamente.

Somente quedas exige preço anterior conhecido e valor novo estritamente menor. Sem essa opção, um primeiro preço também pode avisar. O intervalo é por usuário/posto/produto e compara a data de criação do aviso com `UTC_TIMESTAMP() - INTERVAL ... MINUTE`, usando o tempo do processamento. Quando há aviso recente, o novo aviso é suprimido; o evento não fica esperando para ser enviado depois. Eventos sem assinantes elegíveis também são marcados processados.

Cada insert em `notificacoes` está protegido por única `(usuario_id,registo_id)` e upsert sem duplicação. Depois de todos os assinantes, `processado_em` recebe UTC e ocorre commit. Falha antes do commit reverte avisos e marcação juntos; o evento permanece pendente. Perda de comunicação depois do commit não desfaz o evento. Um novo executor pode continuar; dois executores disputam os mesmos locks, e a integração verificou a ausência de duplicação nesse cenário. Não há `SKIP LOCKED`, cron, push ou mecanismo de retentativa contínua dentro dessa função.

## Revisão própria de locks e limites

| Escritor | Ordem relevante no código atual |
| --- | --- |
| Cadastro | Conta autora → posto → novo registro/histórico/evento. |
| Voto | Conta autora → registro → voto; insert/FKs também envolvem a conta votante. |
| Oferta | Posto → relação de oferta; FK de auditoria envolve a conta confirmante. |
| Exclusão de conta | Conta → desvinculação da auditoria de ofertas → delete/cascatas de preços/votos/históricos/eventos/avisos. |
| Preferências/favoritos | Conta → relações pessoais e preferências. |
| Fila | Evento/preço via join → preferências/favoritos dos assinantes → avisos e suas FKs. |

Não há uma ordem global única de todos os locks entre todos esses escritores. As FKs adquirem locks adicionais. Portanto, os testes aprovados para operações iguais não provam inexistência de deadlock em voto cruzado, oferta/exclusão ou fila/exclusão simultâneos. Uma transação escolhida como vítima deve ser revertida; as rotas retornam erro e a fila mantém o evento pendente para outra rodada. Essa é uma limitação da revisão atual, não um novo defeito reproduzido nesta rodada. Não houve alteração especulativa de lock, retentativa automática ou moderação.

`registrar_karma` pressupõe que o chamador detenha o lock da conta; não deve ser reutilizado fora dessa condição. A exclusão de conta preserva a oferta manual mas remove o vínculo de autoria da auditoria; os preços pessoais seguem as cascatas existentes. Reversão de código não restitui dados apagados por uma exclusão já confirmada.

## Estados de UI e sessão

Os componentes são isolados pela sessão usando `key`, e a avaliação é montada com a chave do ID do preço. `useRef` impede duplo envio durante a requisição; estados `busy`/`disabled` bloqueiam os botões. Cleanup invalida a sessão capturada; respostas após desmontagem/troca de conta não atualizam o controle. Essas proteções existem no código, mas não foram homologadas visualmente nesta rodada.

Oferta tem revisão e cancelamento antes do envio. O cancelamento fica bloqueado durante a confirmação; sair da tela só ignora a resposta e **não** garante cancelar uma gravação que já chegou ao servidor. A oferta só atualiza o catálogo após contrato válido. Em erro HTTP, pode exibir a mensagem do servidor; falha local de GPS mostra a mensagem respectiva. Falha de transporte pode expor a mensagem do cliente HTTP e não representa confirmação de sucesso.

Voto consulta antes de liberar ações. Autor recebe aviso e não pode votar; backend também recusa. Em rede/resposta inválida, o estado é limpo e o controle solicita consultar antes de repetir; não há reenvio automático. Visitante só abre login. Resposta perdida após commit pode significar que o voto foi gravado; GET é o caminho para reconciliar. Votar de novo com o mesmo valor não duplica pontuação.

## Consultas/requisições e desempenho

Catálogo continua com três consultas em lote: postos, relações de oferta e preços atuais. Não há requisição de avaliação por cartão/tecla. Consulta de avaliação: uma requisição GET, uma consulta do decorator e duas SELECTs na operação (autor e agregado). Escrita de voto: uma requisição POST; mais consultas/locks/history conforme novo voto, troca ou repetição. Oferta: uma requisição POST depois do GPS, mais recarga do catálogo; duas SELECTs e até um upsert na operação, além do decorator. A fila tem consultas proporcionais aos assinantes elegíveis; não é um envio push em lote.

PK/índices existentes sustentam relação posto/produto, votos únicos, histórico por origem e avisos únicos. A fila não ganhou índice específico de pendência nesta rodada; o crescimento pode exigir medição/plano próprio. Não se mediu tempo, RAM ou consultas sob carga. A escolha de não consultar por cartão reduz chamadas previstas no fluxo, mas não foi apresentada como benchmark.

## Evidências por risco

| Risco | Cenário/assertiva em `IntegracaoParticipacao` |
| --- | --- |
| Oferta duplica auditoria ou muda preço | `test_oferta_idempotente_nao_altera_preco_karma`: compara linhas antes/depois e saldo. |
| Negativa/OSM sobrescritos | `test_oferta_preserva_negativa_e_origem_osm`: 409 e origem OSM sem manual artificial. |
| GPS/autenticação ignorados | `test_oferta_validacoes_e_autenticacao`: recusas e nenhuma relação gravada. |
| Oferta simultânea duplica | `test_oferta_concorrente_preserva_uma_auditoria`: duas confirmações, uma relação/auditoria. |
| Preço/Karma parcial | `test_preco_grava_evento_e_historico_atomicos`: falha injetada não deixa preço extra. |
| Voto repete/troca pontuação errada | `test_voto_proprio_repeticao_troca_e_retorno`: score, saldo, histórico e voto próprio. |
| Concorrência duplica voto | `test_votos_concorrentes_mesma_conta_e_duas_contas`, `test_trocas_concorrentes_mesma_conta_mantem_saldo`. |
| Falha deixa voto/score parcial | `test_voto_falha_reverte_pontos_score_e_voto`: rollback de todas as tabelas envolvidas. |
| ID de novo preço herda votos | `test_novo_preco_nao_herda_avaliacoes`: novo ID sem avaliações, anterior preservado. |
| Fila avisa conta/produto errado ou duplica | `test_fila_favoritos_quedas_idempotencia_e_concorrencia`: favoritos corretos, intervalo e leitura por conta. |
| Fila perde evento na falha | `test_fila_recupera_falha_sem_aviso_parcial`: rollback, pendência e uma notificação na retomada. |
| Exclusão deixa relações indevidas | `test_conta_nome_favoritos_preferencias_e_exclusao`: revoga sessão, cascatas e oferta preservada sem autor. |

As quatro migrações são aplicadas ao schema vazio descartável por `setUpClass`; não se editam SQLs aplicados nem dados do responsável. O simulador antigo 001/002 continua cobrindo checksum, alvo, DDL parcial, disputa de migração e metadata numérica. Ele não cobre 003/004 em memória; essa parte é exercitada na integração MySQL. Não há teste real TiDB/Overpass/Gemini/Dropbox neste conjunto.

## Roteiro manual ainda não executado

1. Conferir API alcançável no celular e distinguir Expo Go de navegador. Usar raio normal no processo de homologação presencial e local/contas de teste identificados.
2. Visitante: abrir detalhes, caminho para login, retorno. Autenticado: consultar avaliações, foco/teclado, área de toque, tema/contraste e botões ocupados.
3. Confirmar somente oferta observada; conferir produto, API, filtro e barrinha. Exercitar negativa e GPS recusado sem gravação fictícia.
4. Conta autora cadastra preço; outra conta confirma, repete e troca. Conferir ID, saldo, histórico e novo preço sem votos herdados.
5. Sair/trocar conta com requisição em andamento; verificar ausência de estado de outra sessão. Em falha de rede, consultar antes de repetir.
6. Processar fila somente no destino revisto e conferir central/preferências/intervalo. Não confundir falta de executor com falha de push.

Sem aparelho acessível e com a interrupção da ferramenta no Firefox, nenhuma dessas etapas é declarada concluída por testes sintéticos.
