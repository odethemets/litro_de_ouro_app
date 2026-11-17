# Litro de Ouro — continuidade local

Atualizado em **13/11/2026**, referência America/Fortaleza. Esta atualização descreve o disco e os testes executados nesta sessão. O [relatório recebido](docs/RELATORIO_RECEBIDO_2026-11-13.md) permanece como histórico; divergências são resolvidas pelas evidências abaixo.

## Estado confirmado

- Projeto `C:\litro_de_ouro`, branch `main`, HEAD `0ec3c78`, com muitas alterações e arquivos não rastreados anteriores à sessão. Foram preservados; não houve commit, reset, publicação ou deploy.
- Compose principal e override já estavam corrigidos. Há uma publicação do backend `5001:5000` e banco restrito a `127.0.0.1:3307`. Nenhuma alteração nesses arquivos foi necessária.
- Containers db e backend saudáveis. Verificador confirmou TLS, API, listagem, login da conta fictícia e perfil.
- Banco local `litro_de_ouro_dev`, MySQL 8.4.13: **59 postos, 1 usuário, 11 registros de preço, 0 votos**, conforme verificador nesta sessão. As contas e contribuições de teste novas foram criadas em outro banco.
- Migrações 001–004 aplicadas e checksums aceitos pelo dry-run. Nenhuma migração foi aplicada ao banco do responsável nesta sessão.
- API pública do frontend configurada em `http://192.168.1.9:5001`; ipconfig mostrou esse endereço e também `192.168.1.8` em outra interface. Não foi testado o alcance pelo celular.
- Override de desenvolvimento continua com **raio de 50 km**. Os testes de integração usaram processo separado com raio de 500 m e coordenadas sintéticas; não homologam presença física.

## Diferenças encontradas e integração feita

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

## Política de votos efetivamente implementada

Mantida a regra existente: preço começa com score 1 e concede +5 Karma ao autor. Novo voto positivo/negativo altera score em +1/-1 e Karma do autor em +2/-2. Trocar voto altera score em +2/-2 e Karma em +4/-4. Repetir o mesmo voto não altera pontuação nem cria evento de histórico. Voto próprio é recusado; conta e registro precisam existir.

Não foi definido limiar de validado/contestado, remoção automática, prioridade no catálogo ou moderação. A interface informa que o score inicial não é confirmação comunitária. O catálogo continua escolhendo o último preço por produto. Essa política de moderação permanece uma decisão aberta do responsável.

Oferta, preço e voto continuam separados. O Maxi Posto não teve sua disponibilidade confirmada automaticamente; a ação depende da observação do usuário no local. Registros antigos não receberam eventos ou histórico inventados. O saldo anterior permanece o saldo registrado na migração.

## Verificações executadas

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

## Operação e próximos passos

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
