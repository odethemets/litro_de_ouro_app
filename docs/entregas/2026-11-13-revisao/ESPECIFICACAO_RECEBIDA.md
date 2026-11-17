# Litro de Ouro — continuidade revisada e especificação das entregas

**Revisão:** 13/11/2026, America/Fortaleza.  
**Destino:** Codex local em `C:\litro_de_ouro`, como assistente técnico principal; apoio consultivo deste chat quando solicitado.

Este documento consolida o relatório fornecido pelo Codex local, analisa os avanços e organiza a próxima execução. A seção 1 preserva seu relato, com apenas o nível dos títulos adaptado. Os testes ali descritos foram informados pela sessão local; não foram reexecutados nesta revisão documental. As seções seguintes são a análise e as especificações para as próximas entregas.

O estado atual do disco e as instruções mais recentes do responsável prevalecem sobre históricos. Este documento não amplia a autorização para publicação, operações destrutivas sobre dados reais ou redefinição unilateral das regras de produto. O relatório anterior permanece como referência de arquitetura e decisões; os bloqueios locais resolvidos deixam de ser pendências.

## 1. Relatório local recebido — estado e evidências informados

Atualizado em **13/11/2026**, referência America/Fortaleza. Esta atualização descreve o disco e os testes executados nesta sessão. O [relatório recebido](docs/RELATORIO_RECEBIDO_2026-11-13.md) permanece como histórico; divergências são resolvidas pelas evidências abaixo.

### Estado confirmado

- Projeto `C:\litro_de_ouro`, branch `main`, HEAD `0ec3c78`, com muitas alterações e arquivos não rastreados anteriores à sessão. Foram preservados; não houve commit, reset, publicação ou deploy.
- Compose principal e override já estavam corrigidos. Há uma publicação do backend `5001:5000` e banco restrito a `127.0.0.1:3307`. Nenhuma alteração nesses arquivos foi necessária.
- Containers db e backend saudáveis. Verificador confirmou TLS, API, listagem, login da conta fictícia e perfil.
- Banco local `litro_de_ouro_dev`, MySQL 8.4.13: **59 postos, 1 usuário, 11 registros de preço, 0 votos**, conforme verificador nesta sessão. As contas e contribuições de teste novas foram criadas em outro banco.
- Migrações 001–004 aplicadas e checksums aceitos pelo dry-run. Nenhuma migração foi aplicada ao banco do responsável nesta sessão.
- API pública do frontend configurada em `http://192.168.1.9:5001`; ipconfig mostrou esse endereço e também `192.168.1.8` em outra interface. Não foi testado o alcance pelo celular.
- Override de desenvolvimento continua com **raio de 50 km**. Os testes de integração usaram processo separado com raio de 500 m e coordenadas sintéticas; não homologam presença física.

### Diferenças encontradas e integração feita

Busca por nome no Feed, telas do assistente, Karma/ranking e reexportação do mapa legado já existiam. Não foram reaplicados. Havia ainda uma cópia de `lista-postos-consulta.tsx` em `services`; foi preservada. A tela importa a versão de `components`.

Faltavam confirmação de oferta, serviço de eventos/avisos e processamento da fila. A votação antiga não tinha interface e podia disputar atualizações concorrentes; o preço somava pontos sem alimentar o histórico detalhado ou a fila.

