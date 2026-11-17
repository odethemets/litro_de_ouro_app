# Bloco IA: busca por texto/voz e diagnóstico do Gemini

## Objetivo e limites

Aplicar os códigos preparados pelo ChatGPT, conferir compatibilidade, testar e devolver relatório/diff/resultados. A funcionalidade de busca já existia. Esta entrega melhora o controle de sessão, cancelamento, revisão e aplicação dos filtros, além de acrescentar um diagnóstico administrativo do provedor.

A IA interpreta filtros; os postos, preços, unidades e disponibilidade continuam vindo do catálogo. A referência continua única, sem substituir automaticamente seu preço por outro produto. Falar preenche o campo: revisar texto → buscar → conferir combustível/referência/bandeira → aplicar no mapa. Mapa e Feed continuam compartilhando o contexto atual.

Reconhecimento direto pelo botão de voz usa a API do navegador quando disponível em contexto seguro. No aplicativo nativo, preservar `services/voz.ts` e o ditado do teclado. Este bloco não instala captura/transcrição de áudio nativa, não habilita voz direta no Expo Go e não inclui leitura de fotos, Dropbox, Mapbox ou cálculo de custo por rota. Esses recursos continuam em sub-blocos separados.

## Fontes e compatibilidade

A base usada foi o snapshot anterior disponível da tela/serviços de IA, não uma nova cópia da árvore Windows. O relatório local informa que essa busca já estava integrada. Os três arquivos de controles de oferta/votos/detalhes da rodada anterior não são modificados.

Antes de aplicar, comparar os três fontes existentes com a base identificada em `evidencias/MANIFESTO.json`. Se houver mudanças locais adicionais, mesclar somente as alterações deste bloco e relatá-las; não sobrescrever funções ou comportamentos novos. O patch é incremental contra essa base disponível, não uma alegação de igualdade com o projeto atual.

Identificação da base usada (SHA-256 dos bytes; diferenças LF/CRLF exigem comparação de conteúdo):

| Arquivo relativo a front_end/src | SHA-256 da base |
| --- | --- |
| screens/Assistente/index.tsx | 1088c7679c3f98f60a480f4f58c70a407e3632e60b2a4b28dff39663c880f882 |
| services/assistente.ts | e4fa11bc5c9c7b0713d47f94d0333f7932d89d5937aaa1992d56b6300861001b |
| services/voz.web.ts | d6dc201b633652ee17f60bd8d535ae8ccb05eb94f241489fbe36b2218e21a032 |

Os três documentos de códigos e estas instruções contêm tudo que precisa ser aplicado; não dependem de outros anexos para reconstruir os oito arquivos. O manifesto e o patch são evidências adicionais opcionais.

Conferir estas interfaces atuais:

- AuthContext: `token`, `status`, `openAuth`; estado autenticado `AUTHENTICATED`.
- FiltrosPostosContext: `filtros`, `usuario`, `aplicar`; filtros compartilhados entre mapa/feed.
- AppButton/AppField/Notice/Page/Surface e CartaoPosto com as props já usadas pela tela anterior.
- POST `/ia/consultar`: corpo mensagem/filtros e coordenadas opcionais; resposta filtros/postos/total/interpretacao/localizacao_usada/mensagem.
- Backend: `app.rotas.ia` expõe MODELO/genai/types; `services.comandos_ia.interpretar_comando`; `app.rotas.assistente._interpretar_ia`; `app.create_app` registra a rota existente.

Não criar outra rota, trocar SDK/modelo, editar requirements, alterar banco, geofence, Compose ou navegação para acomodar diferenças sem antes identificar a incompatibilidade. Adaptações pontuais de compatibilidade devem preservar os contratos e ser descritas no relatório.

## Arquivos

Existentes, com versões completas em `CODIGOS_FRONTEND.md`:

1. front_end/src/screens/Assistente/index.tsx — sessão por chave, cancelamento, revisão da fala, bloqueio de prévia desatualizada e ações de mapa.
2. front_end/src/services/assistente.ts — mantém as validações; copia filtros, valida entrada/GPS e aceita um quinto argumento opcional de token capturado.
3. front_end/src/services/voz.web.ts — limpeza da escuta, orientação quando não houve fala e recusa de transcrição acima do limite sem truncar restrições.

Novos, em `CODIGOS_DIAGNOSTICO.md` e `CODIGOS_TESTES_FRONTEND.md`:

4. back_end/scripts/verificar_assistente.py.
5. back_end/tests/test_verificar_assistente.py.
6. front_end/tests/apoio-assistente.cjs.
7. front_end/tests/assistente-sessao.test.cjs.
8. front_end/tests/voz-revisao.test.cjs.

Sem dependências novas. Todos os arquivos de código têm menos de 500 linhas e mantêm comentários breves sobre responsabilidade/manutenção.

## Como foi construído

O conteúdo autenticado da tela recebe uma chave por sessão. A busca mantém um AbortController por operação e só publica resposta enquanto a tela estiver focada e o pedido ainda for o atual. Cancelar desvincula esse pedido antes do abort. Isso não garante que o servidor interrompeu uma chamada já iniciada.

O resultado guarda um retrato serializado dos filtros e da posição usados. Se esse contexto mudar, a aplicação no mapa fica bloqueada e os cartões da prévia deixam de oferecer ação até uma nova busca. A transcrição apenas edita o texto, sem envio automático, sem coordenadas inventadas e sem gravação de preço.

