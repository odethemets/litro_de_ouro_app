# Aplicação recebida — oferta, votos e detalhes

Destinatário: **Codex web**. Data/fuso: 13/11/2026, America/Fortaleza.
Responsabilidade nesta entrega: conferir compatibilidade, aplicar os arquivos recebidos e executar verificações; gerar relatório/diff/resultados. Revisão técnica própria, sem revisão independente.
Referência: `main`, HEAD `0ec3c786b2f07e32c7e06d0cf73da5c9b9ee9194`, árvore previamente modificada e com arquivos não rastreados. Identificação em `REFERENCIA.json`; fontes anteriores à aplicação em `base/`, com hashes em `BASE_SHA256.json`.

## Resultado aplicado

Os três arquivos de produto foram extraídos dos blocos TSX do anexo e aplicados **sem adaptação**. A igualdade entre o código recebido e o aplicado foi conferida byte a byte e registrada em `APLICACAO_SHA256.json`. Foram preservadas as outras alterações locais. Os novos fontes já contêm comentários breves por função, em atendimento ao pedido anterior do responsável.

| Arquivo / tamanho | Funções e mudança observável |
| --- | --- |
| `front_end/src/components/confirmar-oferta.tsx` — 135 linhas | `ConfirmarOferta`: chave por conta/status/posto/produto. `ControlesOferta`: etapas início/revisão/confirmada/incerta. `confirmar`: GPS após revisão, um envio ativo, abort na saída e resposta válida. `atualizar`: separa falha síncrona da recarga de sucesso da escrita. |
| `front_end/src/components/votar-preco.tsx` — 118 linhas | `VotarPreco`: chave por conta/status/registro. `ControlesVoto`: consulta sob demanda, ação ocupada e feedback. `consultar`: exige permissão consultada, impede repetir o mesmo voto, permite troca e limpa resumo em falha. |
| `front_end/src/screens/ConsultaPostos/detalhes.tsx` — 175 linhas | `DetalhesPostoConsulta`: referência primeiro, sem modificar o array do catálogo; `tracarRota`: abre navegação externa com origem somente se há posição. `CartaoCombustivel`: mostra nome/cor/unidade/autor/data, expansão acessível e monta contribuições apenas aberto. |

Antes, os controles distinguiam menos estados de falha/sucesso e sua identidade dependia em parte da chave fornecida pelo pai. Os detalhes mostravam todos os controles e um botão genérico de cadastro. Depois, a oferta incerta só oferece recarga naquele controle; voto incerto exige nova consulta; a referência inicia expandida e os outros cartões recolhidos, com ações específicas do produto.

Nenhum fonte de backend, serviço, contexto, layout compartilhado, configuração, migração ou dependência foi alterado. Todos os três arquivos de produto permanecem abaixo de 500 linhas. Não houve commit, alteração de banco, deploy ou agendamento.

## Compatibilidade conferida