| Arquivos alterados/adicionados nesta sessão | Resultado |
| --- | --- |
| `back_end/app/__init__.py` | Registra os blueprints de ofertas e votos junto aos anteriores. |
| `back_end/app/rotas/ofertas.py` | POST de confirmação explícita, autenticado, com GPS/proximidade; modifica somente oferta desconhecida. Negativa efetiva retorna 409; confirmação existente preserva origem/auditoria. Sem preço, Karma ou aviso adicional. |
| `back_end/app/rotas/votos.py` | GET `/precos/<id>/votos` e POST `/precos/<id>/votar`; registro exato, contagens, score, voto da conta e permissão de votar. Serializa por autor/registro; repetição não pontua; troca ajusta score/Karma/histórico. |
| `back_end/app/rotas/precos.py` | Remove implementação antiga de votos, agora no blueprint próprio. Grava preço, +5 pontos, histórico e evento na mesma transação. Lock do posto serializa o preço anterior usado nos avisos. |
| `back_end/services/catalogo_postos.py` | Retorna `registo_id` do preço de cada produto. Mantém consulta em lote, referência, disponibilidade e autoria existentes. |
| `back_end/services/atividade_alertas.py` | Histórico de pontos e processamento transacional de eventos. Respeita posto e produto favoritos, adesão, somente quedas e intervalo por posto/produto. Eventos e avisos confirmados juntos, sem duplicação ao repetir. |
| `back_end/scripts/processar_alertas.py` | Rodada manual limitada, com nome explícito do banco. Não instala agendamento nem envia push. |
| `back_end/scripts/testar_offline.py` | Executa as sete suítes em processos separados; testes legados de IA substituem módulos globais e não podem compartilhar o processo com outras suítes. Usa raio normal nos testes. |
| `back_end/tests/test_infra_banco.py`, `test_transferencia_tidb.py` | Delimita o simulador antigo às migrações 001/002 que ele realmente modela. As quatro migrações foram testadas em MySQL real no banco descartável. |
| `back_end/tests/integracao_participacao.py` | Treze cenários com schema completo, autenticação, transações, concorrência, favoritos, avisos e exclusão de conta sintética. Recusa banco de desenvolvimento, destino divergente ou schema não vazio. |
| `front_end/src/services/catalogoPostos.ts` | Preserva o ID específico do preço no contrato. Backend anterior sem ID continua legível, com avaliação indisponível nesse caso. |
| `front_end/src/services/ofertas.ts`, `votos.ts` | Valida GPS/payload de oferta, confirmação do mesmo posto/produto e resposta de avaliação do registro exato. |
| `front_end/src/components/confirmar-oferta.tsx` | Confirmação revisável e explícita antes de obter GPS; captura a sessão e ignora resposta após saída/troca de conta. |
| `front_end/src/components/votar-preco.tsx` | Consulta avaliações por ação do usuário, sem requisição automática por cartão. Exibe contagens e permite confirmar/contestar; bloqueia autor. Dados são isolados por sessão/registro. |
| `front_end/src/screens/ConsultaPostos/detalhes.tsx`, `index.tsx` | Integra os controles e recarrega catálogo após confirmação de oferta. |
| `front_end/tests/participacao.test.cjs` | Oito novos testes de contrato/GPS/avaliações. |

### Política de votos efetivamente implementada

Mantida a regra existente: preço começa com score 1 e concede +5 Karma ao autor. Novo voto positivo/negativo altera score em +1/-1 e Karma do autor em +2/-2. Trocar voto altera score em +2/-2 e Karma em +4/-4. Repetir o mesmo voto não altera pontuação nem cria evento de histórico. Voto próprio é recusado; conta e registro precisam existir.

Não foi definido limiar de validado/contestado, remoção automática, prioridade no catálogo ou moderação. A interface informa que o score inicial não é confirmação comunitária. O catálogo continua escolhendo o último preço por produto. Essa política de moderação permanece uma decisão aberta do responsável.

Oferta, preço e voto continuam separados. O Maxi Posto não teve sua disponibilidade confirmada automaticamente; a ação depende da observação do usuário no local. Registros antigos não receberam eventos ou histórico inventados. O saldo anterior permanece o saldo registrado na migração.

### Verificações executadas

| Verificação | Resultado e limite |
| --- | --- |
| Compose efetivo, containers, healthcheck e verificador local | Aprovados; TLS, listagem, login fictício e perfil. Não valida e-mail, celular ou provedores. |
| Dry-run das migrações no banco local | 001–004 aplicadas, sem divergência. Nenhum DDL executado nesse destino pela sessão. |
| Rotas do processo Flask | POST de ofertas, POST de votos e novo GET de avaliações presentes, além das rotas anteriores. |
| TypeScript `tsc --noEmit` e `npm run lint` | Aprovados. |
| Frontend `node --test tests/*.test.cjs` | **82 testes aprovados**: 74 existentes e oito novos. |
| Exportação Expo Web | Aprovada, gerada localmente em `front_end/dist`. Não publicada e não representa teste visual ou nativo. |
| Backend `python -B scripts/testar_offline.py` | Sete suítes aprovadas: **128 casos unittest**, mais scripts de assertivas de geofence e IA. SDK, Dropbox e fonte OSM simulados. Não somar assertivas desses scripts como casos unittest. |
| MySQL/TLS descartável | **13 cenários aprovados**. Inclui schema 001–004, GPS/negativas, auditoria idempotente, concorrência em oferta, repetição/troca de votos, duas contas votantes, voto próprio, rollback de preço/voto, recuperação da fila, intervalo, acesso aos avisos, nome/favoritos/preferências/exclusão. |
| `git diff --check` | Aprovado; avisos de conversão LF/CRLF do repositório não são falhas de conteúdo. |

O banco `ldo_validacao_20261113_01` foi criado explicitamente para os testes e removido ao fim, com revogação do grant temporário. Não houve limpeza dos dados do responsável. Os erros simulados de preço/voto aparecem nos logs dos testes para verificar rollback; os respectivos cenários terminaram aprovados.

