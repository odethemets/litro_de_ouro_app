# Comentários de manutenção — primeiro lote

Destinatário: Codex web. Data: 13/11/2026, America/Fortaleza.
Referência: `main`, HEAD `0ec3c78`, com alterações anteriores preservadas.
Pedido: comentar brevemente a função dos códigos, incluindo os antigos, para facilitar manutenção futura. Revisão própria; não houve revisão independente.

## Resultado

Foram acrescentados comentários curtos em português em 14 arquivos: explicam a responsabilidade da função e, quando relevante, onde revisar GPS, filtros, transações, sessão, auditoria e pontuação. Descrições úteis já existentes foram preservadas, sem duplicação desnecessária.

Este é o primeiro lote, abrangendo oferta, votos, cadastro de preço, avisos e consulta de postos. Não representa documentação de todas as funções do repositório. Os próximos códigos recebidos devem seguir o mesmo padrão; o restante da base pode ser documentado por novos lotes autorizados.

## Arquivos e pontos de manutenção

| Arquivo | Funções/trechos documentados |
| --- | --- |
| `back_end/app/rotas/ofertas.py` | `confirmar_oferta`: disponibilidade, GPS, negativas e auditoria. |
| `back_end/app/rotas/votos.py` | `resumo`, `votos`: vínculo ao registro, contagens, locks, repetição/troca e Karma. |
| `back_end/app/rotas/precos.py` | `registrar_preco_validado`, `registrar_preco`: transação e encaminhamento da rota. Validadores auxiliares já possuíam descrições e foram preservados. |
| `back_end/services/atividade_alertas.py` | `registrar_karma`, `processar_pendentes`: origem única, responsabilidade pelo commit e avisos internos. |
| `back_end/services/catalogo_postos.py` | `normalizar_marca`, `validar_filtros`, `_numero`, `_estado`, `_data`, `consultar_catalogo`: normalização, ausência de informação, consulta em lote e referência. |
| `back_end/scripts/processar_alertas.py` | `main`: validação do destino e rodada manual. |
| `back_end/scripts/verificar_sdk_ia.py` | `verificar`: diagnóstico do SDK sem chamada externa. |
| `front_end/src/services/ofertas.ts` | `payloadOferta`, `validarConfirmacaoOferta`: GPS e confirmação do mesmo posto/produto. |
| `front_end/src/services/votos.ts` | `lerAvaliacao`: contrato e registro exato. |
| `front_end/src/services/catalogoPostos.ts` | Funções de seleção, parâmetros, segmentos, referência, rótulo, data, classificação e leitura; também `produto`, `precoFormatado` e auxiliar `recente`. |
| `front_end/src/components/confirmar-oferta.tsx` | `ConfirmarOferta`, `ControlesOferta`, `confirmar`: sessão, revisão, GPS, envio e recarga. |
| `front_end/src/components/votar-preco.tsx` | `VotarPreco`, `ControlesVoto`, `consultar`: isolamento de sessão, consulta e gravação. |
| `front_end/src/screens/ConsultaPostos/detalhes.tsx` | `DetalhesPostoConsulta`: composição dos detalhes e delegação das ações. |
| `front_end/src/screens/ConsultaPostos/index.tsx` | `ConsultaPostos`, `escolher`, `cartao`, `abrirCadastro`, `lista`, `detalhes`, `fecharPainel`: navegação e estados compartilhados. |

Os comentários não alteram contratos, regras, SQL, locks, JSX ou configuração. Nenhuma dependência, migração ou teste foi acrescentado. Todos os arquivos deste lote permanecem com até 500 linhas. Não se mediu desempenho porque o código executável foi preservado.

## Evidências

Antes da edição: fontes copiados por lista explícita para `base/`, com `BASE_SHA256.json`. Apenas os fontes deste lote foram copiados, sem segredos. O diff em `ALTERACOES.patch` compara essa base ao conteúdo final; inclui os arquivos que já eram não rastreados no Git. Não é um diff de toda a árvore contra o HEAD.

| Verificação executada | Ambiente | Resultado / arquivo |
| --- | --- | --- |
| Comparação `ast.dump(ast.parse(...))` antes/depois | Python do backend Docker | Sete fontes Python estruturalmente iguais; `VERIFICACAO_ESTRUTURAL.json`. |
| Printer TypeScript com `removeComments: true` antes/depois | TypeScript instalado no frontend | Sete fontes TS/TSX iguais sem comentários; mesmo JSON. |
| `git apply --reverse --check ALTERACOES.patch` | Raiz do projeto | Aprovado, sem aplicar reversão; `PATCH_CHECK.log`. |
| `node node_modules/typescript/bin/tsc --noEmit` | `front_end`, Node local | Exit 0; `TYPESCRIPT.log`. |
| `npm run lint` | `front_end`, Node local | Exit 0; `LINT.log`. |
| `node --test tests/*.test.cjs` | `front_end`, contratos/estados simulados | 82 aprovados; `TESTES_FRONTEND.log`. |
| `docker compose -f compose.yaml --env-file docker/local/.env exec -T backend python -B scripts/testar_offline.py` | Backend Docker local | Sete suítes aprovadas, 128 casos unittest e scripts de assertivas de IA/geofence; `TESTES_BACKEND.log`. |
| `git diff --check` | Raiz | Aprovado; apenas avisos de conversão LF/CRLF. |

Não foram repetidos testes destrutivos de integração, build, chamadas a provedores ou homologação visual/física: não houve alteração de comportamento, e a comparação estrutural confirma isso. Não houve escrita no banco, deploy ou agendamento.

## Reversão e continuidade

Para desfazer somente este lote, conferir a correspondência do patch com `git apply --reverse --check docs/entregas/2026-11-13-comentarios/ALTERACOES.patch` antes de aplicá-lo em reverso. Se houver mudanças posteriores, revisar os conflitos; não restaurar a árvore inteira nem usar reset/limpeza. As cópias `base/` permitem comparar cada arquivo individualmente.

O relatório e o diff são destinados ao Codex web. Nenhuma versão para Gemini foi preparada. O padrão solicitado para os próximos códigos é manter comentários curtos por função, concentrados em responsabilidade e manutenção, sem comentar cada linha óbvia.