- Expo 58, React 19.3, React Native 0.88 e Axios instalados no projeto. `AppButton` já aceita `busy`, `disabled`, `selected` e `secondary`; `Notice` aceita mensagens/erro e as cores do tema existem.
- `ofertas.ts` continua fornecendo `payloadOferta` e `validarConfirmacaoOferta`; `votos.ts` fornece `lerAvaliacao`, `AvaliacaoPreco`, `Voto`. Nenhuma regra desses serviços foi reimplementada.
- `OfertaPosto.registo_id` local é opcional (`number | null` quando presente), enquanto o texto recebido cita campo obrigatório. Não foi necessário mudar o contrato: o JSX protege a montagem com preço e ID válidos; ausência de ID mantém a leitura sem avaliação.
- `ConsultaPostos/index.tsx` já passa `onAtualizar={recarregar}`; o callback retorna void. A confirmação não afirma que a recarga terminou e não captura eventual falha assíncrona futura do contexto.
- Os três arquivos locais continham os comentários acrescentados na rodada anterior. As responsabilidades equivalentes continuam comentadas no material recebido; não havia outra alteração funcional posterior nesses três arquivos que exigisse mesclagem adicional.
- Foram consultadas as referências de [Expo SDK 58](https://docs.expo.dev/versions/v58.0.0/), [Pressable](https://reactnative.dev/docs/pressable) e [acessibilidade React Native](https://reactnative.dev/docs/accessibility), conforme as instruções locais. Não houve migração de navegação ou inclusão de biblioteca.

## Fluxo, contratos e falhas

Oferta: detalhes do combustível → `ConfirmarOferta` → revisão explícita → `obterPosicao("registro")` → `payloadOferta` → POST `/postos/<postoId>/ofertas/<codigo>/confirmar`, com sessão capturada e `signal` → `validarConfirmacaoOferta` → estado confirmado e pedido de recarga. Permanece a validação backend de autenticação/proximidade/disponibilidade; nenhum SQL ou limite foi alterado.

O campo enviado continua `{ confirmado: true, latitude, longitude, precisao_m, simulada: false }`. A confirmação deve corresponder ao mesmo posto/código com disponibilidade true e origem válida. Erro antes de enviar permite corrigir GPS/repetir; 4xx exceto 408 é recusa. 408, 5xx, rede ou resposta incompatível após envio produzem resultado incerto. Não há reenvio automático. Erro ao iniciar a recarga não converte a escrita confirmada em falha.

Voto: cartão aberto → `VotarPreco` → GET `/precos/<registoId>/votos` → `lerAvaliacao` → ações somente se `pode_votar` → POST `/precos/<registoId>/votar`, corpo `{ voto: "positivo" | "negativo" }` → validação e feedback. O campo `meu_voto` desabilita a opção já selecionada; a outra opção permite troca. Em falha, o resumo é removido e precisa ser consultado de novo. Autor não recebe botões; o backend continua protegendo voto próprio e idempotência.

As chaves incluem sessão/status e IDs do domínio. A desmontagem aborta a requisição e impede usar respostas tardias; **não desfaz uma escrita já recebida pelo servidor**. Fechar/reabrir os detalhes desmonta o controle e não substitui a reconciliação do estado no servidor.

Cartões: uma cópia superficial da lista é ordenada para destacar a referência. A faixa colorida identifica o combustível, inclusive se a oferta é desconhecida ou negativa; o texto mantém a disponibilidade explícita. As barrinhas do mapa e a comparação de preços não mudaram. Autor/data ficam visíveis mesmo recolhido. Expandir monta controles, mas o GET dos votos continua dependendo de clique. Não se mediram RAM, desempenho ou número de frames; não há alegação de ganho mensurado.

## Verificações executadas e evidências

Diretório dos comandos frontend: `C:\litro_de_ouro\front_end`, Node local. Logs individuais neste diretório de entrega.

| Comando | Resultado | Evidência / limite |
| --- | --- | --- |
| `node tests/participacao.test.cjs` | 8 aprovados | `PARTICIPACAO.log`; contratos dos serviços existentes. Esses oito também estão nos 82 abaixo, não somar. |
| `node node_modules/typescript/bin/tsc --noEmit` | Exit 0 | `TYPESCRIPT.log` vazio porque não houve diagnóstico. Mesma ferramenta de `npx tsc`, sem resolução externa. |
| `npm run lint` | Exit 0 | `LINT.log`; usa o script Expo do projeto. |
| `node --test tests/*.test.cjs` | **82 aprovados** | `TESTES_FRONTEND.log`; nenhuma suíte anterior foi removida. |
| `node docs/entregas/2026-11-13-controles-recebidos/evidencias/verificar_controles.cjs C:\litro_de_ouro\front_end` (raiz) | **20 cenários aprovados** | `evidencias/LOGICA.json`; simula hooks/JSX, API e GPS; não usa React/RN reais nem chama API. |
| `npx expo export --platform web` | Aprovado, `front_end/dist` | `EXPORT_WEB.log`; build local, não publicação ou captura visual. |
| `git apply --reverse --check .../ALTERACOES.patch` | Aprovado | `PATCH_CHECK.log`; apenas conferência, não aplicou reversão. |
| `git diff --check` | Aprovado | Somente avisos de LF/CRLF em fontes já existentes. |

O anexo cita um verificador adicional, mas não inclui seu arquivo. O script de evidência entregue aqui foi criado localmente para testar os fontes recebidos; **não é o script original nem reprodução dos 19 cenários relatados pelo outro ambiente**. Ele transpila os TSX instalados e os serviços locais, substitui hooks/JSX/dependências de UI e inspeciona handlers/estado. É uma verificação lógica complementar, sem adicionar dependências ao aplicativo.

Os 20 cenários cobrem: visitante, cancelamento sem GPS, GPS negado sem POST, sucesso da oferta com falha de recarga, payload inválido, HTTP 408/503, recusa 409, duplo clique, desmontagem durante GPS, chaves por sessão/posto/produto, ausência de GET ao montar voto, autor bloqueado, voto selecionado/troca, falha que exige reconciliação, ID divergente, abort de GET, chave do novo preço, ordem da referência sem mutação e expansão que monta os controles. `LOGICA.json` identifica cada cenário e resultado; hooks simulados não comprovam a reconciliação real do React ou comportamento nativo.

Não executados: API/GPS reais, testes de banco, Expo Go, microfone, teste em aparelho e homologação visual de largura estreita/tema/foco/rolagem. Não há captura obtida nesta rodada. A ferramenta já havia interrompido o controle do Firefox nesta sessão por falta de suporte à política de URLs; não houve tentativa de contornar essa restrição. Também não foi presumida uma captura com base na exportação. Backend não foi testado novamente porque não foi modificado e nenhuma escrita real foi necessária.

## Diff, revisão e reversão

`ALTERACOES.patch` compara os três fontes de produto com as cópias em `base/`, e inclui o novo verificador local como arquivo novo em `evidencias/`. Os anexos recebidos estão preservados em `CODIGOS_RECEBIDOS.md` e `INSTRUCOES_RECEBIDAS.md`; `recebidos/` contém cada unidade extraída. `BASE_SHA256.json`/`APLICACAO_SHA256.json` identificam antes e depois. Relatório, logs e manifestos são entregues completos, sem inclusão recursiva no próprio patch.

Para desfazer apenas esta entrega: primeiro conferir `git apply --reverse --check docs/entregas/2026-11-13-controles-recebidos/ALTERACOES.patch`; aplicar em reverso somente se o conteúdo ainda corresponder. Isso restaura os três fontes e remove o verificador de evidência novo. Com alterações posteriores, revisar por arquivo em vez de sobrescrever; as cópias anteriores permitem mesclar. Nenhuma reversão de banco ou imagem Docker é necessária nesta etapa.

## Próximo passo

Validar visualmente no ambiente acessível ao responsável: referência primeiro/expandida, outros cartões recolhidos, autoria/data, nomes/unidades, tema claro/escuro, Tab/Enter, foco, rolagem e fonte ampliada. Depois testar duas contas, GPS real e resultados incertos em ambiente de teste com raio normal. O raio de desenvolvimento de 50 km não comprova presença física.

A aplicação local e as verificações descritas estão concluídas; a homologação visual/física permanece aberta. Nenhuma versão de relatório para Gemini foi gerada, conforme a orientação do responsável.