### Operação e próximos passos

Para testes offline do backend:

```powershell
docker compose -f compose.yaml -f docker/compose.testes-precos.yaml --env-file docker/local/.env exec -T backend python -B scripts/testar_offline.py
```

Para uma rodada manual de avisos internos no banco local, após revisar o destino:

```powershell
docker compose -f compose.yaml -f docker/compose.testes-precos.yaml --env-file docker/local/.env exec -T backend python -B scripts/processar_alertas.py --banco litro_de_ouro_dev --limite 100
```

O segundo comando **não foi executado sobre os dados do responsável nesta sessão**. Novos preços geram eventos pendentes; a entrega de avisos depende de executar a fila. Não existe agendador instalado por esta entrega. Preferências são avaliadas ao processar o evento; o intervalo usa a data de criação do aviso na central. Não há push.

Para repetir a integração, provisionar novamente um banco vazio com o nome exigido pelo script e permissão temporária para o usuário local. Executar com `DB_NAME=ldo_validacao_20261113_01` e `GEOFENCE_RAIO_M=500` no processo de teste; remover somente esse banco ao final. Não apontar o script ao banco do projeto.

Pendências que exigem ambiente/decisões adicionais:

1. Validar os novos controles visualmente e em aparelho físico: confirmação observada, GPS real, alcance da API, teclado, acessibilidade, sessão e troca de conta. Homologar cadastro presencial usando raio normal, sem o override de 50 km.
2. Definir critérios de confiança/moderação e realizar validação de produto com duas contas humanas. Testes sintéticos não homologam observação real do preço.
3. Homologar e-mail real, recuperação/troca de endereço e descarte em serviços externos/backups. Nome/favoritos/exclusão foram testados apenas com contas descartáveis locais.
4. Escolher e configurar executor periódico da fila; implementar transporte push conforme plataformas escolhidas.
5. Homologar Gemini, voz, foto, Mapbox/Dropbox e custo por rota. Foi encontrada outra diferença: o código importa `google.genai`, enquanto `requirements.txt` ainda declara `google-generativeai`; revisar e instalar o SDK compatível antes da integração real. Nenhuma dependência ou credencial de provedor foi alterada nesta sessão.
6. Identificar destinos TiDB/Render/Vercel, validar TLS/CORS/segredos/backup e piloto. Não houve acesso/configuração desses destinos ou autorização nova de deploy.
7. Revisar executor OSM e primeira execução controlada antes de escrita recorrente. Nada foi agendado.
8. Completar identificação do controlador, retenção, direitos e política de privacidade antes da abertura pública. Não há certificação de conformidade.

Os blocos locais de infraestrutura e integração avançaram; os blocos de homologação física, provedores, online e privacidade permanecem abertos. Nenhuma ausência de erro foi usada como confirmação desses fluxos.

## 2. Análise desta revisão

Esta análise foi feita sobre o relatório local fornecido pelo responsável, sem acesso ao checkout atual do Windows ou aos diffs produzidos nessa sessão. As conclusões sobre execução são atribuídas ao relatório; não representam repetição independente dos testes ou auditoria linha a linha do código. O novo anexo tem o mesmo conteúdo do relatório local anteriormente enviado.

### Avanços que substituem pendências do histórico

- **Infraestrutura local:** a duplicação de portas foi corrigida e os serviços estão saudáveis, conforme a verificação local. Não reaplicar a correção antiga por suposição.
- **Migrações:** 001–004 estão aplicadas e os checksums foram aceitos. Uma nova mudança de estrutura exige migração própria; não repetir ou editar as já aplicadas.
- **Oferta:** o controle foi integrado aos detalhes e mantém confirmação explícita, autenticação, proximidade, negativas e auditoria. O Maxi Posto não foi preenchido por dedução dos preços antigos.
- **Votos:** agora há interface e GET de avaliações, além do POST. O contrato leva o ID do registro de preço; a serialização e a repetição/troca foram exercitadas no banco descartável. A ausência de botões deixou de ser a pendência descrita no relatório histórico.
- **Transações e avisos:** preço, pontos, histórico e evento foram integrados; a fila transacional foi adicionada e testada. Isso encerra a lacuna de integração local descrita, mas não instala agendamento ou push.
- **Preservação da base:** a sessão manteve dados e alterações anteriores, usou banco separado para integração e não publicou serviços. A busca no Feed e outras telas já existentes foram reconhecidas e preservadas.

### Pontos que permanecem abertos