O quinto argumento de consultarAssistente é opcional para preservar chamadas existentes. A tela passa o token capturado explicitamente. O POST recebe filtros copiados, coordenadas somente quando recebidas e signal/timeout já compatíveis com a API.

O diagnóstico padrão importa módulos, confere SDK/rotas e executa uma interpretação objetiva em memória. Não chama o modelo nem consulta o catálogo. Carrega back_end/.env sem substituir variáveis já definidas no runtime. Valores de chaves e segredos não são impressos.

`--teste-provedor` é uma única chamada opcional com frase sintética, sem usuário real, foto, coordenadas ou consulta ao banco. Só executa depois das checagens locais. Exige GEMINI_MODEL explícito e compatível com o runtime; não adivinha um modelo vigente. A resposta precisa corresponder aos filtros sintéticos esperados. Não é teste do fluxo JWT/banco completo.

## Verificações para executar

Na pasta front_end:

```powershell
node tests/assistente.test.cjs
node tests/assistente-sessao.test.cjs
node tests/voz-revisao.test.cjs
npx tsc --noEmit
npm run lint
node --test tests/*.test.cjs
npx expo export --platform web
```

Para os testes novos do diagnóstico, na raiz C:\litro_de_ouro:

```powershell
.\back_end\venv\Scripts\python.exe -B -m unittest discover -s back_end/tests -p "test_verificar_assistente.py"
```

Esses testes usam somente a biblioteca padrão e módulos simulados. Não homologam SDK ou provedor reais.

O diagnóstico real deve rodar no runtime usado pela API. Se a imagem Docker não monta os fontes, reconstruir e recriar somente o backend local para incluir o script. Preservar volumes/banco e a mesma combinação atual de arquivos Compose, incluindo overrides utilizados; não alterar portas ou raio neste bloco. Os comandos abaixo mostram a combinação base:

```powershell
Set-Location C:\litro_de_ouro
docker compose -f compose.yaml --env-file docker/local/.env build backend
docker compose -f compose.yaml --env-file docker/local/.env up -d --no-deps --wait --wait-timeout 180 backend
docker compose -f compose.yaml --env-file docker/local/.env exec -T backend python -B scripts/verificar_assistente.py
```

O último comando não chama o Gemini. `pendencias` com chave/modelo ausentes é um diagnóstico esperado, não falha dos comandos objetivos. Não executar `--teste-provedor` automaticamente nesta aplicação. A homologação real do provedor será uma etapa explícita posterior, com configuração presente no backend do runtime correto.

## Configuração a mapear, sem copiar segredos

Registrar somente presença/ausência de GEMINI_API_KEY, GEMINI_MODEL e SECRET_KEY no runtime da API. GEMINI_THINKING_LEVEL, GEMINI_TIMEOUT_S e IA_LIMITE_POR_HORA continuam com as regras existentes. O limite atual é em memória por processo, não uma quota global entre múltiplos workers.

Manter credenciais no backend. Não colocar GEMINI_API_KEY em variável EXPO_PUBLIC nem em código frontend. Variáveis presentes no host não comprovam presença no container. A versão do SDK já corrigida deve ser preservada; o verificador anterior verificar_sdk_ia.py continua válido.

## Evidência desta preparação

- 10 novos testes de tela/serviço com hooks/JSX/foco/API/voz simulados: aprovados.
- 3 novos testes do adaptador de voz com navegador simulado: aprovados.
- 8 testes existentes do assistente: aprovados na cópia de compatibilidade.
- 8 testes novos do diagnóstico com módulos sintéticos: aprovados.
- TypeScript e lint: exit 0 na cópia de compatibilidade. Ela usa contextos/dependências anteriores e o contrato de registro já adaptado na revisão anterior, não a árvore Windows atual.
- `git apply --check AJUSTES.patch`: aprovado contra a base disponível em uma pasta isolada, não contra a árvore local do responsável.
- Nenhuma chamada real ao Gemini, gravação no banco, teste físico ou publicação nesta preparação.
- Não foi repetida a tentativa de prévia visual, já bloqueada pela política do navegador nesta sessão. Não há nova captura ou homologação visual.

## Homologação manual e retorno

1. Digitar diesel/etanol com bandeira e referência; conferir prévia e só então aplicar no mapa/feed. Não misturar preços/unidades nem inventar ofertas desconhecidas.
2. Cancelar uma busca e iniciar outra; voltar à aba após sair durante o carregamento; trocar a conta. Respostas anteriores não devem reaparecer.
3. Alterar filtro ou localização com prévia aberta: exigir nova busca antes de aplicar.
4. Em navegador compatível e contexto seguro, falar, revisar texto e buscar. Exercitar silêncio, permissão negada e parar escuta. Na versão nativa, testar o ditado do teclado.
5. Conferir tema claro/escuro, teclado, fonte ampliada, foco e botões no aparelho e na web. Não avaliar nem interagir ao dirigir.

Devolver relatório com arquivos/funções aplicados, diferenças em relação à base, diff incremental incluindo arquivos novos, comandos/resultados, configurações somente por nome/presença e explicação técnica. Separar simulação, build, teste real de provedor e teste físico. Preservar a árvore existente; não publicar, agendar ou aplicar migrações.
