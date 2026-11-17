# Aplicação e revisão — oferta, votos e detalhes

## Resultado preparado

Os códigos foram construídos a partir dos componentes/serviços colados e das duas unidades de ConsultaPostos anexadas nesta conversa. São entregues três arquivos completos; nenhum foi aplicado ao projeto Windows, publicado ou enviado a um serviço externo.

O conteúdo completo está em `CODIGOS_PROXIMO_BLOCO.md`, além dos arquivos individuais sob `front_end/`.

## Coerência visual

- Preserva AppButton, Notice, useAppTheme e os estilos existentes do aplicativo.
- Mantém superfícies, bordas e textos vinculados ao tema, sem fundos brancos fixos.
- Identifica cada combustível com faixa na cor do catálogo e nome escrito. A faixa do cartão identifica o produto e não confirma sua disponibilidade; o texto de disponibilidade continua explícito. As barrinhas dos marcadores do mapa não foram modificadas.
- Exibe a referência primeiro e expandida. Os outros cartões começam recolhidos; autor, data e horário continuam visíveis mesmo assim.
- Reserva o botão primário de preço para o cartão da referência. Demais ações usam o estilo secundário. O botão genérico de cadastro foi substituído pelas ações específicas de cada produto permitido.
- A expansão tem alvo mínimo de 48 px, estado acessível expanded, foco visível e textos que podem quebrar linha. Os botões compartilhados mantêm seu comportamento atual.
- Preços nos detalhes continuam neutros. Não são atribuídas cores de barato/caro por voto, nem alterada a comparação da referência no mapa/feed.

## Construção dos controles

`ConfirmarOferta` reinicia o controle por sessão, posto e combustível. Um AbortController por operação bloqueia envios concorrentes e impede aplicar uma resposta após desmontagem. A localização é obtida somente depois da revisão explícita. A confirmação válida e o pedido de recarga são tratados separadamente: falha ao iniciar a recarga não declara que a escrita falhou.

Falha de GPS permite corrigir e repetir. Recusa HTTP 4xx, exceto 408, é apresentada como recusa. Resposta perdida, falha 5xx/408 ou payload incompatível deixa o resultado incerto, com ação de atualizar catálogo e sem reenvio direto naquele controle. O callback atual de recarga retorna void; o componente não declara que a atualização terminou. Se o catálogo continuar sem resposta, revisar sua conectividade. Fechar/reabrir os detalhes desmonta o controle; isso não prova nem desfaz uma gravação no servidor.

`VotarPreco` reinicia por sessão e ID do preço. Não consulta ao montar. Um voto só é enviado depois de consultar a permissão; o voto já selecionado fica desabilitado, e a outra opção permite troca. Falha remove o resumo utilizável e exige uma nova consulta. A mensagem continua explicando que score inicial 1 não equivale a um selo de validação.

Abortar uma requisição é uma proteção do estado da interface, não uma reversão de transação nem uma garantia de que o servidor deixou de receber a escrita. As regras backend de autenticação, proximidade, transação e idempotência permanecem necessárias.

## Arquivos para aplicar

1. `front_end/src/components/confirmar-oferta.tsx` — 135 linhas.
2. `front_end/src/components/votar-preco.tsx` — 118 linhas.
3. `front_end/src/screens/ConsultaPostos/detalhes.tsx` — 175 linhas.

Os serviços recebidos `ofertas.ts` e `votos.ts`, os caminhos da API, ConsultaPostos/index.tsx, o contexto de filtros, migrações, Compose e backend são preservados. Nenhuma dependência nova é necessária. O tipo atual de oferta deve continuar contendo `registo_id: number | null`, como no código recebido.

## Instrução ao Codex local

Conferir diferenças feitas depois do envio dos fontes. Aplicar somente estes três arquivos, preservando alterações posteriores relevantes. Não reimplementar os serviços nem reverter arquivos de outras entregas. Manter comentários breves sobre responsabilidade e manutenção. Testar e relatar as adaptações eventualmente necessárias, antes de considerar o bloco concluído. Não fazer deploy, commit, alteração de banco ou agendamento nesta etapa.

Executar na pasta `front_end`:

```powershell
node tests/participacao.test.cjs
npx tsc --noEmit
npm run lint
```

Depois executar as demais suítes frontend existentes conforme o comando utilizado pelo projeto. Não remover testes para acomodar a entrega.

O verificador adicional em `evidencias/verificar_controles.cjs` pode ser executado separadamente, sem instalar dependências:

```powershell
node CAMINHO_DO_ARQUIVO\verificar_controles.cjs C:\litro_de_ouro\front_end
```

Ele usa o TypeScript instalado no frontend, hooks simulados, API/GPS fictícios e gera LOGICA.json ao lado do script. Não usa React/React Native reais e não substitui a homologação da interface.

## Verificação realizada aqui

- Oito testes de contrato dos serviços recebidos: aprovados.
- Dezenove cenários de lógica dos TSX com hooks/chaves/desmontagem/API/GPS simulados: aprovados. Incluem oferta incerta, recusa, falha de recarga, troca de conta/posto e novo ID sem estado anterior.
- TypeScript: exit 0 em uma cópia de compatibilidade. Essa cópia usa os fontes fornecidos mais dependências/contextos de uma versão anterior disponível; o catálogo antigo foi adaptado somente nessa cópia ao campo registo_id que já existe no contrato local recebido. Isso não é validação integral da árvore Windows atual.
- ESLint nos três arquivos entregues: exit 0.
- As três unidades de produto ficam abaixo de 500 linhas.

Não houve teste real de API, GPS, banco ou Expo Go nesta rodada. A tentativa de prévia no Chromium foi interrompida por `net::ERR_BLOCKED_BY_ADMINISTRATOR` ao abrir a página local. Não houve tentativa de contornar a política, captura visual aprovada ou confirmação de responsividade pelo navegador. Tipos/lint e simulações não comprovam o resultado visual final.

## Conferência visual e manual pendente

1. Em largura estreita, abrir um posto: referência primeiro, autoria/data visíveis, combustível identificado por faixa e nome. Expandir outro cartão; verificar quebra de textos e rolagem.
2. Conferir tema claro/escuro e foco por Tab/Enter na web. Testar ampliação de fonte no aparelho e acesso aos botões inferiores com uma mão.
3. Visitante abre login; cancelar revisão não solicita GPS. GPS negado apresenta erro e não confirma oferta.
4. Com oferta desconhecida observada em um local de teste, confirmar e conferir catálogo, filtro e barrinhas. Usar raio normal de 500 m em homologação presencial; o raio de desenvolvimento de 50 km não comprova proximidade.
5. Uma conta registra preço; outra consulta, confirma e troca o voto. Conferir o ID exato e o histórico. Um novo preço começa sem votos anteriores.
6. Trocar conta ou registro durante uma operação. Conferir que resposta antiga não aparece na sessão atual.
7. Simular falta de rede: voto exige nova consulta; oferta incerta orienta atualizar catálogo. Verificar o estado no servidor antes de nova confirmação manual.

Entregar relatório com arquivos/funções aplicados, diff incremental, comandos/resultados, capturas realmente obtidas, limitações e adaptações ao código local. Nenhuma publicação é solicitada.