1. **Homologação visual e física:** exportar web, passar TypeScript e simular GPS não prova que o botão correto, o retorno, o foco, o teclado e a sessão funcionam no aparelho. O alcance pelo celular não foi testado nessa sessão; há dois IPs em interfaces distintas. O raio de desenvolvimento de 50 km continua ativo.
2. **Confiança por votos:** avaliações estão integradas, mas não existe política de validado/contestado ou moderação. O catálogo ainda usa o último registro. O score inicial de 1 continua sem representar um voto externo; testes aprovados não definem essa política de produto.
3. **Fila operacional:** novos eventos dependem de execução da fila. Não há agendador nem push. As preferências são consideradas no processamento e o intervalo na criação do aviso; esses comportamentos temporais precisam ser conhecidos e homologados.
4. **SDK de IA:** `google.genai` e `google-generativeai` não são o mesmo contrato de importação. Revisar a dependência efetiva no Docker e no venv, compatibilidade e versão antes da chamada real. Testes com SDK simulado ou imagem com pacotes antigos podem ocultar a diferença. Isso é prioridade do bloco de IA, não requisito para consultar postos ou testar votos.
5. **Cobertura dos testes:** 128 casos em suítes isoladas e 13 cenários de integração são evidências úteis. Os simuladores limitados a 001/002 precisam ter seu escopo explicado e cobertura complementar preservada; não comparar totais antigos/atuais como se todos medissem o mesmo conjunto.
6. **Dados e implantação:** a contagem local é 59 postos, um usuário, 11 preços e zero votos nessa verificação. Os testes descartáveis não mudam essa contagem nem comprovam votação por pessoas no app. TiDB, hospedagem, provedores e privacidade continuam sem homologação integrada.

### O que deve ser revisado no código, quando o diff estiver disponível

Conferir a ordem de locks entre preço, voto e exclusão; unidade de transação da fila; restrições únicas usadas para idempotência; associação do voto ao registro exato; conservação do saldo/histórico ao trocar voto; filtragem por conta; e tratamento de resposta perdida ou recebida após troca de sessão. Estes são pontos de revisão, não falhas adicionais comprovadas pelo relatório.

O HEAD `0ec3c78` sozinho não identifica a versão executada: havia alterações e arquivos não rastreados. Um `git diff` relativo ao HEAD pode misturar sessões e omitir arquivos novos. A documentação de cada bloco precisa incluir a diferença incremental e a lista de arquivos novos, conforme a especificação adiante.

## 3. Próximos passos, em ordem proposta

| Bloco | Execução pelo Codex local / responsável | Critério de conclusão |
| --- | --- | --- |
| 1 — Conferência e homologação dos controles novos | Preservar o estado atual, registrar o diff incremental e testar oferta/votos visualmente no navegador e no aparelho. Conferir qual IP alcança o celular e a sessão ativa. | Evidência visual e roteiro executado, sem reaplicar correções já presentes. |
| 2 — Oferta, preço e votos com duas contas | Usar conta autora e outra conta controlada; confirmar oferta observada, cadastrar preço, votar, repetir e trocar. Para presença física, usar o raio normal de 500 m no processo escolhido. | Dados/autor/data/registro corretos; voto próprio recusado; sem duplicação de score/Karma; novo preço recebe avaliação do seu próprio ID. |
| Decisão de produto em paralelo | Definir o que significam confiança, contestação, validade temporal, quantidade de avaliações e moderação. | Regras documentadas e aceitas pelo responsável antes de codificar novos limiares ou retirada automática de preços. |
| 3 — Conta e e-mail | Homologar envio real, cadastro/OTP, recuperação, troca de endereço, revogação de sessões e exclusão em conta descartável. | Código recebido em caixa controlada e resultados verificados no aplicativo; limites de exclusão externa documentados. |
| 4 — Operação dos avisos | Conferir CLI atual, destino e uma rodada controlada; testar preferências, somente quedas, intervalo e retomada. Depois escolher executor periódico. | Avisos corretos para posto e combustível favoritos, sem duplicação. Agendamento e push têm evidências próprias. |
| 5 — SDK e integrações de IA | Alinhar dependências/imports e validar instalação reproduzível. Depois homologar modelo/quota, texto/voz/foto, Mapbox, Dropbox e custo por unidade. | SDK importável no runtime real, falhas tratadas e chamadas reais aprovadas para o recurso específico. |
| 6 — Preparação online, em bloco separado | Identificar TiDB, Render e Vercel, ambiente de testes, migrações, dados a carregar, HTTPS/TLS/CORS/segredos/saúde e backup. | Piloto integrado comprovado; publicação depende de instrução expressa, não deste documento. |
| 7 — Automação OSM | Revisar executor, consulta, limites, preservação de dados manuais e concorrência; começar com prévia e execução controlada. | Primeira execução real com relatório e repetição sem duplicar; só então habilitar a periodicidade acordada. |
| 8 — Privacidade e revisão pré-abertura | Concluir controlador, finalidades, retenção, atendimento, arquivos/backups e validações de uso. | Aviso e operação correspondem ao comportamento real antes da abertura pública; sem alegar certificação automática de conformidade. |

Os blocos podem ter preparação paralela, mas nenhuma entrega deve trocar a base local por uma dependência online ainda não configurada. O passo imediato recomendado é homologar o que foi integrado, corrigindo apenas regressões comprovadas, enquanto as decisões de moderação são alinhadas com o responsável.

Se o cadastro/OTP impedir a criação da segunda conta controlada, antecipar a homologação de e-mail do bloco 3. Não contornar a verificação no ambiente de produção para declarar concluído esse teste. Conta sintética provisionada em banco dedicado continua sendo evidência de teste, não homologação do envio real de e-mail.

### Roteiro mínimo da homologação funcional

- Acessar a API pelo celular na rede correta e diferenciar Expo Go de navegador mobile. GPS/microfone web podem exigir HTTPS; uma página que abre por HTTP não comprova essas permissões.
- Verificar visitante e usuário autenticado; reabertura, saída e troca de conta não podem reutilizar avaliação ou ação de outra sessão.
- No posto escolhido, confirmar somente a oferta observada e conferir o produto na API, no filtro e na barrinha. Repetir não deve gerar pontos ou alterar a auditoria original.
- Conferir negativos explícitos, GPS negado/impreciso/fora do raio e falha de rede sem confirmação falsa. Manter dados de teste identificados e evitar contribuições artificiais em locais reais.
- Com duas contas controladas, conferir o ID exato do preço e voto próprio/repetido/trocado. Publicar um novo preço deve manter os votos ligados ao registro anterior, sem transferi-los silenciosamente.
- Registrar um preço e conferir autor, data, unidade, atividade, saldo e evento. Processar a fila conscientemente para validar o aviso; aguardar sem executor não é teste de falha do transporte.
- Validar teclado, foco, toque, retorno, contraste, tema e leitura dos controles. Se uma etapa não for realizada, registrar “não executada”, sem convertê-la em sucesso por teste de build.

## 4. Diretrizes preservadas para o Codex local

1. O disco atual e a instrução mais recente do responsável prevalecem sobre entregas históricas. Examinar `AGENTS.md` aplicáveis e diffs; preservar arquivos anteriores, inclusive não rastreados. Não fazer reset/limpeza/stash das alterações do responsável para facilitar a sessão.
2. Não reaplicar busca, telas, Compose ou migrações já presentes. Não editar SQL aplicado para alterar checksum. Não fazer commit, publicação, deploy ou agendamento por iniciativa deste relatório.
3. Preferir código em arquivos de até 500 linhas, com flexibilidade justificada. Separar responsabilidades sem minificar. Otimizar chamadas, memória e dependências com evidência; não prometer economia por contagem de linhas.
4. Oferta, preço e voto são fatos distintos. Preservar desconhecidos e negativas, origem/auditoria, referência única e unidades. Barrinhas representam selecionados ∩ ofertas confirmadas; as cores dos números indicam faixa de preço, com confiança apresentada separadamente.
5. Preservar sessão real e isolamento por API/conta. Não criar token, localização, preço, voto ou evento de Karma fictício para completar a interface. Backend valida as regras mesmo com validação no frontend.
6. Manter UI acessível, feedback visível, uso com uma mão, teclado e retorno coerentes; evitar requisições automáticas por cartão e nova consulta por letra quando a lista carregada permite busca local.
7. Usar banco descartável para testes de integração destrutivos e documentar destino/isolamento. Não copiar as credenciais de laboratório ou desabilitar TLS para corrigir conexão real.
8. Segredos ficam fora dos relatórios e do frontend público. Informar nomes/presença das variáveis, não seus valores. Evidências compartilhadas devem omitir tokens, códigos de e-mail, dados pessoais e localização pessoal desnecessária.
9. Preferência de entrega: código no repositório local com alterações identificáveis; quando precisar transferir código, usar chat/arquivos individuais, sem ZIPs. Explicar o que foi editado e como foi verificado.
10. Registrar decisões técnicas finais e justificativas verificáveis. Dimensionar o relato à mudança: correções pequenas podem ser curtas; contratos, transações e concorrência exigem detalhe proporcional.

### 4.1 Papel do Codex local no projeto

**O Codex local assume a função de assistente técnico principal do Litro de Ouro.** Ele acumula a construção dos códigos com as funções de análise, arquitetura, planejamento técnico, revisão, testes, diagnóstico e documentação anteriormente exercidas pelo assistente deste chat. Deve acompanhar o projeto de ponta a ponta dentro do escopo autorizado, mantendo a continuidade e o estado real das entregas.

| Participante | Responsabilidade |
| --- | --- |
| Responsável pelo projeto | Define objetivos, prioridades de produto, regras de negócio e critérios de aceitação; resolve decisões como moderação por votos e escopo do piloto; mantém a decisão sobre publicação e serviços externos. |
| Codex local | Analisa o repositório e os problemas, propõe a sequência técnica, implementa, revisa o diff, executa as verificações, registra evidências e atualiza a documentação. Aponta riscos e limites sem esperar que cada detalhe técnico seja decidido pelo responsável. |
| Assistente deste chat | Apoio consultivo e segunda análise quando o responsável trouxer relatórios/diffs. Não é uma etapa obrigatória de aprovação de cada mudança local. |
| Gemini e demais colaboradores, quando envolvidos | Apoio de design, propostas e colaboração. As sugestões devem ser confrontadas com os requisitos aceitos e com os contratos reais antes da integração. |

O Codex local deve conduzir o seguinte ciclo de trabalho:

1. **Analisar:** conferir código, configuração e evidências atuais; identificar causas e diferenças antes de reaplicar soluções históricas.
2. **Planejar:** dividir o objetivo em incrementos concretos, indicar dependências e critérios de conclusão, e priorizar bloqueios reais.
3. **Construir:** implementar as alterações necessárias no repositório, preservando regras, dados, contratos e mudanças anteriores.
4. **Revisar:** examinar o próprio diff, as regras, autorização, concorrência, falhas, compatibilidade e impacto em memória/requisições.
5. **Validar:** executar os testes pertinentes e distinguir laboratório, mocks, runtime real e homologação no aparelho; corrigir falhas comprovadas.
6. **Documentar e coordenar:** explicar a construção conforme a seção 5, atualizar pendências e evidências, apresentar o resultado e indicar o próximo passo.

Dentro do escopo já autorizado, deve avançar autonomamente nas leituras, edições reversíveis, diagnósticos e testes adequados, sem pedir confirmação a cada arquivo ou decisão técnica rotineira. Quando faltar uma decisão de produto que altere o comportamento, identificar o ponto e pedir a definição, continuando o trabalho independente que for possível. Não inventar limiares de votos ou novos compromissos com provedores para contornar essa falta.

Essa transferência de função não amplia por si só a autorização para publicação, implantação, agendamento externo, custos novos ou operações destrutivas sobre dados reais. Preservar as restrições e autorizações expressas do responsável, sem repetir pedidos quando uma ação já estiver autorizada e continuar no mesmo escopo.

Revisão realizada pelo mesmo Codex que implementou deve ser descrita como revisão técnica própria. Só registrar revisão independente quando outro revisor realmente a tiver realizado. O objetivo é autonomia com rastreabilidade, sem atribuir uma garantia de qualidade que os testes ou revisores não forneceram.

## 5. Especificação obrigatória: explicar como o código foi construído

**A cada bloco implementado ou corrigido, o Codex local deve entregar uma explicação técnica junto do código.** O objetivo é permitir revisar a implementação e seus limites, sem depender apenas da afirmação de que “funcionou”. Não basta listar arquivos e número de testes aprovados.

### 5.1 Identificação da entrega e separação do que já existia

Informar data/fuso, objetivo, branch/HEAD de referência, estado anterior relevante e escopo autorizado. Separar mudanças desta sessão de mudanças anteriores preservadas. O mesmo HEAD com árvore suja não é uma identificação suficiente do código alterado.

Antes de editar arquivos relevantes, guardar uma referência segura do conteúdo necessário para produzir o diff incremental, sem copiar segredos. Não criar commit/reset/stash obrigatório para isso. Relatar novos arquivos explicitamente: o diff comum pode não incluí-los enquanto não rastreados.

### 5.2 Comportamento anterior e resultado final

Descrever o gatilho concreto, o comportamento anterior e o novo resultado observável. Exemplo: “ao abrir avaliações do registro X, consultar contagens/voto da sessão atual e permitir uma troca idempotente”. Vincular cada resultado a um critério de aceitação.

Se a mudança for apenas refatoração, dizer qual comportamento foi preservado e qual evidência verifica isso. Alternativas relevantes e tradeoffs devem ser explicados quando influenciam confiabilidade, manutenção, segurança ou desempenho; não narrar cada tentativa de edição.

### 5.3 Arquitetura, arquivos e símbolos

Para cada arquivo alterado/novo, registrar caminho relativo, funções/classes/componentes principais, responsabilidade e motivo da alteração. Explicar de onde vêm os dados e quem controla o estado. Informar se há arquivos acima de 500 linhas e a justificativa ou divisão proposta.

Mostrar o fluxo completo pertinente, por texto ou diagrama simples: **ação na tela → serviço → API → validações → SQL/transação → resposta → atualização do estado/feedback**. Relacionar os símbolos reais, não apenas nomes genéricos de camadas.

### 5.4 Contratos e compatibilidade

Registrar métodos/caminhos da API, autenticação, campos/tipos obrigatórios, respostas e erros relevantes, com exemplos fictícios e sem credenciais. Incluir interfaces TypeScript e ligação dos IDs quando houver alteração de contrato.

Explicar a compatibilidade com versões anteriores. Exemplo: backend sem `registo_id` pode manter leitura do preço, mas deve impedir avaliação indisponível, sem inventar o ID. Não reaproveitar payload de um relatório antigo se o contrato atual tiver mudado.

### 5.5 Regras, transações e concorrência

Indicar quais invariantes precisam permanecer verdadeiras, quais tabelas são lidas/escritas, onde começa/termina a transação e o que é revertido em falha. Se houver locks, documentar sua ordem e a relação com outros escritores, incluindo voto, cadastro e exclusão da conta.

Explicar a proteção de idempotência: chave/restrição, verificação e efeito de repetição/troca, inclusive concorrência. Dizer como saldo, histórico e eventos são mantidos consistentes. Informar se uma falha depois do commit é apenas falha de comunicação/processamento posterior.

Na fila, especificar seleção e ordem dos eventos, unidade de transação, marcação como processado, destino sem assinantes, preferências aplicáveis, cálculo do intervalo, retomada e proteção contra dois executores. Documentar a semântica temporal existente; mudanças nela exigem decisão explícita.

### 5.6 Estados de interface, sessão e falhas

Descrever carregamento, botão ocupado/bloqueado, sucesso confirmado, resposta inválida, falha de rede e resultado incerto. Explicar cancelamento, saída da tela e troca de conta; avaliação deve permanecer vinculada à sessão e ao registro corretos.

Cancelar no cliente não garante desfazer uma gravação que já chegou ao servidor. Documentar o tratamento real de resposta perdida e reenvio. Conferir disponibilidade de ações para visitante, autor da publicação e outro usuário, sem apresentar bloqueio apenas visual como proteção suficiente.

### 5.7 Dependências, configuração e desempenho

Registrar dependências adicionadas/removidas e por quê, versões relevantes e variáveis por nome, defaults e local de configuração. Explicar diferenças entre host/venv/container/build web/nativo. Para o Gemini, comprovar que o SDK instalado corresponde ao import no runtime utilizado, sem exigir uma chamada paga para comprovar só a importação.

Conferir também uma instalação/build limpa com os requisitos declarados: um pacote instalado manualmente em container antigo pode fazer o import funcionar e ainda deixar o projeto irreproduzível. A validação de importação não comprova chave, modelo, quota ou funcionamento do provedor.

Quando a mudança afetar desempenho, informar número de requisições/consultas por ação, chamadas em lote, limites/paginação/cache e índices relevantes. Medir antes/depois quando alegar otimização; se não mediu, apresentar a justificativa como hipótese ou escolha de projeto, não ganho comprovado.

### 5.8 Testes e evidências que possam ser conferidos

Informar comandos realmente executados, diretório/runtime, banco de destino, resultados e artefatos correspondentes. Separar testes unitários, scripts de assertivas, integração real, build, navegador com mocks, teste visual e aparelho físico. Não somar contagens sobrepostas ou afirmar cobertura física por teste sintético.

Para cada risco importante, apontar o cenário que o cobre e a asserção/resultado esperado. Se reduzir ou delimitar um simulador, explicar a cobertura removida e a substituta. Falhas injetadas esperadas devem ser distinguidas de testes que falharam. Registrar “não executado” e motivo quando necessário.

Comandos apenas sugeridos para o responsável devem ficar separados dos executados. Não publicar dumps de `.env`, configuração integral com senhas, tokens ou bancos pessoais como evidência.

### 5.9 Pacote mínimo para revisão e compartilhamento

O pacote documenta a revisão local e permite uma segunda análise neste chat quando o responsável desejar. Sua produção não cria uma dependência de aprovação externa para cada alteração rotineira já autorizada.

- Relatório do bloco em Markdown e lista de arquivos/símbolos alterados, com versão de referência e identificação das mudanças anteriores preservadas.
- **Diff incremental completo da sessão**, incluindo novos arquivos, ou arquivos relevantes completos quando não for possível produzir um patch confiável. Não enviar somente um diff enorme relativo a um HEAD antigo sem distinguir sua origem.
- Contratos alterados e trechos completos das funções centrais para a regra em revisão, com contexto de chamada. Não usar apenas prints de código.
- Testes acrescentados/ajustados, comando e resumo dos resultados. Capturas de UI quando o bloco for visual, identificando plataforma e se os dados/GPS foram simulados.
- Pendências, riscos, limitações e roteiro manual de validação. Sem ZIP e sem segredos; arquivos individuais são suficientes.

Se um desses itens não se aplicar, registrar isso de forma breve. Alteração de uma linha não exige um relatório extenso; o objetivo é rastreabilidade e possibilidade de revisão, não volume de documentação.

### 5.10 Reversão e fechamento do bloco

Explicar como desfazer apenas a mudança desta sessão, preservando a árvore anterior. Não usar `git reset --hard`, limpeza geral ou exclusão de volumes como roteiro genérico de reversão. Alterações de dados exigem plano próprio; a reversão de código não desfaz automaticamente uma migração ou efeito já confirmado.

Encerrar com arquivos alterados, verificações executadas, limitações reais e próximo passo. Atualizar a continuidade local sem transformar implementação em homologação e sem transformar teste em autorização de deploy.

## 6. Modelo de relatório a ser preenchido pelo Codex local

Salvar um relatório por bloco, por exemplo em `docs/entregas/<data>-<bloco>/RELATORIO_BLOCO.md`, com anexos individuais de diff/testes/evidências. O nome do diretório é organizacional, não uma autorização para criar ou apagar arquivos alheios.

```markdown
# Bloco: <nome e objetivo>
Data/fuso: <data, America/Fortaleza>
Versão de referência: <branch, HEAD e identificação do estado local>
Escopo solicitado: <pedido atendido>
Responsável técnico: Codex local — análise, implementação e revisão própria
Revisão independente: <revisor/evidência, ou não realizada>

## Resultado observável
Antes: <gatilho e comportamento>
Depois: <resultado e critério de aceitação>

## Construção e decisões
<Fluxo tela → serviço → API → regras/SQL → resposta → estado.>
<Justificativas e tradeoffs relevantes.>

## Arquivos e símbolos
| Arquivo | Funções/componentes | Responsabilidade e alteração |
| --- | --- | --- |
| <caminho> | <símbolos> | <mudança desta sessão> |
Alterações anteriores preservadas: <quais/não se aplica>
Arquivos novos e arquivos acima de 500 linhas: <lista/justificativa>

## Contratos e consistência
<Rotas, tipos, exemplos fictícios, auth e erros.>
<Tabelas, transações, locks, idempotência e rollback.>
<Sessão, cancelamento, falhas e resultado incerto na UI.>

## Configuração e desempenho
<Dependências/versões e variáveis por nome, sem valores privados.>
<Consultas/requisições por ação e medições, ou não medido.>

## Verificações executadas
| Comando/cenário | Runtime/destino | Resultado | Real/simulado | Evidência |
| --- | --- | --- | --- | --- |
| <comando> | <diretório/ambiente> | <resultado> | <limite> | <arquivo> |
Não executado: <o que e motivo>
Cobertura ajustada: <o que mudou e compensação, ou não se aplica>

## Revisão e reversão
Diff incremental: <arquivo e base, incluindo arquivos novos>
Funções centrais/testes: <anexos ou caminhos com contexto>
Reversão restrita à sessão: <procedimento e limites>
Riscos e decisões abertas: <lista>

## Próximo passo
<Ação, responsável e evidência necessária para encerrar.>
Publicação/agendamento: <não realizado ou autorização e evidência específicas>
```

## 7. Primeiro retorno solicitado ao Codex local

Como assistente técnico principal, conduzir a análise e a execução do próximo ciclo no ambiente local. Compartilhar o relatório/diff com este chat quando o responsável solicitar apoio; não aguardar uma aprovação deste chat para continuar trabalho rotineiro autorizado.

O próximo retorno deve trazer o diff incremental e a explicação dos módulos de oferta, votos e eventos/avisos já integrados, com referência às transações e aos cenários de concorrência/rollback. Não é pedido para reescrever esses módulos por estarem na lista.

Em seguida, registrar os resultados da homologação visual e em aparelho; se houver defeito, corrigir o caso comprovado e acrescentar a evidência pertinente. Revisar a discrepância do SDK no bloco de IA. As regras de moderação e os serviços online permanecem decisões/configurações separadas, sem publicação automática.
